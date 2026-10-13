"""PRICE_CREEP: a supplier's unit price for one SKU up > 10% across invoices issued in the
trailing 120 days. Impact = price rise × quantity bought in the window, annualized (× 365/120).
"""

from collections import defaultdict
from datetime import timedelta

from app.db.models import InsightType, InvoiceDirection, InvoiceStatus
from app.engine.forecast import Forecast
from app.engine.insights.base import PER_YEAR, InsightSpec, annual_severity, money
from app.engine.snapshot import InvoiceFacts, InvoiceLineFacts, Snapshot

WINDOW_DAYS = 120
RISE_PCT = 10


def detect(snap: Snapshot, forecast: Forecast) -> list[InsightSpec]:
    start = snap.as_of - timedelta(days=WINDOW_DAYS)
    points: dict[tuple[int, str], list[tuple[InvoiceFacts, InvoiceLineFacts]]] = defaultdict(list)
    for inv in snap.invoices:
        if inv.direction != InvoiceDirection.payable or inv.status == InvoiceStatus.void:
            continue
        if start <= inv.issue_date < snap.as_of:
            for line in inv.lines:
                if line.sku is not None:
                    points[(inv.counterparty_id, line.sku)].append((inv, line))

    out = []
    for (cp_id, sku), group in sorted(points.items()):
        group.sort(key=lambda p: (p[0].issue_date, p[0].id))
        first, last = group[0][1].unit_price, group[-1][1].unit_price
        if (last - first) * 100 <= first * RISE_PCT:
            continue
        quantity = sum(line.quantity for _, line in group)
        impact = (last - first) * quantity * 365 // WINDOW_DAYS
        name = snap.counterparties[cp_id].name
        out.append(InsightSpec(
            type=InsightType.PRICE_CREEP,
            severity=annual_severity(impact),
            title=(f"{name} raised {sku} by {(last - first) * 100 // first}% in {WINDOW_DAYS} days "
                   f"({money(first, snap.currency)} → {money(last, snap.currency)} per unit)"),
            impact_amount=impact,
            impact_period=PER_YEAR,
            evidence_ids=tuple(f"invoice:{inv.id}" for inv, _ in reversed(group)),  # newest price first
        ))
    return out
