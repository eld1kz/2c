"""Phase 9: an approval card shows the engine's 13-week cash effect of approving the action."""

from datetime import date

from sqlalchemy import func, select

from app.db.models import Action, AuditEvent
from app.engine.forecast import project
from app.engine.snapshot import load_snapshot
from app.engine.whatif import run_what_if
from app.services import action_impact, today
from tests.conftest import ChatHarness, Demo

TODAY = date(2026, 10, 1)


def _base(demo: Demo):
    return project(load_snapshot(demo.session, demo.business.id, TODAY))


def _reminder(demo: Demo) -> Action:
    inv = demo.invoices["INV-1042"]
    draft = demo.service.record_draft(demo.actor("owner"), inv.id, "firm")
    return demo.service.propose(demo.actor("owner"), "send_reminder", {"invoice_id": inv.id, "draft_id": draft.id},
                                idempotency_key="impact-reminder")


def test_reminder_impact_lifts_every_week_by_the_invoice(demo: Demo) -> None:
    base = _base(demo)
    impact = action_impact.impact(demo.session, _reminder(demo), TODAY)
    assert impact is not None
    assert impact["closing_delta"] == 480_000
    assert impact["lowest_before"] == min(w.closing for w in base.weeks)
    assert impact["lowest_after"] == impact["lowest_before"] + 480_000
    assert impact["weeks_below_before"] == sum(w.below_buffer for w in base.weeks)
    assert impact["weeks_below_after"] <= impact["weeks_below_before"]
    assert impact["min_cash_buffer"] == base.min_cash_buffer


def test_reminder_impact_matches_todays_chart_after_sending(demo: Demo) -> None:
    """The preview is the same what-if Today applies once the reminder is sent."""
    impact = action_impact.impact(demo.session, _reminder(demo), TODAY)
    reminder, scenario = next((d, s) for d, s in today.fixes(demo.session, demo.business.id, TODAY)
                              if d.kind == "reminder")
    assert reminder.target == {"invoice_id": demo.invoices["INV-1042"].id}
    lifted = run_what_if(_base(demo), [scenario]).scenario
    assert impact["lowest_after"] == min(w.closing for w in lifted.weeks)


def test_terms_request_impact_shrinks_the_gap(demo: Demo) -> None:
    verde = demo.counterparties["Verde Green Coffee Imports"]
    draft = demo.service.record_terms_draft(demo.actor("owner"), verde.id, 30)
    action = demo.service.propose(demo.actor("owner"), "send_terms_request",
                                  {"counterparty_id": verde.id, "draft_id": draft.id}, idempotency_key="impact-terms")
    impact = action_impact.impact(demo.session, action, TODAY)
    assert impact is not None and impact["lowest_after"] > impact["lowest_before"]
    assert impact["weeks_below_after"] < impact["weeks_below_before"]


def test_price_request_has_no_modelled_impact(demo: Demo) -> None:
    verde = demo.counterparties["Verde Green Coffee Imports"]
    draft = demo.service.record_price_draft(demo.actor("owner"), verde.id)
    action = demo.service.propose(demo.actor("owner"), "send_price_request",
                                  {"counterparty_id": verde.id, "draft_id": draft.id}, idempotency_key="impact-price")
    assert action_impact.impact(demo.session, action, TODAY) is None


def test_decided_actions_have_no_preview(demo: Demo) -> None:
    action = demo.service.approve(demo.users["owner"], _reminder(demo).id)
    assert action.status == "executed" and action_impact.impact(demo.session, action, TODAY) is None


def test_actions_api_carries_the_impact_and_writes_nothing(chat: ChatHarness) -> None:
    owner = chat.login("owner")
    insight = next(d for d in chat.client.get("/today", headers=owner).json()["decisions"] if d["kind"] == "reminder")
    insight_id = insight["insight"]["ref"].removeprefix("insight:")
    chat.client.post(f"/today/decisions/{insight_id}/prepare", headers=owner).raise_for_status()
    with chat.factory() as s:
        before = s.scalar(select(func.count()).select_from(AuditEvent))
    body = chat.client.get("/actions?status=proposed", headers=owner).json()
    with chat.factory() as s:
        assert s.scalar(select(func.count()).select_from(AuditEvent)) == before
    reminder = next(a for a in body if a["tool"] == "send_reminder")
    assert reminder["display"]["impact"]["closing_delta"] == 480_000
    assert chat.model.requests == []
