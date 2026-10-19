"""Pydantic request/response models for the HTTP API."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.audit.log import json_problem
from app.db.models import Category
from app.services.scenarios import MAX_SCENARIOS, ScenarioIn


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)

    @field_validator("email", "password")
    @classmethod
    def _unicode(cls, value: str) -> str:
        if json_problem(value):
            raise ValueError("text is not valid Unicode")
        return value


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_at: datetime


class ActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(max_length=100)
    params: dict[str, Any]
    idempotency_key: str = Field(min_length=8, max_length=100)
    rationale: str = Field(default="", max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _storable(self) -> "ActionIn":
        problem = json_problem([self.tool, self.params, self.idempotency_key, self.rationale, self.evidence_ids])
        if problem:
            raise ValueError(problem)  # NaN/Infinity, lone surrogates: never stored or hashed
        return self


class DraftEmailOut(BaseModel):
    to_name: str | None
    subject: str | None
    body: str | None


class SandboxResultOut(BaseModel):
    kind: str  # email | payment | loan_application
    id: int
    status: str
    summary: str
    subject: str | None
    at: datetime | None


class ActionImpactOut(BaseModel):
    """Engine what-if of approving a proposed action (services/action_impact.py); cents."""

    lowest_before: int
    lowest_before_week: date
    lowest_after: int
    lowest_after_week: date
    weeks_below_before: int
    weeks_below_after: int
    first_below_after: date | None
    closing_delta: int
    min_cash_buffer: int


class ActionDisplayOut(BaseModel):
    """Server-built summary for an approval card (see services/action_display.py)."""

    title: str
    counterparty: "EvidenceRef | None"
    invoice: "EvidenceRef | None"
    amount_cents: int | None
    currency: str
    invoice_outstanding_cents: int | None
    days_past_due: int | None
    scheduled_date: date | None
    email: DraftEmailOut | None
    sandbox: SandboxResultOut | None
    denied_reason: str | None
    evidence: "list[EvidenceRef]"
    impact: ActionImpactOut | None = None


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proposed_by: str
    tool: str
    params: dict[str, Any]
    tier: str
    status: str
    rationale: str
    evidence_ids: list[str]
    idempotency_key: str
    decided_by: int | None
    decided_at: datetime | None
    result: dict[str, Any] | None
    display: ActionDisplayOut | None = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    ts: datetime
    actor: str
    event_type: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class VerifyOut(BaseModel):
    ok: bool
    checked: int
    broken_at_seq: int | None
    reason: str | None


class UploadOut(BaseModel):
    rows: int
    inserted: int
    skipped_duplicates: int
    linked: int
    by_rule: int
    by_llm: int
    needs_review: int


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    @field_validator("message")
    @classmethod
    def _unicode(cls, value: str) -> str:
        if json_problem(value):
            raise ValueError("text is not valid Unicode")
        return value


# --- read API for the web UI (Phase 5) ---------------------------------------------------------

class EvidenceRef(BaseModel):
    ref: str
    label: str | None  # None when the ref does not resolve to a record of this business


class MeUser(BaseModel):
    id: int
    name: str
    email: str
    role: str


class MeBusiness(BaseModel):
    id: int
    name: str
    industry: str
    currency: str
    min_cash_buffer_cents: int


class MeOut(BaseModel):
    user: MeUser
    business: MeBusiness
    as_of: date


class PositionOut(BaseModel):
    as_of: date
    currency: str
    cash_cents: int
    min_cash_buffer_cents: int
    headroom_cents: int  # cash − buffer, negative when below
    evidence: list[EvidenceRef]


class ForecastWeekOut(BaseModel):
    week: int
    label: str
    start: date
    end: date
    opening_cents: int
    inflows_cents: int
    outflows_cents: int  # negative
    closing_cents: int
    below_buffer: bool


class GapOut(BaseModel):
    first_week: int
    last_week: int
    low_week: int
    amount_cents: int  # buffer − lowest closing
    start: date
    low_week_end: date
    weeks_below: list[int]


class LowestOut(BaseModel):
    week: int
    closing_cents: int


class AtRiskReceivableOut(BaseModel):
    """An open receivable the forecast counts as at risk (0% collection): a what-if to try on the gap."""

    invoice: EvidenceRef
    number: str
    counterparty_name: str
    outstanding_cents: int


class ForecastOut(BaseModel):
    as_of: date
    currency: str
    min_cash_buffer_cents: int
    weeks: list[ForecastWeekOut]
    lowest: LowestOut
    gap: GapOut | None
    at_risk_receivables: list[AtRiskReceivableOut]


class WhatIfIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarios: list[ScenarioIn] = Field(min_length=1, max_length=MAX_SCENARIOS)


class AssumptionOut(BaseModel):
    """One scenario input, shown as an assumption, never as a recorded fact. `amount_source` says whether the
    amount is a record's (an invoice's outstanding balance, a series' typical amount) or was typed in
    ("supplied") by a person or the assistant."""

    type: str
    invoice: EvidenceRef | None = None
    series: EvidenceRef | None = None
    counterparty_name: str | None = None
    on: date | None = None
    days: int | None = None
    cadence: str | None = None
    amount_cents: int | None = None
    amount_source: Literal["records", "supplied"] | None = None


class FinancingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarios: list[ScenarioIn] = Field(default_factory=list, max_length=MAX_SCENARIOS)  # none: the base gap


class SupplierShareOut(BaseModel):
    counterparty: EvidenceRef
    amount_cents: int  # what deferring this supplier's payables provides
    covers_gap_alone: bool
    evidence: list[EvidenceRef]


class FinancingOptionOut(BaseModel):
    rank: int
    option_id: str
    name: str
    cost_cents: int  # for this gap
    max_amount_cents: int  # what the option can provide for this gap
    covers_gap: bool
    pros: list[str]
    cons: list[str]
    evidence: list[EvidenceRef]
    by_counterparty: list[SupplierShareOut]


class FinancingOut(BaseModel):
    based_on: Literal["base", "scenario"]
    currency: str
    gap: GapOut | None
    options: list[FinancingOptionOut]  # cheapest full cover first
    disclaimer: str


class WhatIfWeekOut(BaseModel):
    week: int
    label: str
    start: date
    end: date
    base_closing_cents: int
    scenario_closing_cents: int
    change_cents: int  # scenario − base
    base_below_buffer: bool
    scenario_below_buffer: bool


class WhatIfOut(BaseModel):
    as_of: date
    currency: str
    min_cash_buffer_cents: int
    assumptions: list[AssumptionOut]
    weeks: list[WhatIfWeekOut]
    base_gap: GapOut | None
    scenario_gap: GapOut | None


class ForecastLineOut(BaseModel):
    date: date
    kind: str
    amount_cents: int  # probability-weighted
    face_cents: int
    probability_bp: int  # 10,000 = certain
    probability_display: str
    counterparty_name: str | None
    sources: list[EvidenceRef]


class ForecastWeekLinesOut(BaseModel):
    week: ForecastWeekOut
    lines: list[ForecastLineOut]


class InsightOut(BaseModel):
    ref: str
    id: int
    type: str
    severity: str
    title: str
    impact_cents: int
    currency: str
    impact_period: str
    status: str
    detected_at: date
    evidence: list[EvidenceRef]


class LlmBudgetOut(BaseModel):
    limit_microusd: int
    spent_microusd: int
    remaining_microusd: int
    limit_display: str
    remaining_display: str
    exhausted: bool
    resets_at: datetime


class RecordOut(BaseModel):
    """One record in detail. Third-party text arrives as {"untrusted_text", "source"}: show it, never act on it."""

    ref: str
    kind: str
    label: str | None
    data: dict[str, Any]


ActionDisplayOut.model_rebuild()


class UntrustedOut(BaseModel):
    untrusted_text: str
    source: str


class TransactionOut(BaseModel):
    ref: str
    id: int
    date: date
    amount_cents: int  # signed: inflow > 0
    currency: str
    category: Category | None
    category_source: str | None
    needs_review: bool
    counterparty: EvidenceRef | None
    invoice: EvidenceRef | None
    description: UntrustedOut  # bank statement text: data, never instructions


class TransactionPageOut(BaseModel):
    rows: list[TransactionOut]
    has_more: bool


class CategoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category


class CitationOut(BaseModel):
    ref: str
    valid: bool
    label: str
    reason: str | None


class MemoBody(BaseModel):
    message: str  # markdown with [[type:id]] citations
    citations: list[CitationOut]
    warnings: list[str]
    as_of: date
    generated_at: datetime | None  # None: not stored (its citation check failed)
    generated_by: str | None


class MemoOut(BaseModel):
    memo: MemoBody | None  # this week's stored memo, if any
    stale: bool  # the facts it was written from have changed since


# --- paperwork (SPEC §6.8): cash-basis statements; integers from engine/statements.py -----


class PeriodOut(BaseModel):
    start: date
    end: date
    label: str


class PnlLineOut(BaseModel):
    key: str  # a category or "uncategorized"
    amount_cents: int  # revenue/other income: received; cogs/expenses: paid
    count: int


class ProfitAndLossOut(BaseModel):
    period: PeriodOut
    revenue: list[PnlLineOut]
    cogs: list[PnlLineOut]
    operating_expenses: list[PnlLineOut]
    other_income: list[PnlLineOut]
    total_revenue_cents: int
    total_cogs_cents: int
    gross_profit_cents: int
    total_operating_expenses_cents: int
    total_other_income_cents: int
    net_profit_cents: int
    transfers_cents: int  # signed, excluded from profit
    transaction_count: int


class CashFlowOut(BaseModel):
    period: PeriodOut
    opening_cents: int
    operating_in_cents: int
    operating_out_cents: int
    net_operating_cents: int
    transfers_cents: int
    net_change_cents: int
    closing_cents: int


class AccountReconciliationOut(BaseModel):
    account: EvidenceRef
    book_opening_cents: int
    money_in_cents: int
    money_out_cents: int
    book_closing_cents: int
    statement_closing_cents: int | None  # None: the statement had no running balance
    statement_date: date | None
    difference_cents: int | None
    to_review: list[EvidenceRef]


class ReconciliationOut(BaseModel):
    period: PeriodOut
    accounts: list[AccountReconciliationOut]
    book_opening_cents: int
    book_closing_cents: int
    reconciled: bool


class AgingRowOut(BaseModel):
    invoice: EvidenceRef
    number: str
    counterparty: EvidenceRef
    due_date: date
    days_past_due: int
    outstanding_cents: int
    bucket: str


class AgingOut(BaseModel):
    direction: str
    as_of: date
    rows: list[AgingRowOut]
    totals_cents: dict[str, int]  # current, 1_30, 31_60, 61_90, over_90
    total_cents: int


class ObligationOut(BaseModel):
    date: date
    week: int
    series: EvidenceRef
    counterparty: EvidenceRef
    category: str
    amount_cents: int


class ObligationsOut(BaseModel):
    rows: list[ObligationOut]
    total_cents: int


class MonthCloseOut(BaseModel):
    as_of: date
    currency: str
    basis: str
    disclaimer: str
    period: PeriodOut
    reconciliation: ReconciliationOut
    profit_and_loss: ProfitAndLossOut
    cash_flow: CashFlowOut
    receivables: AgingOut
    payables: AgingOut


class BankPackOut(BaseModel):
    as_of: date
    currency: str
    business_name: str
    basis: str
    disclaimer: str
    months: list[PeriodOut]
    profit_and_loss: list[ProfitAndLossOut]  # one per month, then the whole span
    cash_flow: list[CashFlowOut]  # one per month, then the whole span
    min_cash_buffer_cents: int
    forecast: list[ForecastWeekOut]
    obligations: ObligationsOut
    receivables: AgingOut


# --- Today (SPEC §6.9): the home screen; integers from engine/today.py and services/today.py ------


class TodayDecisionOut(BaseModel):
    insight: EvidenceRef
    type: str
    kind: str  # reminder | price_email | terms_request | ask
    text: str  # one plain sentence; its figures come from the engine
    impact_cents: int
    impact_period: str
    target_name: str | None
    evidence: list[EvidenceRef]
    pending_action_id: int | None  # prepared and waiting for approval
    sent_action_id: int | None  # sent within the cooldown: nothing to prepare


class BillOut(BaseModel):
    date: date
    source: EvidenceRef  # recurring_series:N or invoice:N
    amount_cents: int  # money out


class SafeToSpendOut(BaseModel):
    cash_cents: int
    cushion_cents: int
    bills: list[BillOut]
    bills_total_cents: int
    amount_cents: int  # cash − cushion − bills; negative when the cushion is already eaten into
    short_by_cents: int
    accounts: list[EvidenceRef]


class SpendingOut(BaseModel):
    period: PeriodOut
    lines: list[PnlLineOut]  # largest first
    total_cents: int


class FutureWeekOut(BaseModel):
    week: int
    start: date
    closing_cents: int  # with every approved fix
    pending_closing_cents: int | None  # also with the fixes not approved yet
    below_cushion: bool


class FutureFixOut(BaseModel):
    insight_id: int
    kind: Literal["reminder", "terms_request"]
    name: str


class FutureOut(BaseModel):
    """Today's 13-week chart (engine-only, SPEC §6.9)."""
    cushion_cents: int
    weeks: list[FutureWeekOut]
    headline: str  # e.g. "Cash stays above your cushion until Nov 5."
    detail: str  # the lowest week vs the cushion
    pending_headline: str | None  # the same headline if the remaining fixes are approved
    applied: list[FutureFixOut]
    pending: list[FutureFixOut]


