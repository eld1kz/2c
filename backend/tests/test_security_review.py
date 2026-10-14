"""Regression tests for the Phase 3 security review findings (one test group per finding)."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import routes_auth
from app.db.models import (
    Action,
    AuditEvent,
    Base,
    Business,
    Policy,
    Role,
    SandboxEmail,
    SandboxPayment,
    Transaction,
    User,
)
from app.engine.categorize import NullClassifier
from app.services.action_service import ActionError, ActionService, InvalidState, NotFound, actor_for
from seed.load import DEMO_PASSWORD, load
from tests.conftest import Demo, FakeClock
from tests.test_api import _login, _propose_verde, client, db  # noqa: F401  (fixtures)

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model))


def _last_event(session: Session) -> AuditEvent:
    return session.scalar(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1))


def _verde(demo: Demo, key: str, amount: int = 219_600, day: str = "2026-10-08") -> Action:
    return demo.service.propose(demo.actor("owner"), "schedule_payment", {
        "payee_counterparty_id": demo.counterparties["Verde Green Coffee Imports"].id,
        "invoice_id": demo.invoices["VGC-5513"].id, "amount": amount, "date": day}, idempotency_key=key)


# 1. concurrent approve/reject on a stale `proposed` copy -----------------------------------------

@pytest.fixture
def two_sessions() -> Iterator[tuple[Session, Session]]:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        load(s, classifier=NullClassifier())
        s.commit()
    with Session(engine) as a, Session(engine) as b:
        yield a, b


def _svc(session: Session) -> tuple[ActionService, dict[str, User]]:
    return (ActionService(session, date(2026, 10, 1), FakeClock(T0)),
            {u.role.value: u for u in session.scalars(select(User))})


@pytest.mark.parametrize("second", ["approve", "reject"])
def test_stale_second_decision_cannot_overwrite_an_executed_payment(two_sessions: tuple[Session, Session],
                                                                    second: str) -> None:
    s1, s2 = two_sessions
    svc1, users1 = _svc(s1)
    svc2, users2 = _svc(s2)
    from sqlalchemy import select as sel

    from app.db.models import Counterparty, Invoice
    verde = s1.scalar(sel(Counterparty).where(Counterparty.name == "Verde Green Coffee Imports"))
    vgc = s1.scalar(sel(Invoice).where(Invoice.number == "VGC-5513"))
    action = svc1.propose(actor_for(users1["owner"]), "schedule_payment", {
        "payee_counterparty_id": verde.id, "invoice_id": vgc.id, "amount": 219_600, "date": "2026-10-08"},
        idempotency_key="race-1")
    s1.commit()
    stale = s2.get(Action, action.id)  # request 2 loads it while still `proposed`
    assert stale.status == "proposed"
    executed = svc1.approve(users1["owner"], action.id)
    s1.commit()
    if second == "approve":
        replay = svc2.approve(users2["owner"], action.id)
        assert replay.status == "executed" and replay.result == executed.result
    else:
        with pytest.raises(InvalidState):
            svc2.reject(users2["owner"], action.id)
    s2.commit()
    s1.expire_all()
    assert s1.get(Action, action.id).status == "executed"
    assert _count(s1, SandboxPayment) == 1


# 2. loan limits are cumulative -----------------------------------------------------------------

@pytest.mark.parametrize("option,limit", [("invoice_factoring", 1_392_300), ("overdraft", 1_500_000)])
def test_loan_limit_counts_earlier_applications(demo: Demo, option: str, limit: int) -> None:
    first = demo.service.propose(demo.actor("owner"), "submit_loan_application",
                                 {"option_id": option, "amount": limit - 100}, idempotency_key=f"{option}-1")
    assert demo.service.approve(demo.users["owner"], first.id).status == "executed"
    again = demo.service.propose(demo.actor("owner"), "submit_loan_application",
                                 {"option_id": option, "amount": 101}, idempotency_key=f"{option}-2")
    assert again.status == "denied" and f"limit 100 " in again.result["denied"]
    ok = demo.service.propose(demo.actor("owner"), "submit_loan_application",
                              {"option_id": option, "amount": 100}, idempotency_key=f"{option}-3")
    assert ok.status == "proposed"


# 3. /audit only lists the caller's business ----------------------------------------------------

def test_audit_list_is_scoped_to_business(client: TestClient, db) -> None:  # noqa: F811, ANN001
    owner = _login(client, "owner")
    _propose_verde(client, owner, db)
    with db() as s:
        other = Business(name="Other Co", base_currency="USD", industry="x", min_cash_buffer=0, settings={})
        s.add(other)
        s.flush()
        hashed = s.scalar(select(User.password_hash))
        s.add(User(business_id=other.id, email="owner@other.example", name="O", role=Role.owner, password_hash=hashed))
        s.commit()
    r = client.post("/auth/login", json={"email": "owner@other.example", "password": DEMO_PASSWORD})
    events = client.get("/audit", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert {e["event_type"] for e in events} == {"login_succeeded"}
    assert all(e["payload"]["business_id"] == 2 for e in events)
    mine = client.get("/audit", headers=owner).json()
    assert "action_proposed" in {e["event_type"] for e in mine}
    assert all(e["payload"].get("business_id") == 1 for e in mine)


# 5 + 9. inputs that cannot be stored/hashed are refused before any write -----------------------

@pytest.mark.parametrize("params", [{"amount": float("nan")}, {"amount": float("inf")}, {"note": "\ud800"}])
def test_unstorable_input_refused_and_audited(demo: Demo, params: dict) -> None:
    with pytest.raises(ActionError):
        demo.service.propose(demo.actor("owner"), "schedule_payment", params, idempotency_key="bad-input")
    assert _count(demo.session, Action) == 0
    event = _last_event(demo.session)
    assert event.event_type == "action_input_rejected" and event.payload["reason"].startswith("invalid input")


def test_unstorable_input_over_http_is_422(client: TestClient, db) -> None:  # noqa: F811, ANN001
    owner = _login(client, "owner")
    body = '{"tool": "schedule_payment", "idempotency_key": "nan-input-1", "params": {"amount": NaN}}'
    r = client.post("/actions", headers=owner | {"Content-Type": "application/json"}, content=body)
    assert r.status_code == 422
    r = client.post("/auth/login", content='{"email": "\\ud800@x.example", "password": "x"}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


# 6. over-long passwords are a normal, audited failure -----------------------------------------

@pytest.mark.parametrize("password", ["a" * 73, "é" * 50, DEMO_PASSWORD + "x" * 72])
def test_long_password_is_401_and_audited(client: TestClient, db, password: str) -> None:  # noqa: F811, ANN001
    r = client.post("/auth/login", json={"email": "owner@emberoak.demo", "password": password})
    assert r.status_code == 401
    with db() as s:
        assert _last_event(s).event_type == "login_failed"


# 7. refusals that used to leave no audit trace ------------------------------------------------

def test_refusals_are_audited(demo: Demo) -> None:
    with pytest.raises(ActionError):
        demo.service.propose(demo.actor("owner"), "get_ledger", {}, idempotency_key="read-tool")
    assert _last_event(demo.session).event_type == "action_input_rejected"
    with pytest.raises(NotFound):
        demo.service.approve(demo.users["owner"], 99_999)
    assert _last_event(demo.session).event_type == "action_not_found"
    with pytest.raises(NotFound):
        demo.service.record_draft(demo.actor("owner"), demo.invoices["VGC-5513"].id, "polite")
    assert _last_event(demo.session).event_type == "draft_denied"


def test_proposal_audit_covers_rationale_and_evidence(demo: Demo) -> None:
    demo.service.propose(demo.actor("owner"), "submit_loan_application", {"option_id": "overdraft", "amount": 1},
                         idempotency_key="with-why", rationale="bridge week 6", evidence_ids=("insight:4",))
    payload = _last_event(demo.session).payload
    assert (payload["rationale"], payload["evidence_ids"]) == ("bridge week 6", ["insight:4"])


def test_upload_overflow_amount_is_rejected_and_audited(client: TestClient, db) -> None:  # noqa: F811, ANN001
    data = b"Date,Description,Amount,Balance\n10/01/2026,BIG,99999999999999999999999.00,1.00\n"
    r = client.post("/upload", headers=_login(client, "owner"), files={"file": ("big.csv", data, "text/csv")})
    assert r.status_code == 422 and "out of range" in r.json()["detail"]
    with db() as s:
        assert _last_event(s).event_type == "upload_rejected"


# 8. idempotency keys: per business, and never silently reused for different params ------------

def test_idempotency_conflict_and_business_scope(demo: Demo) -> None:
    first = _verde(demo, "same-key", amount=100_000)
    with pytest.raises(InvalidState):
        _verde(demo, "same-key", amount=1)
    assert _last_event(demo.session).event_type == "idempotency_conflict"
    assert _verde(demo, "same-key", amount=100_000).id == first.id
    other = Business(name="Other Co", base_currency="USD", industry="x", min_cash_buffer=0, settings={})
    demo.session.add(other)
    demo.session.flush()
    demo.session.add(Policy(business_id=other.id, max_single_payment=500_000, currency="USD",
                            reminder_cooldown_days=7, require_owner_for=[]))
    stranger = User(business_id=other.id, email="o@other.example", name="O", role=Role.owner, password_hash="x")
    demo.session.add(stranger)
    demo.session.flush()
    theirs = demo.service.propose(actor_for(stranger), "submit_loan_application",
                                  {"option_id": "overdraft", "amount": 1}, idempotency_key="same-key")
    assert theirs.id != first.id and theirs.business_id == other.id


# 10. payment date window ----------------------------------------------------------------------

@pytest.mark.parametrize("day,decision", [("2026-09-30", "denied"), ("1900-01-01", "denied"),
                                           ("2026-12-30", "proposed"), ("2026-12-31", "denied")])
def test_payment_date_window(demo: Demo, day: str, decision: str) -> None:
    assert _verde(demo, f"date-{day}", day=day).status == decision


# 11. stale reminder drafts --------------------------------------------------------------------

def test_reminder_draft_must_match_current_balance(demo: Demo) -> None:
    inv = demo.invoices["INV-1047"]
    draft = demo.service.record_draft(demo.actor("owner"), inv.id, "polite")
    demo.session.add(Transaction(account_id=1, date=date(2026, 10, 1), amount=100_000, currency="USD",
                                 raw_description="HARBORLANE CAFE PMT INV1047", source_file="t.csv", invoice_id=inv.id))
    demo.session.flush()
    action = demo.service.propose(demo.actor("owner"), "send_reminder", {"invoice_id": inv.id, "draft_id": draft.id},
                                  idempotency_key="stale-draft")
    assert action.status == "denied" and "no longer matches" in action.result["denied"]
    assert _count(demo.session, SandboxEmail) == 0


# login lockout --------------------------------------------------------------------------------

def test_login_lockout_after_five_failures(client: TestClient, db, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811, ANN001
    clock = FakeClock(datetime.now(timezone.utc))
    monkeypatch.setattr(routes_auth, "utc_now", clock)
    bad = {"email": "owner@emberoak.demo", "password": "wrong"}
    for _ in range(5):
        assert client.post("/auth/login", json=bad).status_code == 401
    locked = client.post("/auth/login", json={"email": "OWNER@emberoak.demo", "password": DEMO_PASSWORD})
    assert locked.status_code == 429 and locked.headers["Retry-After"] == "900"
    assert client.post("/auth/login", json={"email": "viewer@emberoak.demo", "password": DEMO_PASSWORD}).status_code == 200
    with db() as s:
        types = list(s.scalars(select(AuditEvent.event_type).order_by(AuditEvent.seq)))
    assert types[-2:] == ["login_locked", "login_succeeded"]
    clock.advance(minutes=15, seconds=1)
    assert client.post("/auth/login", json={"email": "owner@emberoak.demo", "password": DEMO_PASSWORD}).status_code == 200


def test_lockout_counts_unknown_emails_too(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.setattr(routes_auth, "utc_now", FakeClock(datetime.now(timezone.utc)))
    for _ in range(5):
        client.post("/auth/login", json={"email": "nobody@emberoak.demo", "password": "x"})
    assert client.post("/auth/login", json={"email": "nobody@emberoak.demo", "password": "x"}).status_code == 429
