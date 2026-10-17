"""Agent tools (SPEC §7): schemas, tier (from policy.tiers, the single source) and dispatch.

READ and SUGGEST tools call the engine and read-only services. Drafts go through ActionService. EXECUTE
tools only *propose*: their parameters go to ActionService.propose unchanged, so the policy gate
validates them, and anything unexpected (a beneficiary name, an account number) becomes an audited
`denied` Action instead of being dropped quietly (T1, T2). No tool can approve or execute.

Tool results are compact JSON. Money is ready-made `*_display` text, so the model copies figures and
never formats or computes them (T7); integer `*_cents` is kept only by tools whose amounts the
model may need for an EXECUTE parameter (invoices, financing, proposals). Long source lists are cut
to MAX_SOURCE_IDS with a count; every ref needed for a citation is kept. Third-party text is wrapped as
{"untrusted_text": ...} (T1), and every string is PII-masked before it leaves the server (T8).
"""

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.agent.citations import EvidenceIndex
from app.agent.pii import PiiVault, strip_token_marks
from app.audit import log as audit
from app.auth.rbac import can_propose
from app.db.models import (
    Business,
    Category,
    InsightStatus,
    InsightType,
    InvoiceDirection,
    InvoiceStatus,
    Tier,
    User,
)
from app.engine.financing import rank_financing
from app.engine.forecast import CERTAIN_BP, Forecast, Gap, project
from app.engine.insights.base import money
from app.engine.memo import memo_facts
from app.engine.position import cash_position
from app.engine.snapshot import Snapshot, load_snapshot
from app.engine.whatif import (
    AddRecurring,
    CollectReceivable,
    DelayReceivable,
    OneOff,
    ScenarioError,
    run_what_if,
)
from app.policy.tiers import (
    TOOL_TIERS,
    SchedulePaymentParams,
    SendReminderParams,
    SendTermsRequestParams,
    SubmitLoanApplicationParams,
)
from app.services import ledger
from app.services.action_service import ActionError, ActionService, actor_for
from app.services.drafts import Tone
from app.services.ledger import UntrustedText
from app.services.scenarios import MAX_SCENARIOS, ScenarioIn, check_targets, to_scenarios

MAX_UNTRUSTED_CHARS = 600
MAX_RATIONALE_CHARS = 500
MAX_EVIDENCE_IDS = 20
MAX_PROPOSALS_PER_TURN = 3
MAX_SOURCE_IDS = 5
MAX_INSIGHT_EVIDENCE = 6
LEDGER_DROP = ("currency", "category_source")  # same for every row, or not useful to the model
INSTRUCTION_LIKE = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above)|system (?:notice|prompt|message)|\bai assistant\b|"
    r"pre-?approved|do not ask|chang(?:e|ed) (?:of )?bank|new (?:bank|account)|beneficiary|wire|"
    r"schedule a payment|transfer (?:the|a) (?:payment|funds)",
    re.IGNORECASE)
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
NOT_SENT = "Draft only: nothing has been sent and no tool sends it on its own."
REMINDER_NEXT = "Use send_reminder with this draft_id to propose sending it; a human approves before it goes out."
TERMS_NEXT = ("Use send_terms_request with this draft_id to propose emailing it to the supplier's stored contact; "
              "an owner approves before it goes out. Do not tell the user to send it themselves.")
AWAITING = "Awaiting human approval in the approvals inbox. You cannot approve it."
DENIED = "The policy gate denied this proposal. Tell the user the reason; do not retry with changed figures."


# --- per-conversation memory ---------------------------------------------------------------


@dataclass
class AgentMemory:
    """What the server remembers about one conversation (never sent by the client)."""

    conversation_id: str
    vault: PiiVault = field(default_factory=PiiVault)
    index: EvidenceIndex = field(default_factory=EvidenceIndex)
    whatif_runs: int = 0


@dataclass
class ToolContext:
    session: Session
    user: User
    business: Business
    today: date  # DEMO_TODAY
    service: ActionService
    memory: AgentMemory
    proposals: int = 0  # EXECUTE proposals made in this turn
    allowed: frozenset[str] | None = None  # the only tools this turn may use (None: every tool the role has)

    def snapshot(self) -> Snapshot:
        return load_snapshot(self.session, self.business.id, self.today)