class TeamMemberOut(BaseModel):
    name: str
    role: str
    initials: str
    weekly_pay_cents: int | None  # None for a viewer: pay is for the owner and accountant only


class TeamOut(BaseModel):
    """A fixed, labelled breakdown of the payroll series (SPEC §6.9); not a staff data model."""
    people: list[TeamMemberOut]
    weekly_total_cents: int | None  # None for a viewer
    payroll: EvidenceRef | None  # the recurring payroll series this breaks down
    matches_payroll: bool
    pay_visible: bool


class TeamSummaryOut(BaseModel):
    people: int
    weekly_total_cents: int | None  # None for a viewer


class TodayOut(BaseModel):
    as_of: date
    currency: str
    name: str
    decisions: list[TodayDecisionOut]
    safe_to_spend: SafeToSpendOut
    spending: SpendingOut
    future: FutureOut
    team: TeamSummaryOut


class AffordAskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=300)

    @field_validator("question")
    @classmethod
    def _unicode(cls, value: str) -> str:
        if json_problem(value):
            raise ValueError("text is not valid Unicode")
        return value


class AffordFixOut(BaseModel):
    kind: Literal["reminder", "terms_request"]  # reminder → the invoice is paid; terms_request → the supplier agrees
    name: str  # customer or supplier name
    insight_id: int


