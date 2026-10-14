"""Reminder drafts from a fixed template (Phase 3 D2).

The text is built only from structured records (invoice number, amount, dates, names), never from
invoice notes or LLM output, so untrusted document text cannot reach an outgoing email (T1).
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.db.models import Business, Counterparty, Invoice
from app.engine.insights.base import money


class Tone(StrEnum):
    polite = "polite"
    firm = "firm"


@dataclass(frozen=True)
class Draft:
    subject: str
    body: str


def reminder_draft(business: Business, customer: Counterparty, invoice: Invoice, outstanding: int, tone: Tone,
                   today: date) -> Draft:
    amount = money(outstanding, invoice.currency)
    due = f"{invoice.due_date:%B} {invoice.due_date.day}, {invoice.due_date.year}"
    days = (today - invoice.due_date).days
    if tone == Tone.polite:
        subject = f"Friendly reminder: invoice {invoice.number} ({amount})"
        body = (f"Hello {customer.name},\n\nThis is a friendly reminder that invoice {invoice.number} for {amount}, "
                f"due {due}, is still open. If payment is already on its way, please disregard this note.\n\n"
                f"Thank you,\n{business.name}")
    else:
        overdue = f", and is now {days} days past due" if days > 0 else ""
        subject = f"Payment overdue: invoice {invoice.number} ({amount})"
        body = (f"Hello {customer.name},\n\nInvoice {invoice.number} for {amount} was due on {due}{overdue}. "
                f"Please arrange payment within 7 days, or reply to let us know when we can expect it.\n\n"
                f"Regards,\n{business.name}")
    return Draft(subject, body)