@dataclass(frozen=True)
class ToolOutcome:
    content: str  # JSON text for the tool_result block
    is_error: bool
    tier: Tier | None
    action: dict[str, Any] | None = None  # {action_id, tool, status} for EXECUTE proposals
    scenarios: list[dict[str, Any]] | None = None  # validated what-if inputs (run_what_if / rank_financing), for the UI


class ToolInputError(ValueError):
    pass


# --- input schemas -------------------------------------------------------------------------


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoInput(_In):
    pass


class LedgerIn(_In):
    record: Literal["transactions", "invoices"]
    date_from: date | None = None
    date_to: date | None = None
    category: Category | None = Field(None, description="transactions only")
    counterparty_id: int | None = None
    direction: InvoiceDirection | None = Field(None, description="invoices only")
    status: InvoiceStatus | None = Field(None, description="invoices only")
    needs_review: bool | None = Field(None, description="transactions only")
    limit: int = Field(10, ge=1, le=ledger.MAX_ROWS)


class ForecastIn(_In):
    week: int | None = Field(None, ge=1, le=13, description="show this week's lines (default: the gap weeks)")


class InsightsIn(_In):
    type: InsightType | None = None
    status: InsightStatus = InsightStatus.open


class ExplainIn(_In):
    ref: str = Field(pattern=rf"^({'|'.join(ledger.REF_TYPES)}):\d+$", description='e.g. "invoice:30"')


class WhatIfIn(_In):
    scenarios: list[ScenarioIn] = Field(min_length=1, max_length=MAX_SCENARIOS)


class FinancingIn(_In):
    scenarios: list[ScenarioIn] = Field(default_factory=list, max_length=MAX_SCENARIOS,
                                        description="rank the gap left after these what-if scenarios (default: none)")


class DraftReminderIn(_In):
    invoice_id: int
    tone: Tone


class TermsRequestIn(_In):
    counterparty_id: int
    extension_days: int = Field(ge=7, le=60)


class _Proposal(BaseModel):
    rationale: str = Field("", max_length=MAX_RATIONALE_CHARS, description="why, for the human approver")
    evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_IDS,
                                    description="refs from tool results that support this action")


class SendReminderIn(SendReminderParams, _Proposal):
    pass


class SendTermsRequestIn(SendTermsRequestParams, _Proposal):
    pass


class SchedulePaymentIn(SchedulePaymentParams, _Proposal):
    pass


class SubmitLoanApplicationIn(SubmitLoanApplicationParams, _Proposal):
    pass


# --- result helpers ------------------------------------------------------------------------


def strip_invisible(text: str) -> str:
    """Remove zero-width and bidi control characters (Unicode category Cf) so hidden text cannot
    split words past the checks or reorder what the model reads."""
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def untrusted(text: str, source: str) -> dict[str, Any]:
    """Wrap third-party text as data: cleaned, cut short, unable to forge citations or PII tokens."""
    clean = CONTROL.sub(" ", strip_token_marks(strip_invisible(text))).replace("[[", "[ [").replace("]]", "] ]")
    clean = " ".join(clean.split())[:MAX_UNTRUSTED_CHARS]
    return {"untrusted_text": clean, "source": source, "instruction_like": bool(INSTRUCTION_LIKE.search(clean))}


def present(value: Any, currency: str, cents: bool = False) -> Any:
    """Wrap UntrustedText and turn every `*_cents` value into `*_display` money text (keeping the
    integer too when `cents`)."""
    if isinstance(value, UntrustedText):
        return untrusted(value.text, value.source)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, v in value.items():
            if key.endswith("_cents") and isinstance(v, (int, list)):
                if cents:
                    out[key] = v
                display = key[: -len("_cents")] + "_display"
                out[display] = money(v, currency) if isinstance(v, int) else [money(x, currency) for x in v]
            else:
                out[key] = present(v, currency, cents)
        return out
    if isinstance(value, (list, tuple)):
        return [present(v, currency, cents) for v in value]
    return value


def sources(ids: tuple[str, ...] | list[str]) -> dict[str, Any]:
    """Source refs, cut to the first MAX_SOURCE_IDS (most specific first) plus how many more."""
    out: dict[str, Any] = {"source_ids": list(ids[:MAX_SOURCE_IDS])}
    if len(ids) > MAX_SOURCE_IDS:
        out["more_sources"] = len(ids) - MAX_SOURCE_IDS
    return out


