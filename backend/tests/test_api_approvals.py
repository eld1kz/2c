"""Approval cards (Phase 5): what GET /actions shows for each action, before and after the decision."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Counterparty, Invoice, User
from app.services.action_service import ActionService, actor_for
from app.services.drafts import Tone
from tests.test_api import _login, client, db  # noqa: F401 - fixtures


def _ids(db) -> dict[str, int]:  # noqa: ANN001
    with db() as s:
        out = {i.number: i.id for i in s.scalars(select(Invoice))}
        out |= {c.name: c.id for c in s.scalars(select(Counterparty))}
    return out


def _propose_reminder(client: TestClient, db) -> dict:  # noqa: F811, ANN001
    ids = _ids(db)
    with db() as s:
        owner = s.scalar(select(User).where(User.email == "owner@emberoak.demo"))
        draft = ActionService(s, get_settings().demo_today).record_draft(actor_for(owner), ids["INV-1042"], Tone.firm)
        s.commit()
        draft_id = draft.id
    r = client.post("/actions", headers=_login(client, "owner"), json={
        "tool": "send_reminder", "idempotency_key": "card-reminder-1042",
        "params": {"invoice_id": ids["INV-1042"], "draft_id": draft_id},
        "rationale": "45 days overdue", "evidence_ids": [f"invoice:{ids['INV-1042']}"]})
    assert r.status_code == 201, r.text
    return r.json()


def test_reminder_card_shows_who_what_and_the_draft(client: TestClient, db) -> None:  # noqa: F811, ANN001
    _propose_reminder(client, db)
    [card] = client.get("/actions", params={"status": "proposed"}, headers=_login(client, "viewer")).json()
    shown = card["display"]
    assert shown["title"] == "Send a payment reminder to Harbor Lane Café"
    assert shown["invoice"]["label"] == "INV-1042" and shown["counterparty"]["label"] == "Harbor Lane Café"
    assert shown["amount_cents"] == 480_000 and shown["invoice_outstanding_cents"] == 480_000
    assert shown["days_past_due"] == 45
    assert shown["email"]["subject"] and "INV-1042" in shown["email"]["body"]
    assert shown["evidence"] == [{"ref": shown["invoice"]["ref"], "label": "INV-1042"}]
    assert shown["sandbox"] is None
    assert "@" not in json.dumps(shown)  # contact emails are never shown


def test_after_approval_the_card_shows_the_sandbox_email(client: TestClient, db) -> None:  # noqa: F811, ANN001
    action = _propose_reminder(client, db)
    r = client.post(f"/actions/{action['id']}/approve", headers=_login(client, "owner"))
    assert r.status_code == 200, r.text
    sandbox = r.json()["display"]["sandbox"]
    assert sandbox["kind"] == "email" and sandbox["status"] == "sent"
    assert "Harbor Lane Café" in sandbox["summary"] and "@" not in json.dumps(sandbox)


def test_denied_payment_card_shows_the_policy_reason(client: TestClient, db) -> None:  # noqa: F811, ANN001
    ids = _ids(db)
    r = client.post("/actions", headers=_login(client, "owner"), json={
        "tool": "schedule_payment", "idempotency_key": "card-a1-quickship",
        "params": {"payee_counterparty_id": ids["QuickShip Logistics"], "invoice_id": ids["QS-2291"],
                   "amount": 465_000, "date": "2026-10-08"}})
    assert r.status_code == 201 and r.json()["status"] == "denied"
    cards = client.get("/actions", params={"status": "denied"}, headers=_login(client, "owner")).json()
    shown = cards[0]["display"]
    assert shown["title"] == "Pay QuickShip Logistics"
    assert shown["amount_cents"] == 465_000 and shown["invoice_outstanding_cents"] == 46_500
    assert shown["denied_reason"]


def test_viewer_sees_the_card_but_cannot_approve(client: TestClient, db) -> None:  # noqa: F811, ANN001
    action = _propose_reminder(client, db)
    r = client.post(f"/actions/{action['id']}/approve", headers=_login(client, "viewer"))
    assert r.status_code == 403
    [card] = client.get("/actions", params={"status": "proposed"}, headers=_login(client, "viewer")).json()
    assert card["id"] == action["id"]
