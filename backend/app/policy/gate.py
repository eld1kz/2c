"""Policy gate (SPEC §8): check(action, actor, ctx) → ALLOW | REQUIRE_APPROVAL | DENY(reason).

Code, not prompt. ActionService calls it when an action is proposed and again just before it is
executed, so state that changed in between (an invoice paid, a reminder just sent) is caught.
EXECUTE tools never get ALLOW: at best REQUIRE_APPROVAL.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.rbac import can_propose
from app.db.models import (
    Action,
    ActionStatus,
    Counterparty,
    CounterpartyKind,
    Invoice,
    InvoiceDirection,
    Policy,
    Role,
    SandboxEmail,
    Tier,
)
from app.policy.limits import LOAN_PRODUCTS, OPEN_STATUSES, invoice_outstanding, loan_limit, payments_on
from app.policy.tiers import (
    EXECUTE_PARAMS,
    SchedulePaymentParams,
    SendPriceRequestParams,
    SendReminderParams,
    SendTermsRequestParams,
    SubmitLoanApplicationParams,
    tier_of,
)

DRAFT_TOOL = "draft_reminder"
TERMS_DRAFT_TOOL = "draft_terms_request"
PRICE_DRAFT_TOOL = "draft_price_request"
MAX_PAYMENT_LEAD_DAYS = 90  # payment date must be within [DEMO_TODAY, +90 days]


class Decision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


@dataclass(frozen=True)
class GateResult:
    decision: Decision
    reason: str = ""


@dataclass(frozen=True)
class Actor:
    """Who is acting. The agent always acts for a signed-in user and carries that user's role."""

    business_id: int
    user_id: int
    role: Role
    via_agent: bool = False

    @property
    def label(self) -> str:
        return f"agent:user:{self.user_id}" if self.via_agent else f"user:{self.user_id}"


@dataclass(frozen=True)
class ActionRequest:
    business_id: int
    tool: str
    params: dict[str, Any]
    action_id: int | None = None  # set on the execution re-check, so the action does not count against itself


@dataclass(frozen=True)
class GateContext:
    session: Session
    policy: Policy
    now: datetime  # wall clock (cooldowns)
    today: date  # DEMO_TODAY (days past due)


def deny(reason: str) -> GateResult:
    return GateResult(Decision.DENY, reason)


APPROVAL = GateResult(Decision.REQUIRE_APPROVAL)


def check(action: ActionRequest, actor: Actor, ctx: GateContext) -> GateResult:
    tier = tier_of(action.tool)
    if tier is None:
        return deny(f"unknown tool {action.tool!r}")
    if actor.business_id != action.business_id:
        return deny("actor belongs to another business")
    if not can_propose(actor.role, tier, action.tool):
        return deny(f"role {actor.role.value} may not use {action.tool}")
    if tier != Tier.EXECUTE:
        return GateResult(Decision.ALLOW)
    try:
        params = EXECUTE_PARAMS[action.tool].model_validate(action.params)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'params'}: {err['msg']}" for err in e.errors())
        return deny(f"invalid parameters ({problems})")
    match params:
        case SchedulePaymentParams():
            return _schedule_payment(action.business_id, params, ctx, action.action_id)
        case SendReminderParams():
            return _send_reminder(action.business_id, params, ctx)
        case SendTermsRequestParams():
            return _supplier_email(action.business_id, params, ctx, TERMS_DRAFT_TOOL, "send_terms_request")
        case SendPriceRequestParams():
            return _supplier_email(action.business_id, params, ctx, PRICE_DRAFT_TOOL, "send_price_request")
        case SubmitLoanApplicationParams():
            return _loan_application(action.business_id, params, ctx)
    return deny(f"no gate rule for {action.tool}")  # pragma: no cover


def _schedule_payment(business_id: int, p: SchedulePaymentParams, ctx: GateContext,
                      action_id: int | None) -> GateResult:
    payee = ctx.session.get(Counterparty, p.payee_counterparty_id)
    if payee is None or payee.business_id != business_id:
        return deny("payee is not an existing counterparty")
    if not payee.is_allowed_payee:
        return deny("payee is not on the payee allowlist")
    invoice = ctx.session.get(Invoice, p.invoice_id)
    if (invoice is None or invoice.business_id != business_id or invoice.direction != InvoiceDirection.payable
            or invoice.counterparty_id != payee.id or invoice.status not in OPEN_STATUSES):
        return deny("invoice is not an open payable of this payee")
    if invoice.currency != ctx.policy.currency:
        return deny(f"invoice currency {invoice.currency} differs from the policy currency {ctx.policy.currency}")
    if p.amount > ctx.policy.max_single_payment:
        return deny(f"amount {p.amount} exceeds max_single_payment {ctx.policy.max_single_payment} (cents)")
    outstanding = invoice_outstanding(ctx.session, invoice)
    if p.amount > outstanding:
        return deny(f"amount {p.amount} exceeds the invoice's outstanding balance {outstanding} (cents)")
    if not ctx.today <= p.date <= ctx.today + timedelta(days=MAX_PAYMENT_LEAD_DAYS):
        return deny(f"payment date must be between {ctx.today} and {MAX_PAYMENT_LEAD_DAYS} days later")
    day_total = payments_on(ctx.session, business_id, p.date, exclude_action_id=action_id) + p.amount
    if day_total > ctx.policy.max_daily_payments:
        return deny(f"payments dated {p.date} would total {day_total}, over max_daily_payments "
                    f"{ctx.policy.max_daily_payments} (cents)")
    return APPROVAL


