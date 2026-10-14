"""Sandbox bank: records payments. Called only by services/action_service.py after approval.

The payee is always the stored counterparty; there is no beneficiary or account input.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Action, Invoice, PaymentStatus, SandboxPayment
from app.policy.tiers import SchedulePaymentParams


def execute_payment(session: Session, action: Action, params: SchedulePaymentParams, now: datetime) -> SandboxPayment:
    invoice = session.get(Invoice, params.invoice_id)
    payment = SandboxPayment(
        business_id=action.business_id,
        action_id=action.id,
        payee_counterparty_id=params.payee_counterparty_id,
        invoice_id=invoice.id,
        amount=params.amount,
        currency=invoice.currency,
        scheduled_date=params.date,
        status=PaymentStatus.executed,
        created_at=now,
        executed_at=now,
    )
    session.add(payment)
    session.flush()
    return payment
