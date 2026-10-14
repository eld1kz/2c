"""Agent tool registry: tiers, schemas, role filtering, and what each tool may and may not do."""

import json
from typing import Any

import pytest
from sqlalchemy import func, select

from app.agent.tools import TOOLS, AgentMemory, ToolContext, ToolOutcome, dispatch, tools_for
from app.config import DEFAULT_DEMO_TODAY
from app.db.models import (
    Action,
    AuditEvent,
    SandboxEmail,
    SandboxLoanApplication,
    SandboxPayment,
    Tier,
)
from app.engine.forecast import project
from app.engine.snapshot import load_snapshot
from app.policy.tiers import TOOL_TIERS
from app.services.action_service import Forbidden
from tests.conftest import Demo

READ = ["get_cash_position", "get_ledger", "get_forecast", "get_insights", "explain_record"]
SUGGEST = ["run_what_if", "rank_financing", "draft_reminder", "draft_terms_request", "draft_cfo_memo"]


def _ctx(demo: Demo, role: str = "owner") -> ToolContext:
    return ToolContext(demo.session, demo.users[role], demo.business, DEFAULT_DEMO_TODAY, demo.service,
                       AgentMemory("test-conversation"))


def _call(ctx: ToolContext, name: str, **tool_input: Any) -> tuple[dict, ToolOutcome]:
    out = dispatch(ctx, name, tool_input)
    return json.loads(out.content), out


def _sandbox_rows(demo: Demo) -> int:
    return sum(demo.session.scalar(select(func.count()).select_from(m))
               for m in (SandboxPayment, SandboxEmail, SandboxLoanApplication))


def test_registry_matches_the_tier_table() -> None:
    assert set(TOOLS) == set(TOOL_TIERS) and len(TOOLS) == 13
    assert TOOLS["draft_terms_request"].tier == Tier.SUGGEST
    assert [n for n, s in TOOLS.items() if s.tier == Tier.READ] == READ
    assert [n for n, s in TOOLS.items() if s.tier == Tier.SUGGEST] == SUGGEST
    assert all((s.handler is None) == (s.tier == Tier.EXECUTE) for s in TOOLS.values())


def test_tools_offered_follow_the_role(demo: Demo) -> None:
    assert [s.name for s in tools_for(demo.users["viewer"])] == READ
    assert [s.name for s in tools_for(demo.users["accountant"])] == [*READ, *SUGGEST, "send_reminder"]
    assert [s.name for s in tools_for(demo.users["owner"])] == list(TOOLS)


def test_schemas_are_closed_and_payments_carry_no_payee_details() -> None:
    for spec in TOOLS.values():
        schema = spec.definition()["input_schema"]
        assert schema["additionalProperties"] is False and "$defs" not in json.dumps(schema), spec.name
    props = TOOLS["schedule_payment"].definition()["input_schema"]["properties"]
    assert set(props) == {"payee_counterparty_id", "invoice_id", "amount", "date", "rationale", "evidence_ids"}


def _execute_inputs(demo: Demo, ctx: ToolContext) -> dict[str, dict]:
    draft, _ = _call(ctx, "draft_reminder", invoice_id=demo.invoices["INV-1042"].id, tone="firm")
    return {
        "send_reminder": {"invoice_id": demo.invoices["INV-1042"].id, "draft_id": draft["data"]["draft_id"]},
        "schedule_payment": {"payee_counterparty_id": demo.counterparties["Verde Green Coffee Imports"].id,
                             "invoice_id": demo.invoices["VGC-5513"].id, "amount": 219_600, "date": "2026-10-08"},
        "submit_loan_application": {"option_id": "overdraft", "amount": 100_000},
    }


@pytest.mark.parametrize("tool", ["send_reminder", "schedule_payment", "submit_loan_application"])
def test_execute_tools_only_create_proposed_actions(demo: Demo, tool: str) -> None:
    ctx = _ctx(demo)
    inputs = _execute_inputs(demo, ctx)[tool]
    result, out = _call(ctx, tool, **inputs, rationale="test")
    assert result["data"]["status"] == "proposed" and out.action["status"] == "proposed"
    action = demo.session.get(Action, result["data"]["action_id"])
    assert (action.status, action.proposed_by, action.tier, action.decided_by) == ("proposed", "agent", "EXECUTE", None)
    assert _sandbox_rows(demo) == 0
    again, _ = _call(ctx, tool, **inputs)
    assert again["data"]["action_id"] == action.id  # same conversation + params → same proposal


