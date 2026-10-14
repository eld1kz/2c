"""Reminder and supplier terms-request drafts from fixed templates (Phase 3 D2, Phase 4).

The text is built only from structured records (invoice number, amount, dates, names, payment
stats), never from invoice notes or LLM output, so untrusted document text cannot reach an
outgoing email (T1).
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


def terms_request_draft(business: Business, supplier: Counterparty, current_terms_days: int | None,
                        extension_days: int, today: date) -> Draft:
    """Ask a supplier for `extension_days` more days on payment terms, from invoices issued `today` on."""
    stats = supplier.stats or {}
    record = (f"We have paid all {stats['invoices_count']} of our recent invoices to you on time, and we value "
              "the relationship. " if stats.get("invoices_count") and stats.get("on_time_rate") == 1 else "")
    if current_terms_days is None:
        terms = f"extend our payment terms by {extension_days} days"
    else:
        terms = (f"extend our payment terms from net {current_terms_days} to net "
                 f"{current_terms_days + extension_days} days")
    start = f"{today:%B} {today.day}, {today.year}"
    subject = f"Request to extend payment terms by {extension_days} days"
    body = (f"Hello {supplier.name},\n\n{record}To smooth our cash flow over the coming weeks, could you {terms}, "
            f"starting with invoices issued from {start}? Please let us know whether this works for you.\n\n"
            f"Kind regards,\n{business.name}")
    return Draft(subject, body)
