"""Phase 6c: the Today home screen — decisions, one-tap prepared actions, safe to spend, spending."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Action,
    AuditEvent,
    ForecastLineKind,
    Invoice,
    InvoiceDirection,
    InvoiceStatus,
    SandboxEmail,
)
from app.engine import statements as st
from app.engine.forecast import CERTAIN_BP, Forecast, Line, build, project
from app.engine.snapshot import load_snapshot
from app.engine.today import outlook, safe_to_spend, spending
from app.engine.whatif import run_what_if
from app.services import today
from app.services.action_service import Forbidden
from app.services.demo_reset import reset_demo
from tests.conftest import ChatHarness, Demo

TODAY = date(2026, 10, 1)


def _decisions(demo: Demo) -> list[today.Decision]:
    return today.decisions(demo.session, demo.business.id, TODAY)


def _decision(demo: Demo, kind: str) -> today.Decision:
    return next(d for d in _decisions(demo) if d.kind == kind)


def _prepare(demo: Demo, kind: str, role: str = "owner") -> Action:
    return today.prepare(demo.session, demo.service, demo.users[role], _decision(demo, kind).insight.id, TODAY)


def _rows(session: Session) -> dict[str, int]:
    return {m.__tablename__: session.scalar(select(func.count()).select_from(m))
            for m in (Action, AuditEvent, SandboxEmail)}


def test_top_three_decisions_by_impact(demo: Demo) -> None:
    ds = _decisions(demo)
    assert [(d.insight.type.value, d.kind) for d in ds] == [
        ("PRICE_CREEP", "price_email"), ("CASH_GAP", "terms_request"), ("LATE_PAYER", "reminder")]
    verde, harbor = demo.counterparties["Verde Green Coffee Imports"], demo.invoices["INV-1042"]
    assert ds[0].target == ds[1].target == {"counterparty_id": verde.id}
    assert ds[2].target == {"invoice_id": harbor.id}
    assert ds[2].text == "Harbor Lane Café owes you $4,800.00 and is 45 days late on INV-1042."
    assert "GRN-COL-HUILA by 18%" in ds[0].text and "$9,198.00 a year" in ds[0].text
    assert ds[1].text == "Your cash drops below your cushion from Nov 5, by up to $7,271.99."


def test_safe_to_spend_is_cash_minus_cushion_minus_this_weeks_bills(demo: Demo) -> None:
    snap = load_snapshot(demo.session, demo.business.id, TODAY)
    safe = safe_to_spend(snap, project(snap))
    assert (safe.cash, safe.cushion) == (865_000, 500_000)
    assert sorted(b.amount for b in safe.bills) == [2_999, 6_900, 434_355, 450_000]  # software, rent, payroll
    assert all(b.ref.startswith("recurring_series:") for b in safe.bills)
    assert safe.amount == 865_000 - 500_000 - 894_254 == -529_254
    assert safe.short_by == 529_254


@pytest.mark.parametrize(("due_in", "counted"), [(-5, True), (3, True), (6, True), (7, False), (8, False)])
def test_supplier_bills_due_this_week_count(demo: Demo, due_in: int, counted: bool) -> None:
    verde = demo.counterparties["Verde Green Coffee Imports"]
    bill = Invoice(business_id=demo.business.id, direction=InvoiceDirection.payable, counterparty_id=verde.id,
                   number="T-1", issue_date=TODAY - timedelta(days=20), due_date=TODAY + timedelta(days=due_in),
                   total=12_345, currency="USD", status=InvoiceStatus.open)
    demo.session.add(bill)
    demo.session.flush()
    snap = load_snapshot(demo.session, demo.business.id, TODAY)
    safe = safe_to_spend(snap, project(snap))
    assert (f"invoice:{bill.id}" in {b.ref for b in safe.bills}) is counted
    assert safe.bills_total == 894_254 + (12_345 if counted else 0)


def test_spending_is_last_months_costs_from_the_pnl(demo: Demo) -> None:
    snap = load_snapshot(demo.session, demo.business.id, TODAY)
    pnl = st.profit_and_loss(snap, st.previous_month(TODAY))
    spent = spending(pnl)
    assert spent.total == pnl.total_cogs + pnl.total_operating_expenses == sum(ln.amount for ln in spent.lines)
    assert spent.lines[0].key == "payroll"
    assert [ln.amount for ln in spent.lines] == sorted((ln.amount for ln in spent.lines), reverse=True)


def test_preparing_a_reminder_proposes_it_once(demo: Demo) -> None:
    action = _prepare(demo, "reminder")
    assert (action.tool, action.status.value, action.proposed_by.value) == ("send_reminder", "proposed", "user")
    assert action.params["invoice_id"] == demo.invoices["INV-1042"].id
    draft = demo.session.get(Action, action.params["draft_id"])
    assert draft.params["tone"] == "firm"  # 45 days late
    assert action.rationale.startswith("Harbor Lane Café owes you")
    drafts = demo.session.scalar(select(func.count()).select_from(Action).where(Action.tool == "draft_reminder"))
    assert _prepare(demo, "reminder").id == action.id  # tapping again reuses it
    assert demo.session.scalar(select(func.count()).select_from(Action).where(Action.tool == "draft_reminder")) == drafts
    assert today.pending_for(demo.session, demo.business.id, _decision(demo, "reminder")).id == action.id


def test_cash_gap_prepares_a_terms_request_to_verde(demo: Demo) -> None:
    action = _prepare(demo, "terms_request")
    verde = demo.counterparties["Verde Green Coffee Imports"]
    assert (action.tool, action.status.value, action.params["counterparty_id"]) == ("send_terms_request", "proposed", verde.id)
    assert demo.session.get(Action, action.params["draft_id"]).params["extension_days"] == 30


def test_price_email_is_drafted_from_records_and_sent_to_the_stored_contact(demo: Demo) -> None:
    action = _prepare(demo, "price_email")
    assert (action.tool, action.status.value) == ("send_price_request", "proposed")
    action = demo.service.approve(demo.users["owner"], action.id)
    (email,) = demo.session.scalars(select(SandboxEmail))
    assert action.status.value == "executed" and email.to_address == "ar@verdegreen.example"
    assert email.subject == "Price review: GRN-COL-HUILA"
    draft = demo.session.get(Action, action.params["draft_id"])
    assert f"${draft.result['first_price'] / 100:,.2f}" in email.body and f"${draft.result['last_price'] / 100:,.2f}" in email.body
    assert "18%" in email.body
    notes = [i.notes for i in demo.session.scalars(select(Invoice)) if i.notes]
    assert notes and not any(n[:30] in email.body for n in notes)  # never document text
    sent = today.sent_for(demo.session, demo.business.id, _decision(demo, "price_email"), demo.clock.now)
    assert sent is not None and sent.id == action.id


def test_price_request_gate(demo: Demo) -> None:
    verde, harbor = demo.counterparties["Verde Green Coffee Imports"], demo.counterparties["Harbor Lane Café"]
    owner = demo.actor("owner")
    draft = demo.service.record_price_draft(owner, verde.id)
    ok = {"counterparty_id": verde.id, "draft_id": draft.id}

    def propose(params: dict, key: str, role: str = "owner") -> Action:
        return demo.service.propose(demo.actor(role), "send_price_request", params, idempotency_key=key)

    assert propose(ok | {"counterparty_id": harbor.id}, "p1").result["denied"] == "counterparty is not a supplier of this business"
    terms = demo.service.record_terms_draft(owner, verde.id, 30)
    assert propose(ok | {"draft_id": terms.id}, "p2").result["denied"] == "draft is not a price-request draft for this supplier"
    assert propose(ok, "p3", "accountant").status.value == "denied"  # owner only
    first = propose(ok, "p4")
    assert first.status.value == "proposed"
    demo.service.approve(demo.users["owner"], first.id)
    fresh = demo.service.record_price_draft(owner, verde.id)
    again = propose({"counterparty_id": verde.id, "draft_id": fresh.id}, "p5")
    assert again.status.value == "denied" and "price request to this supplier was sent within 7 days" in again.result["denied"]
    demo.clock.advance(days=8)
    assert propose({"counterparty_id": verde.id, "draft_id": fresh.id}, "p6").result["denied"].startswith("draft is older than")


def test_price_draft_needs_a_price_rise(demo: Demo) -> None:
    from app.services.action_service import NotFound

    with pytest.raises(NotFound):
        demo.service.record_price_draft(demo.actor("owner"), demo.counterparties["QuickShip Logistics"].id)


def test_roles_for_preparing(demo: Demo) -> None:
    before = _rows(demo.session)
    with pytest.raises(Forbidden):
        _prepare(demo, "price_email", "accountant")  # owner-only tool: refused before anything is drafted
    with pytest.raises(Forbidden):
        _prepare(demo, "reminder", "viewer")
    after = _rows(demo.session)
    assert after["actions"] == before["actions"] and after["audit_events"] == before["audit_events"] + 2
    assert _prepare(demo, "reminder", "accountant").status.value == "proposed"  # reminders are allowed


# --- API ----------------------------------------------------------------------------------


def test_today_reads_without_writing_or_calling_the_model(chat: ChatHarness) -> None:
    with chat.factory() as s:
        before = _rows(s)
    for role in ("owner", "accountant", "viewer"):
        body = chat.client.get("/today", headers=chat.login(role)).json()
        assert [d["kind"] for d in body["decisions"]] == ["price_email", "terms_request", "reminder"]
    with chat.factory() as s:
        after = _rows(s)
    assert after["actions"] == before["actions"] and after["sandbox_emails"] == before["sandbox_emails"]
    assert after["audit_events"] - before["audit_events"] == 3  # the three sign-ins only
    assert chat.model.requests == []
    safe = body["safe_to_spend"]
    assert (safe["amount_cents"], safe["short_by_cents"], safe["bills_total_cents"]) == (-529_254, 529_254, 894_254)
    assert all(b["source"]["label"] for b in safe["bills"]) and safe["accounts"][0]["label"]
    assert body["spending"]["period"]["label"] == "September 2026" and body["spending"]["total_cents"] == 3_459_989
    assert all(e["label"] for d in body["decisions"] for e in d["evidence"])


def test_prepare_over_http(chat: ChatHarness) -> None:
    owner = chat.login("owner")
    decisions = chat.client.get("/today", headers=owner).json()["decisions"]
    reminder = next(d for d in decisions if d["kind"] == "reminder")
    insight_id = int(reminder["insight"]["ref"].split(":")[1])
    r = chat.client.post(f"/today/decisions/{insight_id}/prepare", headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "proposed" and r.json()["display"]["email"]["subject"]
    again = chat.client.get("/today", headers=owner).json()["decisions"]
    assert next(d for d in again if d["kind"] == "reminder")["pending_action_id"] == r.json()["id"]
    assert chat.client.post(f"/today/decisions/{insight_id}/prepare", headers=chat.login("viewer")).status_code == 403
    assert chat.client.post("/today/decisions/999999/prepare", headers=owner).status_code == 404
    assert "today_prepare_forbidden" in chat.events() and "today_prepare_refused" in chat.events()
    assert chat.model.requests == []


# --- Watch your future fix itself (the chart) -------------------------------------------------


def _future(demo: Demo) -> today.Future:
    return today.future(demo.session, demo.business.id, TODAY, demo.clock.now)


def _approve(demo: Demo, kind: str) -> None:
    demo.service.approve(demo.users["owner"], _prepare(demo, kind).id)


def _closings(f: Forecast | None) -> list[int]:
    assert f is not None
    return [w.closing for w in f.weeks]


def test_the_chart_starts_on_the_base_forecast(demo: Demo) -> None:
    f = _future(demo)
    base = project(load_snapshot(demo.session, demo.business.id, TODAY))
    assert _closings(f.applied) == _closings(base) and f.applied_fixes == ()
    assert {d.kind for d in f.pending_fixes} == {"reminder", "terms_request"}  # the price email has no figure
    now, then = outlook(f.applied), outlook(f.pending)
    assert (now.headline, now.first_below) == ("Cash stays above your cushion until Nov 5.", date(2026, 11, 5))
    assert now.detail == "Lowest week: Nov 26, $7,271.99 below your cushion."
    assert then.headline == "Cash stays above your cushion for all 13 weeks."
    # the ghost line is the same world as the "if Today's fixes succeed" verdict
    assert _closings(f.pending) == _closings(run_what_if(base, [s for _, s in today.fixes(
        demo.session, demo.business.id, TODAY)]).scenario)


def test_each_approved_fix_lifts_the_curve_and_a_reset_restores_it(demo: Demo) -> None:
    base = _closings(_future(demo).applied)
    _approve(demo, "reminder")
    one = _future(demo)
    assert [d.kind for d in one.applied_fixes] == ["reminder"] and [d.kind for d in one.pending_fixes] == ["terms_request"]
    assert [a - b for a, b in zip(_closings(one.applied), base)] == [480_000] * 13  # INV-1042 collected now
    assert outlook(one.applied).headline == "Cash stays above your cushion until Nov 5."  # still short, by less
    assert outlook(one.applied).detail == "Lowest week: Nov 26, $2,471.99 below your cushion."
    _approve(demo, "terms_request")
    both = _future(demo)
    assert both.pending is None and both.pending_fixes == ()
    assert not any(w.below_buffer for w in both.applied.weeks)
    assert outlook(both.applied).headline == "Cash stays above your cushion for all 13 weeks."
    reset_demo(demo.session, demo.business.id, "cli:demo_reset", TODAY)
    after = _future(demo)  # the actions are gone, so the chart is the (reloaded) base forecast again
    assert after.applied_fixes == () and len(after.pending_fixes) == 2
    assert _closings(after.applied) == _closings(project(load_snapshot(demo.session, demo.business.id, TODAY)))


def test_outlook_wording() -> None:
    def forecast(*closings: int) -> Forecast:
        lines = [Line(TODAY, ForecastLineKind.opening, closings[0], CERTAIN_BP, ("account:1",))]
        lines += [Line(TODAY + timedelta(days=7 * i), ForecastLineKind.baseline_in, c - p, CERTAIN_BP, ("transaction:1",))
                  for i, (p, c) in enumerate(zip(closings, closings[1:]), start=1)]
        return build(TODAY, "USD", 500_000, lines, {})

    assert outlook(forecast(*[600_000] * 13)).detail == "Lowest week: Oct 1, $1,000.00 above your cushion."
    assert outlook(forecast(400_000, *[600_000] * 12)).headline == "Cash is below your cushion this week."
    later = outlook(forecast(*[600_000] * 9, 450_000, *[600_000] * 3))
    assert (later.headline, later.lowest_week) == ("Cash stays above your cushion until Dec 3.", 10)


def test_today_sends_the_chart_to_every_role(chat: ChatHarness) -> None:
    for role in ("owner", "viewer"):
        f = chat.client.get("/today", headers=chat.login(role)).json()["future"]
        assert len(f["weeks"]) == 13 and f["cushion_cents"] == 500_000 and f["applied"] == []
        assert f["headline"] == "Cash stays above your cushion until Nov 5."
        assert f["pending_headline"] == "Cash stays above your cushion for all 13 weeks."
        assert [w["below_cushion"] for w in f["weeks"]][5:10] == [True] * 5
        assert all(w["pending_closing_cents"] >= 500_000 for w in f["weeks"])
        assert {x["kind"] for x in f["pending"]} == {"reminder", "terms_request"}
