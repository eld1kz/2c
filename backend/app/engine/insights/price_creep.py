"""PRICE_CREEP: a supplier's unit price for one SKU up > 10% across invoices issued in the
trailing 120 days. Impact = price rise × quantity bought in the window, annualized (× 365/120).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.db.models import InsightType, InvoiceDirection, InvoiceStatus
from app.engine.forecast import Forecast
from app.engine.insights.base import PER_YEAR, InsightSpec, annual_severity, money
from app.engine.snapshot import InvoiceFacts, InvoiceLineFacts, Snapshot

WINDOW_DAYS = 120
RISE_PCT = 10


@dataclass(frozen=True)
class PriceRise:
    counterparty_id: int
    sku: str
    first_price: int  # unit price on the oldest invoice in the window
    last_price: int  # unit price on the newest
    first_date: date
    last_date: date
    quantity: int  # bought in the window
    invoice_ids: tuple[int, ...]  # newest first

    @property
    def pct(self) -> int:
        return (self.last_price - self.first_price) * 100 // self.first_price

    @property
    def annual_impact(self) -> int:
        return (self.last_price - self.first_price) * self.quantity * 365 // WINDOW_DAYS


def price_rises(snap: Snapshot) -> list[PriceRise]:
    """Every (supplier, SKU) whose unit price rose more than RISE_PCT across the trailing window."""
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
        out.append(PriceRise(cp_id, sku, first, last, group[0][0].issue_date, group[-1][0].issue_date,
                             sum(line.quantity for _, line in group), tuple(inv.id for inv, _ in reversed(group))))
    return out


def detect(snap: Snapshot, forecast: Forecast) -> list[InsightSpec]:
    out = []
    for r in price_rises(snap):
        name = snap.counterparties[r.counterparty_id].name
        out.append(InsightSpec(
            type=InsightType.PRICE_CREEP,
            severity=annual_severity(r.annual_impact),
            title=(f"{name} raised {r.sku} by {r.pct}% in {WINDOW_DAYS} days "
                   f"({money(r.first_price, snap.currency)} → {money(r.last_price, snap.currency)} per unit)"),
            impact_amount=r.annual_impact,
            impact_period=PER_YEAR,
            evidence_ids=tuple(f"invoice:{i}" for i in r.invoice_ids),  # newest price first
        ))
    return out
