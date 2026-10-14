"""ActionService: propose → gate → approve → sandbox → audit (SPEC §8, A1–A4)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.audit.verify import verify_chain
from app.db.models import (
    Action,
    AuditEvent,
    PaymentStatus,
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
