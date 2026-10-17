"""ActionService: propose → gate → approve → sandbox → audit (SPEC §8, A1–A4)."""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.audit.verify import verify_chain
from app.db.models import (
    Action,
    ActionStatus,
    AuditEvent,
    Invoice,
    PaymentStatus,
    Policy,
    SandboxEmail,
    SandboxLoanApplication,
    SandboxPayment,
)
from app.sandbox import bank
from app.policy.tiers import SchedulePaymentParams
from app.services.action_service import ActionError, Forbidden, InvalidState, NotFound
from tests.conftest import Demo


def _events(demo: Demo) -> list[str]:
    return list(demo.session.scalars(select(AuditEvent.event_type).order_by(AuditEvent.seq)))


def _count(demo: Demo, model: type) -> int:
    return demo.session.scalar(select(func.count()).select_from(model))


def _pay_verde(demo: Demo, key: str = "pay-verde-5513", amount: int = 219_600) -> Action:
    return demo.service.propose(demo.actor("owner"), "schedule_payment", {
        "payee_counterparty_id": demo.counterparties["Verde Green Coffee Imports"].id,
        "invoice_id": demo.invoices["VGC-5513"].id, "amount": amount, "date": "2026-10-08",
    }, idempotency_key=key, rationale="Pay the open bean invoice on its due date",
        evidence_ids=(f"invoice:{demo.invoices['VGC-5513'].id}",))


def test_payment_flow_executes_once_to_stored_payee(demo: Demo) -> None:
    action = _pay_verde(demo)
    assert (action.status, action.proposed_by, action.tier) == ("proposed", "user", "EXECUTE")
    assert _count(demo, SandboxPayment) == 0  # nothing happens before approval
    action = demo.service.approve(demo.users["owner"], action.id)
    assert action.status == "executed" and action.decided_by == demo.users["owner"].id
    payment = demo.session.scalar(select(SandboxPayment))
    assert (payment.payee_counterparty_id, payment.invoice_id, payment.amount, payment.status) == (
        demo.counterparties["Verde Green Coffee Imports"].id, demo.invoices["VGC-5513"].id, 219_600,
        PaymentStatus.executed)
    assert action.result["sandbox_payment_id"] == payment.id
    assert _events(demo) == ["action_proposed", "action_approved", "action_executed"]


def test_a4_executing_twice_returns_original_result(demo: Demo) -> None:
    action = demo.service.approve(demo.users["owner"], _pay_verde(demo).id)
    first = dict(action.result)
    again = demo.service.execute(demo.users["owner"], action.id)
    approved_again = demo.service.approve(demo.users["owner"], action.id)
    assert again.result == approved_again.result == first
    assert _count(demo, SandboxPayment) == 1
    assert _events(demo)[-2:] == ["execute_replayed", "execute_replayed"]


def test_a4_db_rejects_second_sandbox_payment_for_one_action(demo: Demo) -> None:
    action = demo.service.approve(demo.users["owner"], _pay_verde(demo).id)
    params = SchedulePaymentParams.model_validate(action.params)
    with pytest.raises(IntegrityError):
        bank.execute_payment(demo.session, action, params, demo.clock())


def test_idempotency_key_returns_the_same_action(demo: Demo) -> None:
    first = _pay_verde(demo)
    assert _pay_verde(demo).id == first.id
    assert _count(demo, Action) == 1
    with pytest.raises(InvalidState):
        demo.service.propose(demo.actor("owner"), "submit_loan_application", {"option_id": "overdraft", "amount": 1},
                             idempotency_key="pay-verde-5513")


def test_a1_gate_denial_is_recorded_and_audited(demo: Demo) -> None:
    action = demo.service.propose(demo.actor("owner"), "schedule_payment", {
        "payee_counterparty_id": demo.counterparties["QuickShip Logistics"].id,
        "invoice_id": demo.invoices["QS-2291"].id, "amount": 465_000, "date": "2026-10-10",
    }, idempotency_key="a1-forced")
    assert action.status == "denied" and "outstanding balance 46500" in action.result["denied"]
    event = demo.session.scalar(select(AuditEvent).order_by(AuditEvent.seq.desc()))
    assert (event.event_type, event.payload["decision"], event.payload["action_id"]) == (
        "action_denied", "DENY", action.id)
    with pytest.raises(InvalidState):
        demo.service.approve(demo.users["owner"], action.id)  # a denied action can never run
    assert _count(demo, SandboxPayment) == 0


def test_a2_over_limit_denied_with_reason(demo: Demo) -> None:
    action = _pay_verde(demo, "a2", amount=900_000)
    assert action.status == "denied" and "max_single_payment" in action.result["denied"]


