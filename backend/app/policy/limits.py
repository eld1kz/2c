"""Numeric limits and balances the gate checks against. Reads only; never writes."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Invoice, InvoiceDirection, InvoiceStatus, PaymentStatus, SandboxPayment, Transaction
from app.engine.financing import FACTORING_ADVANCE_PCT, LOAN_MAX, OVERDRAFT_LIMIT

OPEN_STATUSES = (InvoiceStatus.open, InvoiceStatus.overdue)
FACTORING_MAX_DAYS_PAST_DUE = 30
FIXED_LOAN_LIMITS = {"overdraft": OVERDRAFT_LIMIT, "short_term_loan": LOAN_MAX}
LOAN_PRODUCTS = (*FIXED_LOAN_LIMITS, "invoice_factoring")


def invoice_outstanding(session: Session, invoice: Invoice) -> int:
    """Total − payments already applied: linked bank transactions and sandbox payments made."""
    banked = session.scalar(
        select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(Transaction.invoice_id == invoice.id))
    sandboxed = session.scalar(
        select(func.coalesce(func.sum(SandboxPayment.amount), 0)).where(
            SandboxPayment.invoice_id == invoice.id,
            SandboxPayment.status.in_((PaymentStatus.scheduled, PaymentStatus.executed)),
        ))
    return max(invoice.total - int(banked) - int(sandboxed), 0)  # Postgres SUM() returns Decimal


def loan_limit(session: Session, business_id: int, option_id: str, today: date) -> int:
    """Largest amount a sandbox loan product will accept; factoring is bounded by eligible AR."""
    if option_id in FIXED_LOAN_LIMITS:
        return FIXED_LOAN_LIMITS[option_id]
    receivables = session.scalars(select(Invoice).where(
        Invoice.business_id == business_id,
        Invoice.direction == InvoiceDirection.receivable,
        Invoice.status.in_(OPEN_STATUSES),
    ))
    eligible = sum(invoice_outstanding(session, i) for i in receivables
                   if (today - i.due_date).days <= FACTORING_MAX_DAYS_PAST_DUE)
    return eligible * FACTORING_ADVANCE_PCT // 100
