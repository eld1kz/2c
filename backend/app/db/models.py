"""SQLAlchemy models for SPEC §5.

Money is always integer minor units (BigInteger) next to an ISO 4217 `currency` column.
AuditEvent is append-only: the ORM refuses to flush updates or deletes of it, and migration 0003
adds a DB trigger that rejects UPDATE/DELETE from any client.
"""

import datetime as dt
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, ORMExecuteState, Session, mapped_column


class Base(DeclarativeBase):
    pass


def _enum(cls: type[StrEnum]) -> Enum:
    return Enum(cls, native_enum=False, create_constraint=True, length=32, values_callable=lambda e: [m.value for m in e])


def _money() -> Mapped[int]:
    return mapped_column(BigInteger, nullable=False)


def _currency() -> Mapped[str]:
    return mapped_column(String(3), nullable=False, default="USD")


# --- enums -----------------------------------------------------------------


class Role(StrEnum):
    owner = "owner"
    accountant = "accountant"
    viewer = "viewer"


class AccountType(StrEnum):
    checking = "checking"
    savings = "savings"
    cash = "cash"


class CounterpartyKind(StrEnum):
    customer = "customer"
    supplier = "supplier"
    both = "both"


class Category(StrEnum):
    revenue_retail = "revenue_retail"
    revenue_wholesale = "revenue_wholesale"
    cogs_beans = "cogs_beans"
    cogs_packaging = "cogs_packaging"
    rent = "rent"
    utilities = "utilities"
    payroll = "payroll"
    software = "software"
    equipment = "equipment"
    logistics = "logistics"
    marketing = "marketing"
    fees = "fees"
    taxes = "taxes"
    transfer = "transfer"
    other = "other"


class CategorySource(StrEnum):
    rule = "rule"
    llm = "llm"
    human = "human"


class RuleKind(StrEnum):
    keyword = "keyword"  # whole-token phrase anywhere in the normalized description
    name = "name"  # matched counterparty's normalized_name


class RuleDirection(StrEnum):
    inflow = "in"
    outflow = "out"
    any = "any"


class RuleSource(StrEnum):
    seed = "seed"
    human = "human"


class InvoiceDirection(StrEnum):
    receivable = "receivable"
    payable = "payable"


class InvoiceStatus(StrEnum):
    open = "open"
    paid = "paid"
    overdue = "overdue"
    void = "void"


class Cadence(StrEnum):
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"


class ForecastLineKind(StrEnum):
    opening = "opening"
    recurring = "recurring"
    ar_expected = "ar_expected"
    ap_due = "ap_due"
    baseline_in = "baseline_in"
    baseline_out = "baseline_out"
    scenario = "scenario"


class InsightType(StrEnum):
    LATE_PAYER = "LATE_PAYER"
    DUPLICATE_SUBSCRIPTION = "DUPLICATE_SUBSCRIPTION"
    PRICE_CREEP = "PRICE_CREEP"
    CASH_GAP = "CASH_GAP"
    UNUSUAL_EXPENSE = "UNUSUAL_EXPENSE"
    LOW_MARGIN_CUSTOMER = "LOW_MARGIN_CUSTOMER"


class Severity(StrEnum):
    low = "low"
    med = "med"
    high = "high"


class InsightStatus(StrEnum):
    open = "open"
    actioned = "actioned"
    dismissed = "dismissed"


class ProposedBy(StrEnum):
    agent = "agent"
    user = "user"


class Tier(StrEnum):
    READ = "READ"
    SUGGEST = "SUGGEST"
    EXECUTE = "EXECUTE"


