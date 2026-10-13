"""Future invoices projected from a counterparty's regular invoicing (wholesale AR, supplier AP).

A cycle is ≥3 invoices for one (counterparty, direction) issued monthly (30 ± 4 days) or at a
fixed gap of 7–31 days (± 2). Next issue dates step on from the latest real invoice, so an
invoice that already exists — open or paid — is never projected again. Amount per line: SKU
lines use the latest unit price × median quantity; lines without a SKU use the median total.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.db.models import InvoiceDirection, InvoiceStatus
from app.engine.recurring import add_months
from app.engine.snapshot import InvoiceFacts

MIN_INVOICES = 3
MONTHLY_DAYS, MONTHLY_TOLERANCE = 30, 4
FIXED_GAP_RANGE, FIXED_TOLERANCE = (7, 31), 2
BASIS_INVOICES = 3  # most recent invoices cited as the projection's source


@dataclass(frozen=True)
class ProjectedInvoice:
    counterparty_id: int
    direction: InvoiceDirection
    issue_date: date
    due_date: date
    amount: int  # unsigned
    basis_ids: tuple[int, ...]


def _step(gaps: list[int]) -> int | None:
    """0 = monthly; n > 0 = fixed n-day gap; None = irregular."""
    g = statistics.median_low(gaps)
    if abs(g - MONTHLY_DAYS) <= MONTHLY_TOLERANCE and all(abs(x - g) <= MONTHLY_TOLERANCE for x in gaps):
        return 0
    lo, hi = FIXED_GAP_RANGE
    if lo <= g <= hi and all(abs(x - g) <= FIXED_TOLERANCE for x in gaps):
        return g
    return None


def _amount(group: list[InvoiceFacts]) -> int:
    latest = group[-1]
    total = 0
    if any(line.sku is None for line in latest.lines):
        total += statistics.median_low([sum(ln.quantity * ln.unit_price for ln in i.lines if ln.sku is None) for i in group])
    for line in latest.lines:
        if line.sku is not None:
            qty = statistics.median_low([ln.quantity for i in group for ln in i.lines if ln.sku == line.sku])
            total += qty * line.unit_price
    return total


def project_invoices(invoices: tuple[InvoiceFacts, ...], as_of: date, end: date) -> list[ProjectedInvoice]:
    """Invoices expected to be issued in [as_of, end]."""
    groups: dict[tuple[int, InvoiceDirection], list[InvoiceFacts]] = defaultdict(list)
    for inv in invoices:
        if inv.status != InvoiceStatus.void:
            groups[(inv.counterparty_id, inv.direction)].append(inv)

    out: list[ProjectedInvoice] = []
    for (cp_id, direction), group in sorted(groups.items()):
        group.sort(key=lambda i: (i.issue_date, i.id))
        if len(group) < MIN_INVOICES:
            continue
        gaps = [(b.issue_date - a.issue_date).days for a, b in zip(group, group[1:])]
        step = _step(gaps)
        if step is None:
            continue
        latest = group[-1].issue_date
        if as_of > latest + timedelta(days=2 * (step or MONTHLY_DAYS)):
            continue  # the relationship has gone quiet
        terms = timedelta(days=statistics.median_low([(i.due_date - i.issue_date).days for i in group]))
        amount = _amount(group)
        basis = tuple(i.id for i in group[-BASIS_INVOICES:])
        n = 1
        while (issue := add_months(latest, n) if step == 0 else latest + timedelta(days=step * n)) <= end:
            if issue >= as_of:
                out.append(ProjectedInvoice(cp_id, direction, issue, issue + terms, amount, basis))
            n += 1
    return out