def _send_reminder(business_id: int, p: SendReminderParams, ctx: GateContext) -> GateResult:
    invoice = ctx.session.get(Invoice, p.invoice_id)
    if (invoice is None or invoice.business_id != business_id or invoice.direction != InvoiceDirection.receivable
            or invoice.status not in OPEN_STATUSES or invoice_outstanding(ctx.session, invoice) == 0):
        return deny("invoice is not an open receivable")
    draft = ctx.session.get(Action, p.draft_id)
    if (draft is None or draft.business_id != business_id or draft.tool != DRAFT_TOOL
            or draft.status != ActionStatus.executed or draft.params.get("invoice_id") != invoice.id):
        return deny("draft is not a reminder draft for this invoice")
    # The draft states an amount and a lateness: refuse to send it once either may be out of date.
    if draft.result.get("outstanding") != invoice_outstanding(ctx.session, invoice):
        return deny("draft amount no longer matches the outstanding balance; draft a new reminder")
    drafted_at = datetime.fromisoformat(draft.result["drafted_at"])
    if ctx.now - drafted_at > timedelta(days=ctx.policy.reminder_cooldown_days):
        return deny(f"draft is older than {ctx.policy.reminder_cooldown_days} days; draft a new reminder")
    customer = ctx.session.get(Counterparty, invoice.counterparty_id)
    if not customer.contact_email:
        return deny("customer has no stored contact email")
    since = ctx.now - timedelta(days=ctx.policy.reminder_cooldown_days)
    recent = ctx.session.scalars(
        select(Action).join(SandboxEmail, SandboxEmail.action_id == Action.id)
        .where(Action.business_id == business_id, Action.tool == "send_reminder", SandboxEmail.sent_at >= since)
    )
    if any(a.params.get("invoice_id") == invoice.id for a in recent):
        return deny(f"a reminder for this invoice was sent within {ctx.policy.reminder_cooldown_days} days")
    return APPROVAL


def _supplier_email(business_id: int, p: SendTermsRequestParams | SendPriceRequestParams, ctx: GateContext,
                    draft_tool: str, send_tool: str) -> GateResult:
    """send_terms_request / send_price_request: a fixed-template draft for this supplier, to its stored
    contact, at most once per supplier and kind within the cooldown."""
    kind = "terms request" if draft_tool == TERMS_DRAFT_TOOL else "price request"
    supplier = ctx.session.get(Counterparty, p.counterparty_id)
    if (supplier is None or supplier.business_id != business_id
            or supplier.kind not in (CounterpartyKind.supplier, CounterpartyKind.both)):
        return deny("counterparty is not a supplier of this business")
    draft = ctx.session.get(Action, p.draft_id)
    if (draft is None or draft.business_id != business_id or draft.tool != draft_tool
            or draft.status != ActionStatus.executed or draft.params.get("counterparty_id") != supplier.id):
        return deny(f"draft is not a {kind.replace(' ', '-')} draft for this supplier")
    # The draft names a start date and the supplier's payment record: refuse to send a stale one.
    drafted_at = datetime.fromisoformat(draft.result["drafted_at"])
    if ctx.now - drafted_at > timedelta(days=ctx.policy.reminder_cooldown_days):
        return deny(f"draft is older than {ctx.policy.reminder_cooldown_days} days; draft a new {kind}")
    if not supplier.contact_email:
        return deny("supplier has no stored contact email")
    since = ctx.now - timedelta(days=ctx.policy.reminder_cooldown_days)
    recent = ctx.session.scalars(
        select(Action).join(SandboxEmail, SandboxEmail.action_id == Action.id)
        .where(Action.business_id == business_id, Action.tool == send_tool, SandboxEmail.sent_at >= since)
    )
    if any(a.params.get("counterparty_id") == supplier.id for a in recent):
        return deny(f"a {kind} to this supplier was sent within {ctx.policy.reminder_cooldown_days} days")
    return APPROVAL


def _loan_application(business_id: int, p: SubmitLoanApplicationParams, ctx: GateContext) -> GateResult:
    if p.option_id not in LOAN_PRODUCTS:
        return deny(f"{p.option_id!r} is not a sandbox loan product")
    limit = loan_limit(ctx.session, business_id, p.option_id, ctx.today)
    if p.amount > limit:
        return deny(f"amount {p.amount} exceeds the {p.option_id} limit {limit} (cents)")
    return APPROVAL