def _insight(i: Any) -> dict[str, Any]:
    row = ledger.insight_dict(i)
    for key in ("currency", "status", "detected_at"):
        row.pop(key)
    ids = row.pop("evidence_ids")
    row["evidence_ids"] = ids[:MAX_INSIGHT_EVIDENCE]
    if len(ids) > MAX_INSIGHT_EVIDENCE:
        row["more_evidence"] = len(ids) - MAX_INSIGHT_EVIDENCE
    return row


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v is not None and k not in LEDGER_DROP
            and not (k == "needs_review" and v is False)}


def week_label(week: int, start: date) -> str:
    return f"Week {week} ({start:%b} {start.day})"


def _gap(gap: Gap | None) -> dict[str, Any] | None:
    if gap is None:
        return None
    return {"first_week": gap.first_week, "last_week": gap.last_week, "low_week": gap.low_week,
            "amount_cents": gap.amount, "start": gap.start.isoformat(), "low_week_end": gap.low_week_end.isoformat(),
            "days": gap.days}


def _base_gap(forecast: Forecast) -> dict[str, Any] | None:
    """The base forecast's gap, citable through the forecast weeks it spans."""
    gap = _gap(forecast.gap())
    if gap is not None:
        weeks = range(gap["first_week"], gap["last_week"] + 1)
        gap |= {"min_cash_buffer_cents": forecast.min_cash_buffer,
                "evidence_ids": [f"forecast_week:{w}" for w in weeks if forecast.weeks[w - 1].below_buffer]}
    return gap


def _probability(bp: int) -> str:
    return f"{bp * 100 / CERTAIN_BP:g}%"


def _register_weeks(ctx: ToolContext, forecast: Forecast) -> None:
    for w in forecast.weeks:
        ctx.memory.index.add_computed(f"forecast_week:{w.week}", week_label(w.week, w.start))


# --- handlers ------------------------------------------------------------------------------


def _get_cash_position(ctx: ToolContext, _: NoInput) -> dict[str, Any]:
    pos = cash_position(ctx.snapshot())
    return {"as_of": ctx.today.isoformat(), "cash_cents": pos.as_of_cash, "min_cash_buffer_cents": pos.min_cash_buffer,
            "headroom_cents": pos.headroom, "currency": pos.currency,
            "evidence_ids": [f"account:{a}" for a in pos.account_ids]}


def _get_ledger(ctx: ToolContext, p: LedgerIn) -> dict[str, Any]:
    if p.record == "transactions":
        rows = ledger.query_transactions(ctx.session, ctx.business.id, date_from=p.date_from, date_to=p.date_to,
                                         category=p.category, counterparty_id=p.counterparty_id,
                                         needs_review=p.needs_review, limit=p.limit)
    else:
        rows = ledger.query_invoices(ctx.session, ctx.business.id, ctx.today, direction=p.direction, status=p.status,
                                     counterparty_id=p.counterparty_id, date_from=p.date_from, date_to=p.date_to,
                                     limit=p.limit)
    return {"record": p.record, "count": len(rows), "rows": [_compact_row(r) for r in rows]}


def _lines(forecast: Forecast, week: int, snap: Snapshot) -> list[dict[str, Any]]:
    out = []
    for ln in forecast.lines_in(week):
        line: dict[str, Any] = {"date": ln.on.isoformat(), "kind": ln.kind.value, "amount_cents": ln.amount}
        if ln.counterparty_id in snap.counterparties:
            line["counterparty_name"] = snap.counterparties[ln.counterparty_id].name
        if ln.probability_bp < CERTAIN_BP:
            line["probability"] = _probability(ln.probability_bp)
        out.append(line | sources(ln.source_ids))
    return out


