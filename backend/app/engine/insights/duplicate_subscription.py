"""DUPLICATE_SUBSCRIPTION: ≥ 2 active `software` series whose vendors share a name root (first
word of normalized_name) with amounts within 10%. Impact = annual cost of the extra series.

The SPEC's optional LLM `same_service` check is not implemented; root matching only.
"""

from collections import defaultdict

from app.db.models import Cadence, Category, InsightType
from app.engine.forecast import Forecast
from app.engine.insights.base import PER_YEAR, InsightSpec, annual_severity
from app.engine.snapshot import SeriesFacts, Snapshot

AMOUNT_TOLERANCE_PCT = 10
PER_YEAR_COUNT = {Cadence.weekly: 52, Cadence.monthly: 12, Cadence.quarterly: 4}


def detect(snap: Snapshot, forecast: Forecast) -> list[InsightSpec]:
    by_root: dict[str, list[SeriesFacts]] = defaultdict(list)
    for s in snap.series:
        if s.category == Category.software:
            by_root[snap.counterparties[s.counterparty_id].normalized_name.split()[0]].append(s)

    out = []
    for root, group in sorted(by_root.items()):
        keep, *others = sorted(group, key=lambda s: s.id)
        extra = [s for s in others
                 if abs(abs(s.amount) - abs(keep.amount)) * 100 <= abs(keep.amount) * AMOUNT_TOLERANCE_PCT]
        if not extra:
            continue
        impact = sum(abs(s.amount) * PER_YEAR_COUNT[s.cadence] for s in extra)
        names = " and ".join(snap.counterparties[s.counterparty_id].name for s in [keep, *extra])
        out.append(InsightSpec(
            type=InsightType.DUPLICATE_SUBSCRIPTION,
            severity=annual_severity(impact),
            title=f"Possible duplicate subscription: {names}",
            impact_amount=impact,
            impact_period=PER_YEAR,
            evidence_ids=(*(f"recurring_series:{s.id}" for s in [keep, *extra]),
                          *(f"transaction:{t}" for s in [keep, *extra] for t in s.transaction_ids)),
        ))
    return out