class ActionStatus(StrEnum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"
    failed = "failed"
    denied = "denied"


class PaymentStatus(StrEnum):
    scheduled = "scheduled"
    executed = "executed"
    failed = "failed"


class EmailStatus(StrEnum):
    queued = "queued"
    sent = "sent"
    failed = "failed"


class LoanStatus(StrEnum):
    submitted = "submitted"
    approved = "approved"
    declined = "declined"


# --- core ------------------------------------------------------------------


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    base_currency: Mapped[str] = _currency()
    industry: Mapped[str] = mapped_column(String(100))
    min_cash_buffer: Mapped[int] = _money()
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(_enum(Role))
    password_hash: Mapped[str] = mapped_column(String(100))


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[AccountType] = mapped_column(_enum(AccountType))
    currency: Mapped[str] = _currency()
    opening_balance: Mapped[int] = _money()


class Counterparty(Base):
    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[CounterpartyKind] = mapped_column(_enum(CounterpartyKind))
    is_allowed_payee: Mapped[bool] = mapped_column(Boolean, default=False)
    # Stored contact for sandbox emails; recipients never come from documents or drafts.
    contact_email: Mapped[str | None] = mapped_column(String(254))
    # avg_days_late, invoices_count, on_time_rate — computed by the engine
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    date: Mapped[dt.date] = mapped_column(Date)
    amount: Mapped[int] = _money()  # signed: inflow > 0, outflow < 0
    currency: Mapped[str] = _currency()
    raw_description: Mapped[str] = mapped_column(Text)
    counterparty_id: Mapped[int | None] = mapped_column(ForeignKey("counterparties.id"))
    category: Mapped[Category | None] = mapped_column(_enum(Category))
    category_source: Mapped[CategorySource | None] = mapped_column(_enum(CategorySource))
    confidence: Mapped[float | None] = mapped_column(Float)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    source_file: Mapped[str] = mapped_column(String(255))
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))