def test_a3_viewer_cannot_approve_and_it_is_audited(demo: Demo) -> None:
    action = _pay_verde(demo)
    with pytest.raises(Forbidden):
        demo.service.approve(demo.users["viewer"], action.id)
    with pytest.raises(Forbidden):
        demo.service.reject(demo.users["viewer"], action.id)
    assert _events(demo)[-2:] == ["approval_forbidden", "rejection_forbidden"]
    assert demo.session.get(Action, action.id).status == "proposed"


def test_accountant_approves_reminders_but_not_payments(demo: Demo) -> None:
    with pytest.raises(Forbidden):
        demo.service.approve(demo.users["accountant"], _pay_verde(demo).id)
    inv = demo.invoices["INV-1042"]
    draft = demo.service.record_draft(demo.actor("accountant"), inv.id, "firm")
    reminder = demo.service.propose(demo.actor("accountant"), "send_reminder",
                                    {"invoice_id": inv.id, "draft_id": draft.id}, idempotency_key="p1-reminder")
    reminder = demo.service.approve(demo.users["accountant"], reminder.id)
    email = demo.session.scalar(select(SandboxEmail))
    assert reminder.status == "executed" and email.to_address == "ap@harborlane.example"
    assert "INV-1042" in email.subject and "45 days past due" in email.body and "$4,800.00" in email.body


def test_terms_request_is_sent_once_to_the_suppliers_stored_contact(demo: Demo) -> None:
    verde = demo.counterparties["Verde Green Coffee Imports"]
    draft = demo.service.record_terms_draft(demo.actor("owner"), verde.id, 30)
    params = {"counterparty_id": verde.id, "draft_id": draft.id}
    denied = demo.service.propose(demo.actor("accountant"), "send_terms_request", params, idempotency_key="t-acc")
    assert denied.status == "denied"  # owner only
    action = demo.service.propose(demo.actor("owner"), "send_terms_request", params, idempotency_key="terms-1")
    assert action.status == "proposed"
    with pytest.raises(Forbidden):
        demo.service.approve(demo.users["accountant"], action.id)
    action = demo.service.approve(demo.users["owner"], action.id)
    (email,) = demo.session.scalars(select(SandboxEmail))
    assert action.status == "executed" and action.result["sandbox_email_id"] == email.id
    assert email.to_address == "ar@verdegreen.example"
    assert (email.subject, email.body) == (draft.result["subject"], draft.result["body"])
    assert "net 14 to net 44" in email.body
    assert demo.service.execute(demo.users["owner"], action.id).result == action.result  # A4: replay
    assert demo.session.scalar(select(func.count()).select_from(SandboxEmail)) == 1

    # Cooldown: a second request to the same supplier within 7 days is denied.
    again = demo.service.record_terms_draft(demo.actor("owner"), verde.id, 30)
    second = demo.service.propose(demo.actor("owner"), "send_terms_request",
                                  {"counterparty_id": verde.id, "draft_id": again.id}, idempotency_key="terms-2")
    assert second.status == "denied" and "within 7 days" in second.result["denied"]


def test_reject_then_cannot_execute(demo: Demo) -> None:
    action = demo.service.reject(demo.users["owner"], _pay_verde(demo).id)
    assert action.status == "rejected"
    with pytest.raises(InvalidState):
        demo.service.execute(demo.users["owner"], action.id)
    assert _events(demo)[-2:] == ["action_rejected", "execute_invalid_state"]


def test_gate_rechecked_at_execution(demo: Demo) -> None:
    first, second = _pay_verde(demo, "half-1", 150_000), _pay_verde(demo, "half-2", 150_000)
    assert (first.status, second.status) == ("proposed", "proposed")  # each fits the $2,196 outstanding alone
    demo.service.approve(demo.users["owner"], first.id)
    second = demo.service.approve(demo.users["owner"], second.id)
    assert second.status == "denied" and second.result["stage"] == "execute"
    assert "outstanding balance 69600" in second.result["denied"]
    assert _count(demo, SandboxPayment) == 1


def test_loan_application_executes_into_sandbox(demo: Demo) -> None:
    action = demo.service.propose(demo.actor("owner"), "submit_loan_application",
                                  {"option_id": "overdraft", "amount": 238_199}, idempotency_key="loan-1")
    action = demo.service.approve(demo.users["owner"], action.id)
    application = demo.session.scalar(select(SandboxLoanApplication))
    assert action.status == "executed" and (application.option_id, application.amount) == ("overdraft", 238_199)


def test_agent_proposals_are_marked_and_cannot_exceed_user_role(demo: Demo) -> None:
    from app.services.action_service import actor_for

    action = demo.service.propose(actor_for(demo.users["owner"], via_agent=True), "schedule_payment",
                                  _pay_verde(demo, "x").params, idempotency_key="agent-1")
    assert action.proposed_by == "agent"
    viewer_agent = demo.service.propose(actor_for(demo.users["viewer"], via_agent=True), "schedule_payment",
                                        action.params, idempotency_key="agent-2")
    assert viewer_agent.status == "denied"
    event = demo.session.scalar(select(AuditEvent).order_by(AuditEvent.seq.desc()))
    assert event.actor == f"agent:user:{demo.users['viewer'].id}"


