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