class CategoryRule(Base):
    """Categorization rules (SPEC §6.2), applied in ascending priority; first match wins."""

    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    kind: Mapped[RuleKind] = mapped_column(_enum(RuleKind))
    pattern: Mapped[str] = mapped_column(String(200))
    direction: Mapped[RuleDirection] = mapped_column(_enum(RuleDirection))
    category: Mapped[Category] = mapped_column(_enum(Category))
    source: Mapped[RuleSource] = mapped_column(_enum(RuleSource))
    priority: Mapped[int] = mapped_column(Integer)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("business_id", "number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    direction: Mapped[InvoiceDirection] = mapped_column(_enum(InvoiceDirection))
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"))
    number: Mapped[str] = mapped_column(String(50))
    issue_date: Mapped[dt.date] = mapped_column(Date)
    due_date: Mapped[dt.date] = mapped_column(Date)
    total: Mapped[int] = _money()
    currency: Mapped[str] = _currency()
    status: Mapped[InvoiceStatus] = mapped_column(_enum(InvoiceStatus))
    # UNTRUSTED text from the counterparty. Never interpolate into prompts.
    notes: Mapped[str | None] = mapped_column(Text)


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    description: Mapped[str] = mapped_column(String(500))
    sku: Mapped[str | None] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = _money()  # currency = parent invoice's


class RecurringSeries(Base):
    __tablename__ = "recurring_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"))
    category: Mapped[Category] = mapped_column(_enum(Category))
    typical_amount: Mapped[int] = _money()
    currency: Mapped[str] = _currency()
    cadence: Mapped[Cadence] = mapped_column(_enum(Cadence))
    next_expected_date: Mapped[dt.date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    transaction_ids: Mapped[list[int]] = mapped_column(JSON, default=list)


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    as_of: Mapped[dt.date] = mapped_column(Date)
    horizon_weeks: Mapped[int] = mapped_column(Integer)
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    scenario_name: Mapped[str | None] = mapped_column(String(200))


class ForecastLine(Base):
    __tablename__ = "forecast_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"))
    week_start: Mapped[dt.date] = mapped_column(Date)
    kind: Mapped[ForecastLineKind] = mapped_column(_enum(ForecastLineKind))
    amount: Mapped[int] = _money()
    currency: Mapped[str] = _currency()
    probability: Mapped[float] = mapped_column(Float, default=1.0)
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    type: Mapped[InsightType] = mapped_column(_enum(InsightType))
    severity: Mapped[Severity] = mapped_column(_enum(Severity))
    title: Mapped[str] = mapped_column(String(300))
    impact_amount: Mapped[int] = _money()
    currency: Mapped[str] = _currency()
    impact_period: Mapped[str] = mapped_column(String(20))
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    detected_at: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[InsightStatus] = mapped_column(_enum(InsightStatus), default=InsightStatus.open)


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("business_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    proposed_by: Mapped[ProposedBy] = mapped_column(_enum(ProposedBy))
    tool: Mapped[str] = mapped_column(String(100))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tier: Mapped[Tier] = mapped_column(_enum(Tier))
    status: Mapped[ActionStatus] = mapped_column(_enum(ActionStatus))
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(100))  # unique per business
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AuditEvent(Base):
    """Append-only. Never update or delete rows (see guard below)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, unique=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class AppendOnlyViolation(Exception):
    pass


@event.listens_for(Session, "before_flush")
def _guard_audit_append_only(session: Session, flush_context: object, instances: object) -> None:
    for obj in list(session.dirty) + list(session.deleted):
        if isinstance(obj, AuditEvent):
            raise AppendOnlyViolation("AuditEvent is append-only")


@event.listens_for(Session, "do_orm_execute")
def _guard_audit_bulk_append_only(state: ORMExecuteState) -> None:
    if (state.is_update or state.is_delete) and state.statement.table.name == AuditEvent.__tablename__:
        raise AppendOnlyViolation("AuditEvent is append-only")


DEFAULT_MAX_DAILY_PAYMENTS = 1_000_000  # $10,000


class Policy(Base):
    __tablename__ = "policies"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), primary_key=True)
    max_single_payment: Mapped[int] = _money()
    # Total of executed + approved payments with the same payment date (default 2 × the single limit).
    max_daily_payments: Mapped[int] = mapped_column(BigInteger, nullable=False, default=DEFAULT_MAX_DAILY_PAYMENTS)
    currency: Mapped[str] = _currency()
    reminder_cooldown_days: Mapped[int] = mapped_column(Integer)
    require_owner_for: Mapped[list[str]] = mapped_column(JSON, default=list)
    payee_allowlist_mode: Mapped[str] = mapped_column(String(20), default="strict")


# --- sandbox ---------------------------------------------------------------


class SandboxPayment(Base):
    __tablename__ = "sandbox_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    action_id: Mapped[int] = mapped_column(ForeignKey("actions.id"), unique=True)
    payee_counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"))
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))  # the payable it settles
    amount: Mapped[int] = _money()
    currency: Mapped[str] = _currency()
    scheduled_date: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[PaymentStatus] = mapped_column(_enum(PaymentStatus))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    executed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class SandboxEmail(Base):
    __tablename__ = "sandbox_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    action_id: Mapped[int] = mapped_column(ForeignKey("actions.id"), unique=True)
    to_address: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[EmailStatus] = mapped_column(_enum(EmailStatus))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class SandboxLoanApplication(Base):
    __tablename__ = "sandbox_loan_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    action_id: Mapped[int] = mapped_column(ForeignKey("actions.id"), unique=True)
    option_id: Mapped[str] = mapped_column(String(100))
    amount: Mapped[int] = _money()
    currency: Mapped[str] = _currency()
    status: Mapped[LoanStatus] = mapped_column(_enum(LoanStatus))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


# --- LLM spend -------------------------------------------------------------


class LlmUsage(Base):
    """One billed model call (agent or categorizer). Cost in integer micro-dollars; `day` is the UTC
    calendar day the daily budget is counted on (real spend, so wall clock, not DEMO_TODAY)."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    day: Mapped[dt.date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(20))  # agent | classifier
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cache_read_tokens: Mapped[int] = mapped_column(Integer)
    cache_write_tokens: Mapped[int] = mapped_column(Integer)
    cost_microusd: Mapped[int] = mapped_column(BigInteger)


class CfoMemo(Base):
    """The weekly CFO memo, cached so viewing it never calls the model. Only memos whose every figure
    passed the citation check are stored; `facts_digest` tells whether the numbers changed since. Demo
    reset deletes them."""

    __tablename__ = "cfo_memos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    as_of: Mapped[dt.date] = mapped_column(Date)  # DEMO_TODAY when written
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    generated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    facts_digest: Mapped[str] = mapped_column(String(64))
