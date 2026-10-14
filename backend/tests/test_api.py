"""HTTP API: auth, approvals, audit verify, upload (golden data in SQLite, LLM mocked)."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_classifier, get_session
from app.config import get_settings
from app.db.models import AuditEvent, Base, Counterparty, Invoice, SandboxPayment
from app.main import app
from seed.generate_golden import GOLDEN_DIR, Q3_FILE
from seed.load import DEMO_PASSWORD, load
from tests.fakes import FakeClassifier


@pytest.fixture
def db() -> Iterator[sessionmaker]:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as s:
        load(s, classifier=FakeClassifier())
        s.commit()

    def session_override() -> Iterator[Session]:
        with factory() as s:
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_classifier] = FakeClassifier
    yield factory
    app.dependency_overrides.clear()


@pytest.fixture
def client(db: sessionmaker) -> TestClient:
    return TestClient(app)


def _login(client: TestClient, role: str) -> dict[str, str]:
    r = client.post("/auth/login", json={"email": f"{role}@emberoak.demo", "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _events(db: sessionmaker) -> list[str]:
    with db() as s:
        return list(s.scalars(select(AuditEvent.event_type).order_by(AuditEvent.seq)))


def _ids(db: sessionmaker) -> tuple[int, int, int, int]:
    with db() as s:
        cp = {c.name: c.id for c in s.scalars(select(Counterparty))}
        inv = {i.number: i.id for i in s.scalars(select(Invoice))}
    return cp["Verde Green Coffee Imports"], inv["VGC-5513"], cp["QuickShip Logistics"], inv["QS-2291"]


def _propose_verde(client: TestClient, headers: dict, db: sessionmaker, key: str = "http-pay-verde") -> dict:
    verde, vgc, _, _ = _ids(db)
    r = client.post("/actions", headers=headers, json={
        "tool": "schedule_payment", "idempotency_key": key,
        "params": {"payee_counterparty_id": verde, "invoice_id": vgc, "amount": 219_600, "date": "2026-10-08"}})
    assert r.status_code == 201, r.text
    return r.json()


def test_login_and_failed_login_audited(client: TestClient, db: sessionmaker) -> None:
    r = client.post("/auth/login", json={"email": "Owner@EmberOak.demo", "password": DEMO_PASSWORD})
    assert r.status_code == 200 and r.json()["role"] == "owner"
    for email in ("owner@emberoak.demo", "nobody@emberoak.demo"):
        assert client.post("/auth/login", json={"email": email, "password": "wrong"}).status_code == 401
    assert _events(db) == ["login_succeeded", "login_failed", "login_failed"]
    with db() as s:
        payload = s.scalar(select(AuditEvent.payload).where(AuditEvent.event_type == "login_failed"))
    assert set(payload) == {"email_key"} and len(payload["email_key"]) == 64  # keyed HMAC, no email


def test_token_required_and_validated(client: TestClient) -> None:
    assert client.get("/actions").status_code == 401
    assert client.get("/actions", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    secret = get_settings().jwt_secret
    past = datetime.now(timezone.utc) - timedelta(hours=9)
    expired = jwt.encode({"sub": "1", "iat": int(past.timestamp()), "exp": int((past + timedelta(hours=8)).timestamp())},
                         secret, algorithm="HS256")
    assert client.get("/actions", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    forged = jwt.encode({"sub": "1", "iat": 0, "exp": 4_102_444_800}, "x" * 40, algorithm="HS256")
    assert client.get("/actions", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    none_alg = jwt.encode({"sub": "1", "iat": 0, "exp": 4_102_444_800}, None, algorithm="none")
    assert client.get("/actions", headers={"Authorization": f"Bearer {none_alg}"}).status_code == 401


def test_owner_proposes_lists_and_approves(client: TestClient, db: sessionmaker) -> None:
    owner = _login(client, "owner")
    action = _propose_verde(client, owner, db)
    assert action["status"] == "proposed"
    pending = client.get("/actions", params={"status": "proposed"}, headers=_login(client, "viewer")).json()
    assert [a["id"] for a in pending] == [action["id"]]
    r = client.post(f"/actions/{action['id']}/approve", headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "executed"
    again = client.post(f"/actions/{action['id']}/approve", headers=owner).json()  # A4 over HTTP
    assert again["result"] == r.json()["result"]
    with db() as s:
        assert len(list(s.scalars(select(SandboxPayment)))) == 1


def test_a3_viewer_approve_is_403_and_audited(client: TestClient, db: sessionmaker) -> None:
    action = _propose_verde(client, _login(client, "owner"), db)
    r = client.post(f"/actions/{action['id']}/approve", headers=_login(client, "viewer"))
    assert r.status_code == 403
    assert _events(db)[-1] == "approval_forbidden"  # committed despite the error response
    assert client.post(f"/actions/{action['id']}/approve", headers=_login(client, "accountant")).status_code == 403


def test_a1_injected_beneficiary_over_http_is_denied(client: TestClient, db: sessionmaker) -> None:
    _, _, quickship, qs = _ids(db)
    r = client.post("/actions", headers=_login(client, "owner"), json={
        "tool": "schedule_payment", "idempotency_key": "a1-http-forced",
        "params": {"payee_counterparty_id": quickship, "invoice_id": qs, "amount": 465_000, "date": "2026-10-10",
                   "payee_name": "QS Logistics Holdings", "account_number": "000123456789"}})
    assert r.status_code == 201 and r.json()["status"] == "denied"
    assert _events(db)[-1] == "action_denied"


def test_request_body_is_closed(client: TestClient) -> None:
    r = client.post("/actions", headers=_login(client, "owner"),
                    json={"tool": "schedule_payment", "params": {}, "idempotency_key": "closed-1", "approve": True})
    assert r.status_code == 422


def test_unknown_action_is_404(client: TestClient) -> None:
    assert client.post("/actions/99999/approve", headers=_login(client, "owner")).status_code == 404


def test_audit_list_and_verify_detects_tamper(client: TestClient, db: sessionmaker) -> None:
    owner = _login(client, "owner")
    _propose_verde(client, owner, db)
    events = client.get("/audit", headers=_login(client, "viewer")).json()
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert client.get("/audit/verify", headers=owner).json()["ok"] is True
    with db() as s:
        s.connection().execute(text("UPDATE audit_events SET actor = 'user:999' WHERE seq = 2"))
        s.commit()
    body = client.get("/audit/verify", headers=owner).json()
    assert (body["ok"], body["broken_at_seq"]) == (False, 2)


def test_upload_roles_limits_and_dedupe(client: TestClient, db: sessionmaker) -> None:
    viewer, owner = _login(client, "viewer"), _login(client, "owner")
    data = (GOLDEN_DIR / Q3_FILE).read_bytes()
    assert client.post("/upload", headers=viewer, files={"file": (Q3_FILE, data, "text/csv")}).status_code == 403
    assert _events(db)[-1] == "upload_forbidden"
    r = client.post("/upload", headers=owner, files={"file": (Q3_FILE, data, "text/csv")})
    assert r.status_code == 200 and (r.json()["inserted"], r.json()["skipped_duplicates"]) == (0, 158)
    assert _events(db)[-1] == "upload_ingested"
    too_big = b"Date,Description,Amount\n" + b"x" * (2 * 1024 * 1024)
    assert client.post("/upload", headers=owner, files={"file": ("big.csv", too_big, "text/csv")}).status_code == 422
    assert client.post("/upload", headers=owner, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 422
    assert _events(db)[-1] == "upload_rejected"


def test_cors_only_for_configured_origins(client: TestClient) -> None:
    allowed = get_settings().cors_origins.split(",")[0].strip()
    ok = client.options("/actions", headers={"Origin": allowed, "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == allowed
    bad = client.options("/actions", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