def test_other_business_actions_are_not_found(demo: Demo) -> None:
    action = _pay_verde(demo)
    action.business_id = demo.business.id + 1
    demo.session.flush()
    with pytest.raises(NotFound):
        demo.service.approve(demo.users["owner"], action.id)


def test_read_and_suggest_tools_are_not_actions(demo: Demo) -> None:
    with pytest.raises(ActionError):
        demo.service.propose(demo.actor("owner"), "run_what_if", {}, idempotency_key="not-an-action")
    with pytest.raises(Forbidden):
        demo.service.record_draft(demo.actor("viewer"), demo.invoices["INV-1042"].id, "polite")


def test_every_decision_is_audited_and_chain_verifies(demo: Demo) -> None:
    demo.service.approve(demo.users["owner"], _pay_verde(demo, "k1", 100_000).id)
    demo.service.reject(demo.users["owner"], _pay_verde(demo, "k2", 100_000).id)
    _pay_verde(demo, "k3", 900_000)
    with pytest.raises(Forbidden):
        demo.service.approve(demo.users["viewer"], _pay_verde(demo, "k4", 1_000).id)
    assert _events(demo) == ["action_proposed", "action_approved", "action_executed", "action_proposed",
                             "action_rejected", "action_denied", "action_proposed", "approval_forbidden"]
    assert verify_chain(demo.session).ok


# --- cumulative daily cap (Policy.max_daily_payments, default $10,000 per payment date) ---------

def _verde_payables(demo: Demo, n: int, total: int = 400_000) -> list[Invoice]:
    verde = demo.counterparties["Verde Green Coffee Imports"]
    invoices = [Invoice(business_id=demo.business.id, direction="payable", counterparty_id=verde.id,
                        number=f"VGC-CAP-{i}", issue_date=date(2026, 9, 28), due_date=date(2026, 10, 12),
                        total=total, currency="USD", status="open") for i in range(n)]
    demo.session.add_all(invoices)
    demo.session.flush()
    return invoices


def _pay(demo: Demo, invoice: Invoice, key: str, day: str = "2026-10-12", amount: int = 400_000) -> Action:
    return demo.service.propose(demo.actor("owner"), "schedule_payment", {
        "payee_counterparty_id": invoice.counterparty_id, "invoice_id": invoice.id, "amount": amount, "date": day,
    }, idempotency_key=key)


def test_daily_cap_two_4000_payments_pass_third_denied(demo: Demo) -> None:
    assert demo.session.get(Policy, demo.business.id).max_daily_payments == 1_000_000
    first, second, third, fourth = _verde_payables(demo, 4)
    for inv, key in ((first, "cap-1"), (second, "cap-2")):
        assert demo.service.approve(demo.users["owner"], _pay(demo, inv, key).id).status == "executed"
    denied = _pay(demo, third, "cap-3")
    assert denied.status == "denied"
    assert denied.result["denied"] == ("payments dated 2026-10-12 would total 1200000, over max_daily_payments "
                                       "1000000 (cents)")
    event = demo.session.scalar(select(AuditEvent).order_by(AuditEvent.seq.desc()))
    assert (event.event_type, event.payload["action_id"]) == ("action_denied", denied.id)
    assert _pay(demo, third, "cap-3-fits", amount=200_000).status == "proposed"  # exactly $10,000 is allowed
    assert _pay(demo, fourth, "cap-4-next-day", day="2026-10-13").status == "proposed"
    assert _count(demo, SandboxPayment) == 2


def test_daily_cap_rechecked_at_execution(demo: Demo) -> None:
    actions = [_pay(demo, inv, f"cap-x{i}") for i, inv in enumerate(_verde_payables(demo, 3))]
    assert [a.status for a in actions] == ["proposed"] * 3  # proposals alone do not use up the cap
    results = [demo.service.approve(demo.users["owner"], a.id) for a in actions]
    assert [r.status for r in results] == ["executed", "executed", "denied"]
    assert results[2].result["stage"] == "execute" and "max_daily_payments" in results[2].result["denied"]
    assert _count(demo, SandboxPayment) == 2


def test_daily_cap_counts_approved_but_not_yet_executed(demo: Demo) -> None:
    pending_inv, executed_inv, new_inv = _verde_payables(demo, 3)
    pending = _pay(demo, pending_inv, "cap-pending")
    pending.status = ActionStatus.approved  # e.g. another request is mid-execution
    demo.service.approve(demo.users["owner"], _pay(demo, executed_inv, "cap-executed").id)
    assert _pay(demo, new_inv, "cap-new").status == "denied"
