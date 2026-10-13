"""LATE_PAYER: an open receivable > 30 days past due, or avg_days_late > 20 over ≥ 3 paid invoices.

One insight per customer. Impact = outstanding on the > 30-day invoices (else all open receivables).
"""

from app.db.models import InsightType, InvoiceDirection, Severity
from app.engine.forecast import Forecast
from app.engine.insights.base import ONCE, InsightSpec, money
from app.engine.snapshot import Snapshot

OVERDUE_DAYS = 30
PATTERN_DAYS_LATE = 20
PATTERN_MIN_INVOICES = 3


def detect(snap: Snapshot, forecast: Forecast) -> list[InsightSpec]:
    out = []
    for cp in sorted(snap.counterparties.values(), key=lambda c: c.id):
        receivables = [i for i in snap.invoices if i.counterparty_id == cp.id and i.direction == InvoiceDirection.receivable]
        open_ar = sorted((i for i in receivables if i.is_open), key=lambda i: i.due_date)
        overdue = [i for i in open_ar if (snap.as_of - i.due_date).days > OVERDUE_DAYS]
        pattern = (cp.stats.get("avg_days_late", 0) > PATTERN_DAYS_LATE
                   and cp.stats.get("invoices_count", 0) >= PATTERN_MIN_INVOICES)
        impact = sum(i.outstanding for i in (overdue or open_ar))
        if not (overdue or pattern) or impact == 0:
            continue
        paid = [i for i in receivables if i.outstanding == 0]
        if overdue:
            worst = overdue[0]
            title = (f"{cp.name}: {worst.number} is {(snap.as_of - worst.due_date).days} days overdue "
                     f"({money(worst.outstanding, snap.currency)})")
        else:
            title = f"{cp.name} pays {cp.stats['avg_days_late']} days late on average"
        out.append(InsightSpec(
            type=InsightType.LATE_PAYER,
            severity=Severity.high if overdue else Severity.med,
            title=title,
            impact_amount=impact,
            impact_period=ONCE,
            evidence_ids=(*(f"invoice:{i.id}" for i in overdue), f"counterparty:{cp.id}",
                          *(f"invoice:{i.id}" for i in paid)),
        ))
    return out