def _get_forecast(ctx: ToolContext, p: ForecastIn) -> dict[str, Any]:
    snap = ctx.snapshot()
    forecast = project(snap)
    _register_weeks(ctx, forecast)
    gap = forecast.gap()
    focus = {p.week} if p.week else ({gap.first_week, gap.low_week} if gap else set())
    weeks = []
    for w in forecast.weeks:
        row: dict[str, Any] = {"ref": f"forecast_week:{w.week}", "label": week_label(w.week, w.start),
                               "inflows_cents": w.inflows, "outflows_cents": w.outflows, "closing_cents": w.closing,
                               "below_buffer": w.below_buffer}
        if w.week in focus:
            row["lines"] = _lines(forecast, w.week, snap)
        weeks.append(row)
    return {"as_of": forecast.as_of.isoformat(), "opening_cents": forecast.weeks[0].opening,
            "min_cash_buffer_cents": forecast.min_cash_buffer, "gap": _base_gap(forecast), "weeks": weeks,
            "at_risk_receivables": forecast.assumptions.get("at_risk_receivables", []),
            "note": "Lines are listed for the first and lowest weeks under the buffer (or the requested week); "
                    "ask for another week to see its lines."}


def _get_insights(ctx: ToolContext, p: InsightsIn) -> dict[str, Any]:
    rows = ledger.list_insights(ctx.session, ctx.business.id, type_=p.type, status=p.status)
    return {"count": len(rows), "insights": [_insight(i) for i in rows]}


def _explain_record(ctx: ToolContext, p: ExplainIn) -> dict[str, Any]:
    try:
        return ledger.explain(ctx.session, ctx.business.id, p.ref, ctx.today)
    except ledger.RecordNotFound:
        raise ToolInputError(f"{p.ref} not found") from None


def _run_what_if(ctx: ToolContext, p: WhatIfIn) -> dict[str, Any]:
    scenarios = to_scenarios(p.scenarios, ctx.today)
    check_targets(ctx.session, ctx.business.id, ctx.business.base_currency, ctx.today, scenarios)
    base = project(ctx.snapshot())
    result = run_what_if(base, scenarios)
    ctx.memory.whatif_runs += 1
    ref = f"whatif:{ctx.memory.whatif_runs}"
    ctx.memory.index.add_computed(ref, f"What-if {ctx.memory.whatif_runs}")
    _register_weeks(ctx, base)
    # A change that only reflects an amount the model chose is not evidence (see agent/citations.py).
    change = "change_from_supplied_cents" if any(isinstance(s, (OneOff, AddRecurring)) for s in scenarios) \
        else "change_cents"
    weeks = [{"week": b.week, "base_closing_cents": b.closing, "scenario_closing_cents": s.closing, change: d,
              "below_buffer": s.below_buffer}
             for b, s, d in zip(base.weeks, result.scenario.weeks, result.closing_delta)]
    receivables = [ledger.explain(ctx.session, ctx.business.id, f"invoice:{s.invoice_id}", ctx.today)
                   for s in scenarios if isinstance(s, (CollectReceivable, DelayReceivable))]
    return {"ref": ref, "label": f"What-if {ctx.memory.whatif_runs}",
            "supplied_input": {"scenarios": result.scenario.assumptions["scenarios"]},
            "receivables": [{"ref": r["ref"], "number": r["number"], "outstanding_cents": r["outstanding_cents"]}
                            for r in receivables],
            "min_cash_buffer_cents": base.min_cash_buffer,
            "base_gap": _base_gap(base), "scenario_gap": _gap(result.scenario.gap()), "weeks": weeks,
            "note": "A simulation only; nothing in the books was changed."}


def _rank_financing(ctx: ToolContext, p: FinancingIn) -> dict[str, Any]:
    snap = ctx.snapshot()
    forecast = project(snap)
    _register_weeks(ctx, forecast)
    if p.scenarios:
        scenarios = to_scenarios(p.scenarios, ctx.today)
        check_targets(ctx.session, ctx.business.id, ctx.business.base_currency, ctx.today, scenarios)
        forecast = run_what_if(forecast, scenarios).scenario
    gap = forecast.gap()
    based_on = "the forecast after the given what-if scenarios" if p.scenarios else "the base forecast"
    if gap is None:
        return {"based_on": based_on, "gap": None, "options": [], "note": "No week closes below the buffer."}
    ranking = rank_financing(gap, forecast, snap)
    options = []
    for rank, o in enumerate(ranking.options, start=1):
        ref = f"financing:{o.option_id}"
        ctx.memory.index.add_computed(ref, o.name)
        options.append({
            "ref": ref, "label": o.name, "rank": rank, "option_id": o.option_id, "cost_cents": o.cost,
            "max_amount_cents": o.max_amount, "covers_gap": o.covers_gap, "pros": list(o.pros), "cons": list(o.cons),
            "evidence_ids": list(o.evidence_ids),
            **({"by_counterparty": [
                {"counterparty": f"counterparty:{s.counterparty_id}",
                 "counterparty_name": snap.counterparties[s.counterparty_id].name,
                 "amount_cents": s.amount, "covers_gap_alone": s.covers_gap, "evidence_ids": list(s.evidence_ids)}
                for s in o.by_counterparty]} if o.by_counterparty else {}),
        })
    gap_info = _gap(gap) if p.scenarios else _base_gap(forecast)
    gap_info["evidence_ids"] = [*gap_info.get("evidence_ids", []), *(o["ref"] for o in options)]  # ranked for it
    return {"based_on": based_on, "gap": gap_info, "options": options, "disclaimer": ranking.disclaimer}


