"""UNUSUAL_EXPENSE: an outflow > 3× the median outflow of its category (≥ 5 samples).

The median uses every outflow in the category, but only one-off spending is flagged: members of a
recurring series and invoice-linked payments are expected by definition (otherwise, e.g., monthly
merchant fees would be flagged against small bank fees in the same category).
"""

import statistics
from collections import defaultdict

from app.db.models import Category, InsightType, Severity
from app.engine.forecast import Forecast
from app.engine.insights.base import ONCE, InsightSpec, money
from app.engine.snapshot import Snapshot, TxFacts

MULTIPLE = 3
MIN_SAMPLES = 5


def detect(snap: Snapshot, forecast: Forecast) -> list[InsightSpec]:
    expected = {tx_id for s in snap.series for tx_id in s.transaction_ids}
    by_category: dict[Category, list[TxFacts]] = defaultdict(list)
    for t in snap.transactions:
        if t.amount < 0 and t.category is not None:
            by_category[t.category].append(t)

    out = []
    for category, txs in sorted(by_category.items()):
        if len(txs) < MIN_SAMPLES:
            continue
        median = statistics.median_low([-t.amount for t in txs])
        for t in txs:
            if t.id in expected or t.invoice_id is not None or -t.amount <= MULTIPLE * median:
                continue
            out.append(InsightSpec(
                type=InsightType.UNUSUAL_EXPENSE,
                severity=Severity.med,
                title=(f"Unusual {category.value} expense: {money(-t.amount, snap.currency)} on {t.date:%b %d} "
                       f"(typical {money(median, snap.currency)})"),
                impact_amount=-t.amount - median,
                impact_period=ONCE,
                evidence_ids=(f"transaction:{t.id}",),
            ))
    return out
