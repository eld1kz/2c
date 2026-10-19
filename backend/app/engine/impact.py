"""What approving an action would do to the 13-week forecast (approval card "If you approve").

Pure and integer-only: a summary of a what-if result (the base forecast plus the action's scenario),
compared week by week against the cushion. Nothing is written and no model is called.
"""

from dataclasses import dataclass
from datetime import date

from app.engine.forecast import Forecast, Week
from app.engine.whatif import WhatIfResult


@dataclass(frozen=True)
class Impact:
    lowest_before: int  # cents: the lowest weekly closing
    lowest_before_week: date
    lowest_after: int
    lowest_after_week: date
    weeks_below_before: int  # weeks closing below the cushion
    weeks_below_after: int
    first_below_after: date | None
    closing_delta: int  # week-13 closing, scenario − base
    min_cash_buffer: int


def _lowest(forecast: Forecast) -> Week:
    return min(forecast.weeks, key=lambda w: (w.closing, w.week))


def summarize(result: WhatIfResult) -> Impact:
    before, after = result.base, result.scenario
    low_b, low_a = _lowest(before), _lowest(after)
    first = next((w.start for w in after.weeks if w.below_buffer), None)
    return Impact(
        lowest_before=low_b.closing, lowest_before_week=low_b.start,
        lowest_after=low_a.closing, lowest_after_week=low_a.start,
        weeks_below_before=sum(w.below_buffer for w in before.weeks),
        weeks_below_after=sum(w.below_buffer for w in after.weeks),
        first_below_after=first,
        closing_delta=result.closing_delta[-1] if result.closing_delta else 0,
        min_cash_buffer=before.min_cash_buffer,
    )
