"""ActionService: the ONLY path that executes anything (CLAUDE.md rule 2, SPEC §8).

propose → policy gate → Action `proposed` (needs approval) or `denied`.
approve → RBAC → `approved` → gate re-check → sandbox write → `executed` (or `denied`/`failed`).
Every proposal, decision, refusal, execution and replay writes an AuditEvent. Executing an action
that already ran returns its original result and writes nothing to the sandbox. Decisions lock and
re-read the Action row first, so two concurrent approvals cannot both act on a stale `proposed`.
"""

import statistics
import uuid
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log as audit
from app.auth.rbac import can_approve
from app.db.models import (
    Action,
    ActionStatus,
    Business,
    Counterparty,
    CounterpartyKind,
    Invoice,
    InvoiceDirection,
    InvoiceStatus,
    Policy,
    ProposedBy,
    Tier,
    User,
)
from app.policy import gate
from app.policy.gate import Actor, ActionRequest, Decision, GateContext
from app.policy.limits import OPEN_STATUSES, invoice_outstanding
from app.policy.tiers import (
    EXECUTE_PARAMS,
    SchedulePaymentParams,
    SendReminderParams,
    SendTermsRequestParams,
    SubmitLoanApplicationParams,
    tier_of,
)
from app.sandbox import bank, loans, outbox
from app.services.drafts import Tone, reminder_draft, terms_request_draft

MIN_TERMS_EXTENSION_DAYS = 7
MAX_TERMS_EXTENSION_DAYS = 60


class ActionError(Exception):
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFound(ActionError):
    status_code = 404


class Forbidden(ActionError):
    status_code = 403


class InvalidState(ActionError):
    status_code = 409


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def actor_for(user: User, via_agent: bool = False) -> Actor:
    return Actor(business_id=user.business_id, user_id=user.id, role=user.role, via_agent=via_agent)