def _draft_reminder(ctx: ToolContext, p: DraftReminderIn) -> dict[str, Any]:
    draft = ctx.service.record_draft(actor_for(ctx.user, via_agent=True), p.invoice_id, p.tone)
    return {**ledger.action_dict(draft), "draft_id": draft.id, "outstanding_cents": draft.result["outstanding"],
            "note": NOT_SENT, "next_step": REMINDER_NEXT}


def _draft_terms_request(ctx: ToolContext, p: TermsRequestIn) -> dict[str, Any]:
    draft = ctx.service.record_terms_draft(actor_for(ctx.user, via_agent=True), p.counterparty_id, p.extension_days)
    return {**ledger.action_dict(draft), "draft_id": draft.id, "note": NOT_SENT, "next_step": TERMS_NEXT}


def _draft_cfo_memo(ctx: ToolContext, _: NoInput) -> dict[str, Any]:
    snap = ctx.snapshot()
    forecast = project(snap)
    _register_weeks(ctx, forecast)
    facts = memo_facts(snap, forecast, ledger.list_insights(ctx.session, ctx.business.id),
                       ledger.pending_actions(ctx.session, ctx.business.id))
    pos = facts.position
    low = forecast.weeks[facts.lowest_week - 1]
    return {
        "cash": {"as_of": ctx.today.isoformat(), "cash_cents": pos.as_of_cash,
                 "min_cash_buffer_cents": pos.min_cash_buffer, "headroom_cents": pos.headroom,
                 "evidence_ids": [f"account:{a}" for a in pos.account_ids]},
        "gap": _base_gap(forecast),
        "lowest_week": {"ref": f"forecast_week:{low.week}", "label": week_label(low.week, low.start),
                        "closing_cents": facts.lowest_closing},
        "top_insights": [ledger.insight_dict(i) for i in facts.insights],
        "pending_approvals": [{"ref": f"action:{a.id}", "tool": a.tool, "status": a.status.value}
                              for a in facts.pending_actions],
        "note": "Facts for this week's CFO memo. Write it up with citations; it is not stored or sent.",
    }


def _propose(ctx: ToolContext, tool: str, raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    params = {k: v for k, v in raw.items() if k not in ("rationale", "evidence_ids")}
    rationale = raw.get("rationale") if isinstance(raw.get("rationale"), str) else ""
    index = ctx.memory.index
    claimed = raw.get("evidence_ids") if isinstance(raw.get("evidence_ids"), list) else []
    targets = [f"{kind}:{params[key]}" for key, kind in (("invoice_id", "invoice"), ("payee_counterparty_id",
               "counterparty"), ("counterparty_id", "counterparty"), ("draft_id", "action"))
               if isinstance(params.get(key), int)]
    evidence = [e for e in claimed if isinstance(e, str) and (e in index.seen or e in index.computed)]
    evidence = list(dict.fromkeys([*targets, *evidence]))[:MAX_EVIDENCE_IDS]
    digest = hashlib.sha256(json.dumps([ctx.memory.conversation_id, tool, params], sort_keys=True, default=str)
                            .encode()).hexdigest()
    action = ctx.service.propose(actor_for(ctx.user, via_agent=True), tool, params,
                                 idempotency_key=f"agent:{digest[:40]}",
                                 rationale=rationale[:MAX_RATIONALE_CHARS], evidence_ids=tuple(evidence))
    status = action.status.value
    data: dict[str, Any] = {"ref": f"action:{action.id}", "action_id": action.id, "tool": tool, "status": status}
    invoice_id = params.get("invoice_id")
    if isinstance(invoice_id, int) and ledger.record_exists(ctx.session, ctx.business.id, f"invoice:{invoice_id}"):
        inv = ledger.explain(ctx.session, ctx.business.id, f"invoice:{invoice_id}", ctx.today)
        data["invoice"] = {"ref": inv["ref"], "number": inv["number"], "outstanding_cents": inv["outstanding_cents"]}
    if status == "denied":
        data |= {"reason": (action.result or {}).get("denied", ""), "next_step": DENIED}
    elif status == "proposed":
        data["next_step"] = AWAITING
    return data, {"action_id": action.id, "tool": tool, "status": status}


# --- registry ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[ToolContext, Any], dict[str, Any]] | None  # None = EXECUTE (proposal)
    cents: bool = False  # keep integer *_cents next to *_display (amounts the model may need for EXECUTE)

    @property
    def tier(self) -> Tier:
        return TOOL_TIERS[self.name]

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "input_schema": json_schema(self.input_model)}