def test_viewer_proposal_is_denied_by_the_gate(demo: Demo) -> None:
    ctx = _ctx(demo, "viewer")
    inputs = _execute_inputs(demo, _ctx(demo))["schedule_payment"]
    result, _ = _call(ctx, "schedule_payment", **inputs)
    assert result["data"]["status"] == "denied" and "may not use" in result["data"]["reason"]
    blocked, out = _call(ctx, "run_what_if", scenarios=[{"type": "one_off", "amount_cents": -1, "on": "2026-10-02"}])
    assert out.is_error and "not available to the viewer role" in blocked["error"]


def test_read_tools_return_engine_numbers(demo: Demo) -> None:
    ctx = _ctx(demo)
    base = project(load_snapshot(demo.session, demo.business.id, DEFAULT_DEMO_TODAY))
    forecast, _ = _call(ctx, "get_forecast")
    assert [w["closing_cents"] for w in forecast["data"]["weeks"]] == [w.closing for w in base.weeks]
    assert forecast["data"]["gap"]["amount_cents"] == base.gap().amount
    assert "lines" in forecast["data"]["weeks"][5] and forecast["data"]["weeks"][5]["closing_display"] == "−$2,087.67"
    cash, _ = _call(ctx, "get_cash_position")
    assert cash["data"]["cash_cents"] == base.weeks[0].opening


def test_ledger_rows_resolve_and_hide_notes(demo: Demo) -> None:
    ctx = _ctx(demo)
    rows = _call(ctx, "get_ledger", record="invoices", direction="payable", status="open")[0]["data"]["rows"]
    assert {r["number"] for r in rows} == {"VGC-5513", "QS-2291"}
    assert all("notes" not in r for r in rows) and all(r["has_notes"] is not None for r in rows)
    for r in rows:
        detail, out = _call(ctx, "explain_record", ref=r["ref"])
        assert not out.is_error and detail["data"]["number"] == r["number"]
    txs = _call(ctx, "get_ledger", record="transactions", limit=3)[0]["data"]["rows"]
    assert len(txs) == 3 and all("untrusted_text" in t["description"] for t in txs)


def test_draft_terms_request(demo: Demo) -> None:
    ctx = _ctx(demo)
    verde = demo.counterparties["Verde Green Coffee Imports"].id
    result, _ = _call(ctx, "draft_terms_request", counterparty_id=verde, extension_days=30)
    draft = result["data"]
    assert (draft["tool"], draft["tier"], draft["status"]) == ("draft_terms_request", "SUGGEST", "executed")
    assert "net 14 to net 44" in draft["result"]["body"] and "all 12 of our recent invoices" in draft["result"]["body"]
    assert "Draft only" in draft["note"] and _sandbox_rows(demo) == 0

    customer, out = _call(ctx, "draft_terms_request", counterparty_id=demo.counterparties["Harbor Lane Café"].id,
                          extension_days=30)
    assert out.is_error and "not found" in customer["error"]
    with pytest.raises(Forbidden):
        demo.service.record_terms_draft(demo.actor("viewer"), verde, 30)
    assert demo.session.scalar(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1)).event_type == "draft_denied"


def test_every_call_is_audited(demo: Demo) -> None:
    ctx = _ctx(demo)
    _call(ctx, "get_insights")
    _call(ctx, "explain_record", ref="invoice:999999")
    events = list(demo.session.scalars(select(AuditEvent).where(AuditEvent.event_type == "agent_tool_called")))
    assert [(e.payload["tool"], e.payload["ok"]) for e in events] == [("get_insights", True), ("explain_record", False)]
    assert all(e.actor == f"agent:user:{demo.users['owner'].id}" for e in events)
