"""Pydantic request/response models for the HTTP API."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.audit.log import json_problem
from app.db.models import Category


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


class ForecastOut(BaseModel):
    as_of: date
    currency: str
    min_cash_buffer_cents: int
    weeks: list[ForecastWeekOut]
    lowest: LowestOut
    gap: GapOut | None


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