TOOLS: dict[str, ToolSpec] = {spec.name: spec for spec in (
    ToolSpec("get_cash_position", "Cash in the bank today, the minimum cash buffer and the headroom above it.",
             NoInput, _get_cash_position),
    ToolSpec("get_ledger", "List bank transactions or invoices (newest first) with filters. Invoice lists show "
             "outstanding balances and days past due but not invoice notes; use explain_record for those.",
             LedgerIn, _get_ledger, cents=True),
    ToolSpec("get_forecast", "The 13-week cash forecast from today: weekly opening/inflows/outflows/closing, "
             "whether each week is below the buffer, the gap, and the lines driving the gap weeks (or a chosen "
             "week) with their source records.", ForecastIn, _get_forecast),
    ToolSpec("get_insights", "Detected problems and opportunities (late payers, duplicate subscriptions, price "
             "creep, cash gaps, unusual expenses) with impact and evidence.", InsightsIn, _get_insights),
    ToolSpec("explain_record", "Full detail of one record by reference, e.g. invoice:30 (lines, outstanding, "
             "days past due, notes), counterparty:6 (payment history, payee allowlist), recurring_series:2, "
             "transaction:5, insight:4, action:12, account:1.", ExplainIn, _explain_record, cents=True),
    ToolSpec("run_what_if", "Simulate the forecast with scenario changes (collect or delay a receivable, add a "
             "recurring cost/income, a one-off payment, remove a recurring series) and compare with the base "
             "forecast. Changes nothing.", WhatIfIn, _run_what_if),
    ToolSpec("rank_financing", "Rank ways to cover the cash gap (sandbox catalog: overdraft, short-term loan, "
             "invoice factoring, supplier terms extension, early-payment discount) by cost. The gap comes from "
             "the forecast, optionally after what-if scenarios; you never pass an amount.",
             FinancingIn, _rank_financing, cents=True),
    ToolSpec("draft_reminder", "Draft a payment reminder for an open receivable from a fixed template. Returns "
             "the draft (draft_id); nothing is sent. Use send_reminder to propose sending it.",
             DraftReminderIn, _draft_reminder),
    ToolSpec("draft_terms_request", "Draft a request asking a supplier for more days on payment terms, from a "
             "fixed template. Returns the draft (draft_id); nothing is sent. Use send_terms_request to propose "
             "sending it.", TermsRequestIn, _draft_terms_request),
    ToolSpec("draft_cfo_memo", "Facts for this week's CFO memo: cash, the gap, top insights, pending approvals.",
             NoInput, _draft_cfo_memo),
    ToolSpec("send_reminder", "Propose emailing a reminder draft (from draft_reminder) to the customer's stored "
             "address. Creates a proposal that a human must approve; it does not send anything.",
             SendReminderIn, None),
    ToolSpec("send_terms_request", "Propose emailing a terms-request draft (from draft_terms_request) to the "
             "supplier's stored address. Creates a proposal that the owner must approve; it does not send anything.",
             SendTermsRequestIn, None),
    ToolSpec("schedule_payment", "Propose paying an open payable invoice of an existing, allowlisted "
             "counterparty, by ids only; amount in integer cents. Payment always goes to the counterparty's stored "
             "details. Creates a proposal that a human must approve.", SchedulePaymentIn, None),
    ToolSpec("submit_loan_application", "Propose applying for a sandbox financing product (option_id from "
             "rank_financing: overdraft, short_term_loan, invoice_factoring); amount in integer cents. Creates a "
             "proposal that a human must approve.", SubmitLoanApplicationIn, None),
)}


