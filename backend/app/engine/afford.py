"""Can I afford it? (SPEC §6.9): an engine verdict for a new cost, never the model's.

A plan is safe when, with it, no week of the 13-week forecast closes below the cushion
(`min_cash_buffer`). The verdict for the requested start:
- `yes`: safe as asked;
- `not_yet`: not safe as asked, but starting it at a later week start inside the horizon is;
  `earliest_safe_start` is the first such date;
- `no`: no start date inside the 13 weeks is safe.
Only what the forecast can see counts: a cost starting near the end of the horizon is judged on
the weeks left. `scenarios_at(day)` builds the plan's scenarios starting on `day`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.engine.forecast import Forecast, horizon_end
from app.engine.whatif import Scenario, WhatIfResult, run_what_if

Verdict = Literal["yes", "not_yet", "no"]


@dataclass(frozen=True)
class Affordability:
    verdict: Verdict
    requested_start: date
    earliest_safe_start: date | None
    result: WhatIfResult  # the plan as asked

    @property
    def base_weeks_below(self) -> tuple[int, ...]:
        return tuple(w.week for w in self.result.base.weeks if w.below_buffer)

    @property
    def weeks_below_with_it(self) -> tuple[int, ...]:
        return tuple(w.week for w in self.result.scenario.weeks if w.below_buffer)


def _safe(result: WhatIfResult) -> bool:
    return not any(w.below_buffer for w in result.scenario.weeks)


def affordability(base: Forecast, scenarios_at: Callable[[date], list[Scenario]], start: date) -> Affordability:
    asked = run_what_if(base, scenarios_at(start))
    if _safe(asked):
        return Affordability("yes", start, start, asked)
    day, end = start + timedelta(days=7), horizon_end(base.as_of)
    while day <= end:
        if _safe(run_what_if(base, scenarios_at(day))):
            return Affordability("not_yet", start, day, asked)
        day += timedelta(days=7)
    return Affordability("no", start, None, asked)