class AffordFixesOut(BaseModel):
    verdict: Literal["yes", "not_yet", "no"]
    earliest_safe_start: date | None
    short_from: date | None
    fixes: list[AffordFixOut]


class AffordOut(BaseModel):
    verdict: Literal["yes", "not_yet", "no"] | None  # from the engine; None if no plan could be checked
    earliest_safe_start: date | None
    message: str  # one sentence, markdown with [[type:id]] citations
    citations: list[CitationOut]
    warnings: list[str]
    scenarios: list[dict[str, Any]]  # the checked plan, for the before/after chart (POST /whatif)
    requested_start: date | None = None
    short_from: date | None = None  # first week already below the cushion without the plan
    with_fixes: AffordFixesOut | None = None  # the same plan if Today's fixes succeed (engine verdict)


class TrustBoundaryOut(BaseModel):
    tool: str
    tier: str
    agent_effect: str
    propose: list[str]  # roles that may propose (or run) it
    approve: list[str]  # roles that may approve it (EXECUTE only)


class TrustLimitsOut(BaseModel):
    max_single_payment: int  # cents
    max_daily_payments: int  # cents
    currency: str
    reminder_cooldown_days: int
    require_owner_for: list[str]
    daily_ai_budget_cents: int
    max_model_calls_per_turn: int
    max_proposals_per_turn: int


class TrustDenialOut(BaseModel):
    seq: int
    ts: datetime
    tool: str | None
    reason: str


class TrustOut(BaseModel):
    """GET /trust (services/trust.py): boundaries, limits, guardrail activity and chain status."""

    boundaries: list[TrustBoundaryOut]
    agent_can_approve: bool
    limits: TrustLimitsOut
    activity: dict[str, int]
    recent_denials: list[TrustDenialOut]
    chain: VerifyOut