def json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic schema with $refs inlined and pydantic-only keywords dropped."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def clean(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return clean(defs[node["$ref"].split("/")[-1]])
            return {k: clean(v) for k, v in node.items() if k not in ("title", "discriminator")}
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    out = clean(schema)
    out["additionalProperties"] = False
    return out


def tools_for(user: User) -> list[ToolSpec]:
    """Only the tools the user's role may use are offered to the model (the gate still checks every call)."""
    return [spec for spec in TOOLS.values() if can_propose(user.role, spec.tier, spec.name)]


# --- dispatch ------------------------------------------------------------------------------


def _result(name: str, ok: bool, body: dict[str, Any]) -> str:
    return json.dumps({"tool": name, "ok": ok, **body}, ensure_ascii=False, separators=(",", ":"), default=str)


def _audit_call(ctx: ToolContext, name: str, tier: Tier | None, tool_input: Any, ok: bool,
                action: dict[str, Any] | None, error: str | None = None) -> None:
    stored = tool_input if audit.json_problem(tool_input) is None else {"unstorable_input": True}
    payload: dict[str, Any] = {"business_id": ctx.business.id, "conversation_id": ctx.memory.conversation_id,
                               "tool": name, "tier": tier.value if tier else None, "input": stored, "ok": ok}
    if action:
        payload["action_id"] = action["action_id"]
    if error:
        payload["error"] = error[:200]
    audit.append(ctx.session, actor_for(ctx.user, via_agent=True).label, "agent_tool_called", payload,
                 now=ctx.service.clock())


def dispatch(ctx: ToolContext, name: str, tool_input: Any) -> ToolOutcome:
    """Run one tool call. Errors come back as an is_error result the model can read; nothing raises
    except database errors."""
    spec = TOOLS.get(name)
    tier = spec.tier if spec else None
    action, parsed = None, None
    tool_input = ctx.memory.vault.mask(tool_input)  # backstop: model input is stored and audited masked
    try:
        if spec is None:
            raise ToolInputError(f"unknown tool {name!r}")
        if not isinstance(tool_input, dict):
            raise ToolInputError("tool input must be a JSON object")
        if not can_propose(ctx.user.role, spec.tier, name):  # before anything is proposed or stored
            raise ToolInputError(f"{name} is not available to the {ctx.user.role.value} role")
        if ctx.allowed is not None and name not in ctx.allowed:
            raise ToolInputError(f"{name} is not available in this task")
        if spec.handler is None:
            if ctx.proposals >= MAX_PROPOSALS_PER_TURN:
                raise ToolInputError(f"at most {MAX_PROPOSALS_PER_TURN} proposals per turn; ask the user first")
            ctx.proposals += 1
            data, action = _propose(ctx, name, tool_input)
        else:
            parsed = spec.input_model.model_validate(tool_input)
            data = spec.handler(ctx, parsed)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'input'}: {err['msg']}" for err in e.errors())
        return _error(ctx, name, tier, tool_input, f"invalid input ({problems})")
    except (ToolInputError, ScenarioError, ActionError) as e:
        return _error(ctx, name, tier, tool_input, getattr(e, "detail", None) or str(e))
    shown = ctx.memory.vault.mask(present(data, ctx.business.base_currency, cents=spec.cents or spec.handler is None))
    ctx.memory.index.add_result(shown)
    _audit_call(ctx, name, tier, tool_input, True, action)
    scenarios = ([sc.model_dump(mode="json", exclude_none=True) for sc in parsed.scenarios]
                 if isinstance(parsed, (WhatIfIn, FinancingIn)) else None)
    return ToolOutcome(_result(name, True, {"data": shown}), False, tier, action, scenarios)


def _error(ctx: ToolContext, name: str, tier: Tier | None, tool_input: Any, message: str) -> ToolOutcome:
    _audit_call(ctx, name, tier, tool_input, False, None, message)
    return ToolOutcome(_result(name, False, {"error": ctx.memory.vault.mask_text(message)}), True, tier)

