"""Demo reset (pulled forward from Phase 7): owner-only, restores the golden state, never deletes or
rewrites audit events, and the chain still verifies."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.models import Action, AuditEvent, Insight, Invoice, SandboxEmail, Transaction, User
from app.services.action_service import ActionService, actor_for
from app.services.drafts import Tone
from tests.conftest import ChatHarness
from tests.test_api import _login, client, db  # noqa: F401 - fixtures
from tests.test_forecast import CLOSINGS_NULL


def _inv_1042(db: sessionmaker) -> int:
    with db() as s:
        return s.scalar(select(Invoice.id).where(Invoice.number == "INV-1042"))


def _propose_reminder(client: TestClient, db: sessionmaker, key: str) -> dict:  # noqa: F811
    with db() as s:
        owner = s.scalar(select(User).where(User.email == "owner@emberoak.demo"))
        draft = ActionService(s, get_settings().demo_today).record_draft(actor_for(owner), _inv_1042(db), Tone.firm)
        s.commit()
        draft_id = draft.id
    r = client.post("/actions", headers=_login(client, "owner"), json={
        "tool": "send_reminder", "idempotency_key": key, "params": {"invoice_id": _inv_1042(db), "draft_id": draft_id}})
    assert r.status_code == 201, r.text
    return r.json()


def _audit(db: sessionmaker) -> list[tuple[int, str, str]]:
    with db() as s:
        return [(e.seq, e.event_type, e.hash) for e in s.scalars(select(AuditEvent).order_by(AuditEvent.seq))]


def test_reset_after_a_p1_approval_makes_inv_1042_remindable_again(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    owner = _login(client, "owner")
    invoice_id = _inv_1042(db)
    first = _propose_reminder(client, db, "p1-first")
    assert client.post(f"/actions/{first['id']}/approve", headers=owner).json()["status"] == "executed"
    assert _propose_reminder(client, db, "p1-cooldown")["status"] == "denied"  # cooldown: one reminder a week
    before = _audit(db)

    r = client.post("/demo/reset", headers=owner)
    assert r.status_code == 200, r.text
    assert r.json()["removed"]["sandbox_emails"] == 1 and r.json()["removed"]["actions"] >= 3

    # the audit log only grew: every earlier event is still there, unchanged, and the chain verifies
    after = _audit(db)
    assert after[:len(before)] == before
    assert after[len(before)][1] == "demo_reset"
    verify = client.get("/audit/verify", headers=owner).json()
    assert verify["ok"] and verify["checked"] == len(after)

    # golden state: same invoice id, no actions or sandbox rows, the seeded forecast and insights
    assert _inv_1042(db) == invoice_id
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Action)) == 0
        assert s.scalar(select(func.count()).select_from(SandboxEmail)) == 0
        assert {i.type.value for i in s.scalars(select(Insight))} >= {"LATE_PAYER", "CASH_GAP", "PRICE_CREEP", "DUPLICATE_SUBSCRIPTION"}
    forecast = client.get("/forecast", headers=owner).json()  # the same sign-in still works
    assert [w["closing_cents"] for w in forecast["weeks"]] == CLOSINGS_NULL

    # INV-1042 can be reminded again, and the reminder goes out
    again = _propose_reminder(client, db, "p1-after-reset")
    assert again["status"] == "proposed"
    assert client.post(f"/actions/{again['id']}/approve", headers=owner).json()["display"]["sandbox"]["status"] == "sent"


def test_reset_removes_uploaded_and_recategorized_data(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    with db() as s:
        golden = s.scalar(select(func.count()).select_from(Transaction))
        t = s.scalar(select(Transaction).order_by(Transaction.id))
        t_id = t.id
    owner = _login(client, "owner")
    assert client.post(f"/transactions/{t_id}/category", json={"category": "other"}, headers=owner).status_code == 200
    client.post("/demo/reset", headers=owner)
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Transaction)) == golden
        assert s.get(Transaction, t_id).category_source.value != "human"


def test_only_the_owner_can_reset_and_refusals_are_audited(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    for role in ("accountant", "viewer"):
        r = client.post("/demo/reset", headers=_login(client, role))
        assert r.status_code == 403
    assert [e for _, e, _ in _audit(db)].count("demo_reset_forbidden") == 2
    assert "demo_reset" not in [e for _, e, _ in _audit(db)]


def test_conversations_from_before_the_reset_are_gone(chat: ChatHarness) -> None:
    owner = chat.login("owner")
    events = chat.chat(owner, "Hi")
    conversation_id = events[0][1]["conversation_id"]
    assert chat.client.post("/demo/reset", headers=owner).status_code == 200
    gone = chat.chat(owner, "Still there?", conversation_id=conversation_id, expect=404)
    assert gone[0][1]["detail"] == "conversation not found"
    assert chat.chat(owner, "Hi again")[-1][0] == "done"  # a new conversation works