class ActionService:
    def __init__(self, session: Session, today: date, clock: Callable[[], datetime] = utc_now) -> None:
        self.session = session
        self.today = today  # DEMO_TODAY, for days-past-due rules
        self.clock = clock

    # --- helpers -----------------------------------------------------------------------------

    def _ctx(self, business_id: int) -> GateContext:
        return GateContext(self.session, self.session.get(Policy, business_id), self.clock(), self.today)

    def _audit(self, actor: str, event_type: str, action: Action | None, **extra: Any) -> None:
        payload: dict[str, Any] = dict(extra)
        if action is not None:
            payload |= {"action_id": action.id, "business_id": action.business_id, "tool": action.tool,
                        "status": action.status.value}
        audit.append(self.session, actor, event_type, payload, now=self.clock())

    def _locked(self, user: User, action_id: int) -> Action:
        """Row-locked, freshly read Action of the user's business (SELECT … FOR UPDATE on Postgres)."""
        action = self.session.scalar(
            select(Action).where(Action.id == action_id).with_for_update()
            .execution_options(populate_existing=True))
        if action is None or action.business_id != user.business_id:
            self._audit(actor_for(user).label, "action_not_found", None, business_id=user.business_id,
                        requested_action_id=action_id)
            raise NotFound(f"action {action_id} not found")
        return action

    def _reject_input(self, actor: Actor, reason: str) -> None:
        self._audit(actor.label, "action_input_rejected", None, business_id=actor.business_id, reason=reason)
        raise ActionError(reason)

    # --- propose -----------------------------------------------------------------------------

    def propose(self, actor: Actor, tool: str, params: dict[str, Any], *, idempotency_key: str,
                rationale: str = "", evidence_ids: tuple[str, ...] = ()) -> Action:
        problem = audit.json_problem([tool, params, rationale, list(evidence_ids), idempotency_key])
        if problem is not None:
            self._reject_input(actor, f"invalid input: {problem}")  # checked before anything is written
        tier = tier_of(tool)
        if tier in (Tier.READ, Tier.SUGGEST):
            self._reject_input(actor, f"{tool} is a {tier.value} tool, not an action to approve")
        existing = self.session.scalar(select(Action).where(Action.business_id == actor.business_id,
                                                            Action.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.tool != tool or existing.params != params:
                self._audit(actor.label, "idempotency_conflict", existing)
                raise InvalidState("idempotency key already used for a different action")
            self._audit(actor.label, "action_propose_replayed", existing)
            return existing

        result = gate.check(ActionRequest(actor.business_id, tool, params), actor, self._ctx(actor.business_id))
        denied = result.decision == Decision.DENY
        action = Action(
            business_id=actor.business_id,
            proposed_by=ProposedBy.agent if actor.via_agent else ProposedBy.user,
            tool=tool,
            params=params,
            tier=Tier.EXECUTE,
            status=ActionStatus.denied if denied else ActionStatus.proposed,
            rationale=rationale,
            evidence_ids=list(evidence_ids),
            idempotency_key=idempotency_key,
            result={"denied": result.reason, "stage": "propose"} if denied else None,
        )
        self.session.add(action)
        self.session.flush()
        self._audit(actor.label, "action_denied" if denied else "action_proposed", action,
                    params=params, rationale=rationale, evidence_ids=list(evidence_ids),
                    decision=result.decision.value, reason=result.reason)
        return action

    # --- decide ------------------------------------------------------------------------------

    def approve(self, user: User, action_id: int) -> Action:
        action = self._locked(user, action_id)
        actor = actor_for(user)
        if not can_approve(user.role, action.tool, self.session.get(Policy, user.business_id)):
            self._audit(actor.label, "approval_forbidden", action, role=user.role.value)
            raise Forbidden(f"role {user.role.value} may not approve {action.tool}")
        if action.status == ActionStatus.executed:
            self._audit(actor.label, "execute_replayed", action)
            return action
        if action.status != ActionStatus.proposed:
            self._audit(actor.label, "approval_invalid_state", action)
            raise InvalidState(f"action is {action.status.value}, not proposed")
        action.status, action.decided_by, action.decided_at = ActionStatus.approved, user.id, self.clock()
        self._audit(actor.label, "action_approved", action)
        return self._execute(actor, action)

    def reject(self, user: User, action_id: int) -> Action:
        action = self._locked(user, action_id)
        actor = actor_for(user)
        if not can_approve(user.role, action.tool, self.session.get(Policy, user.business_id)):
            self._audit(actor.label, "rejection_forbidden", action, role=user.role.value)
            raise Forbidden(f"role {user.role.value} may not reject {action.tool}")
        if action.status != ActionStatus.proposed:
            self._audit(actor.label, "rejection_invalid_state", action)
            raise InvalidState(f"action is {action.status.value}, not proposed")
        action.status, action.decided_by, action.decided_at = ActionStatus.rejected, user.id, self.clock()
        self._audit(actor.label, "action_rejected", action)
        return action

    def execute(self, user: User, action_id: int) -> Action:
        """Run an approved action; an already-executed one returns its original result (A4)."""
        action = self._locked(user, action_id)
        actor = actor_for(user)
        if not can_approve(user.role, action.tool, self.session.get(Policy, user.business_id)):
            self._audit(actor.label, "execute_forbidden", action, role=user.role.value)
            raise Forbidden(f"role {user.role.value} may not execute {action.tool}")
        return self._execute(actor, action)

    def _execute(self, actor: Actor, action: Action) -> Action:
        if action.status == ActionStatus.executed:
            self._audit(actor.label, "execute_replayed", action)
            return action
        if action.status != ActionStatus.approved:
            self._audit(actor.label, "execute_invalid_state", action)
            raise InvalidState(f"action is {action.status.value}, not approved")
        recheck = gate.check(ActionRequest(action.business_id, action.tool, action.params, action.id), actor,
                             self._ctx(action.business_id))
        if recheck.decision == Decision.DENY:
            action.status, action.result = ActionStatus.denied, {"denied": recheck.reason, "stage": "execute"}
            self._audit(actor.label, "action_denied", action, decision=recheck.decision.value, reason=recheck.reason)
            return action
        try:
            with self.session.begin_nested():
                action.result = self._run(action)
        except Exception as e:  # sandbox failure: record it, never retry silently
            action.status, action.result = ActionStatus.failed, {"error": type(e).__name__}
            self._audit(actor.label, "action_failed", action, error=type(e).__name__)
            return action
        action.status = ActionStatus.executed
        self._audit(actor.label, "action_executed", action, result=action.result)
        return action

    def _run(self, action: Action) -> dict[str, Any]:
        params = EXECUTE_PARAMS[action.tool].model_validate(action.params)
        now = self.clock()
        match params:
            case SchedulePaymentParams():
                payment = bank.execute_payment(self.session, action, params, now)
                return {"sandbox_payment_id": payment.id, "payee_counterparty_id": payment.payee_counterparty_id,
                        "invoice_id": payment.invoice_id, "amount": payment.amount, "currency": payment.currency,
                        "status": payment.status.value}
            case SendReminderParams():
                draft = self.session.get(Action, params.draft_id)
                invoice = self.session.get(Invoice, params.invoice_id)
                customer = self.session.get(Counterparty, invoice.counterparty_id)
                email = outbox.send_email(self.session, action, customer, draft.result["subject"],
                                          draft.result["body"], now)
                return {"sandbox_email_id": email.id, "to_counterparty_id": customer.id, "invoice_id": invoice.id,
                        "status": email.status.value}
            case SendTermsRequestParams():
                draft = self.session.get(Action, params.draft_id)
                supplier = self.session.get(Counterparty, params.counterparty_id)
                email = outbox.send_email(self.session, action, supplier, draft.result["subject"],
                                          draft.result["body"], now)
                return {"sandbox_email_id": email.id, "to_counterparty_id": supplier.id, "status": email.status.value}
            case SubmitLoanApplicationParams():
                business = self.session.get(Business, action.business_id)
                application = loans.submit_application(self.session, action, params, business.base_currency, now)
                return {"sandbox_loan_application_id": application.id, "option_id": application.option_id,
                        "amount": application.amount, "currency": application.currency,
                        "status": application.status.value}
        raise ActionError(f"no executor for {action.tool}")  # pragma: no cover

    # --- drafts (SUGGEST) --------------------------------------------------------------------

    def _check_draft(self, actor: Actor, tool: str) -> None:
        result = gate.check(ActionRequest(actor.business_id, tool, {}), actor, self._ctx(actor.business_id))
        if result.decision == Decision.DENY:
            self._audit(actor.label, "draft_denied", None, business_id=actor.business_id, reason=result.reason)
            raise Forbidden(result.reason)

    def _store_draft(self, actor: Actor, tool: str, params: dict[str, Any], result: dict[str, Any],
                     **audit_extra: Any) -> Action:
        action = Action(
            business_id=actor.business_id,
            proposed_by=ProposedBy.agent if actor.via_agent else ProposedBy.user,
            tool=tool,
            params=params,
            tier=Tier.SUGGEST,
            status=ActionStatus.executed,
            idempotency_key=f"draft:{uuid.uuid4().hex}",
            result={**result, "drafted_at": self.clock().isoformat()},
        )
        self.session.add(action)
        self.session.flush()
        self._audit(actor.label, "draft_created", action, **audit_extra)
        return action

    def record_draft(self, actor: Actor, invoice_id: int, tone: Tone) -> Action:
        """draft_reminder: a templated reminder stored as an executed SUGGEST action."""
        self._check_draft(actor, "draft_reminder")
        invoice = self.session.get(Invoice, invoice_id)
        if (invoice is None or invoice.business_id != actor.business_id
                or invoice.direction != InvoiceDirection.receivable or invoice.status not in OPEN_STATUSES):
            self._audit(actor.label, "draft_denied", None, business_id=actor.business_id,
                        reason=f"open receivable {invoice_id} not found")
            raise NotFound(f"open receivable {invoice_id} not found")
        outstanding = invoice_outstanding(self.session, invoice)
        draft = reminder_draft(self.session.get(Business, actor.business_id),
                               self.session.get(Counterparty, invoice.counterparty_id), invoice,
                               outstanding, Tone(tone), self.today)
        return self._store_draft(actor, "draft_reminder", {"invoice_id": invoice.id, "tone": Tone(tone).value},
                                 {"subject": draft.subject, "body": draft.body, "outstanding": outstanding},
                                 invoice_id=invoice.id)

    def record_terms_draft(self, actor: Actor, counterparty_id: int, extension_days: int) -> Action:
        """draft_terms_request: a templated supplier payment-terms request, stored as an executed
        SUGGEST action. It is a draft only; send_terms_request (EXECUTE, approved by an owner) sends it."""
        self._check_draft(actor, "draft_terms_request")
        supplier = self.session.get(Counterparty, counterparty_id)
        if (supplier is None or supplier.business_id != actor.business_id
                or supplier.kind not in (CounterpartyKind.supplier, CounterpartyKind.both)):
            self._audit(actor.label, "draft_denied", None, business_id=actor.business_id,
                        reason=f"supplier {counterparty_id} not found")
            raise NotFound(f"supplier {counterparty_id} not found")
        if not MIN_TERMS_EXTENSION_DAYS <= extension_days <= MAX_TERMS_EXTENSION_DAYS:
            self._reject_input(actor, f"extension_days must be between {MIN_TERMS_EXTENSION_DAYS} and "
                                      f"{MAX_TERMS_EXTENSION_DAYS}")
        terms = [(i.due_date - i.issue_date).days for i in self.session.scalars(select(Invoice).where(
            Invoice.counterparty_id == supplier.id, Invoice.direction == InvoiceDirection.payable,
            Invoice.status != InvoiceStatus.void))]
        current = statistics.median_low(terms) if terms else None
        draft = terms_request_draft(self.session.get(Business, actor.business_id), supplier, current,
                                    extension_days, self.today)
        return self._store_draft(
            actor, "draft_terms_request", {"counterparty_id": supplier.id, "extension_days": extension_days},
            {"subject": draft.subject, "body": draft.body, "current_terms_days": current,
             "new_terms_days": None if current is None else current + extension_days},
            counterparty_id=supplier.id)
