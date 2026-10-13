"""CASH_GAP: some forecast week closes below min_cash_buffer. One insight per forecast covering the
first to last week below the buffer; impact = shortfall at the lowest week; high if cash goes < 0.

Evidence: the outflow sources of the first breach week and the lowest week, largest outflow first.
"""

from app.db.models import InsightType, Severity
from app.engine.forecast import Forecast
from app.engine.insights.base import ONCE, InsightSpec, money
from app.engine.snapshot import Snapshot


def detect(snap: Snapshot, forecast: Forecast) -> list[InsightSpec]:
    gap = forecast.gap()
    if gap is None:
        return []
    low = forecast.min_cash_buffer - gap.amount
    outflows = sorted(
        (ln for week in sorted({gap.first_week, gap.low_week}) for ln in forecast.lines_in(week) if ln.amount < 0),
        key=lambda ln: ln.amount,
    )
    evidence = tuple(dict.fromkeys(s for ln in outflows for s in ln.source_ids))
    buffer = money(forecast.min_cash_buffer, forecast.currency)
    return [InsightSpec(
        type=InsightType.CASH_GAP,
        severity=Severity.high if low < 0 else Severity.med,
        title=(f"Cash falls below the {buffer} buffer in week {gap.first_week} (from {gap.start:%b %d}); "
               f"lowest {money(low, forecast.currency)} in week {gap.low_week}"),
        impact_amount=gap.amount,
        impact_period=ONCE,
        evidence_ids=evidence,
    )]
