"""What-if simulator (SPEC §6.5): the base forecast plus `scenario` adjustment lines.

Base lines are never changed or removed; each scenario adds signed `scenario` lines (e.g. a
reversal at the old date and the flow at the new one), so sum-of-lines == closing still holds and
the diff is exactly the scenario lines. Nothing is written to the database.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.db.models import Cadence, ForecastLineKind
from app.engine.forecast import CERTAIN_BP, STEP_MONTHS, Forecast, Line, build, horizon_end
from app.engine.recurring import add_months


@dataclass(frozen=True)
class AddRecurring:
    amount: int  # signed cents per occurrence
    cadence: Cadence
    start: date


@dataclass(frozen=True)
class OneOff:
    amount: int  # signed cents
    on: date


@dataclass(frozen=True)
class DelayReceivable:
    invoice_id: int
    days: int


@dataclass(frozen=True)
class CollectReceivable:
    invoice_id: int
    on: date  # a past date (e.g. the original due date) means "collected now"


@dataclass(frozen=True)
class RemoveSeries:
    series_id: int


Scenario = AddRecurring | OneOff | DelayReceivable | CollectReceivable | RemoveSeries


@dataclass(frozen=True)
class WhatIfResult:
    base: Forecast
    scenario: Forecast
    closing_delta: tuple[int, ...]  # scenario − base closing, per week


class ScenarioError(ValueError):
    pass


def _reverse(line: Line) -> Line:
    return Line(line.on, ForecastLineKind.scenario, -line.face, line.probability_bp, line.source_ids, line.counterparty_id)


def _receivable_lines(base: Forecast, invoice_id: int) -> list[Line]:
    source = f"invoice:{invoice_id}"
    found = [ln for ln in base.lines if ln.kind == ForecastLineKind.ar_expected and ln.source_ids == (source,)]
    if not found:
        raise ScenarioError(f"invoice {invoice_id} is not an open receivable in this forecast")
    return found


def _adjustments(base: Forecast, index: int, scenario: Scenario) -> list[Line]:
    tag = (f"scenario:{index}",)
    match scenario:
        case OneOff(amount, on):
            return [Line(on, ForecastLineKind.scenario, amount, CERTAIN_BP, tag)]
        case AddRecurring(amount, cadence, start):
            first, end = max(start, base.as_of), horizon_end(base.as_of)
            out, n = [], 0
            while (on := first + timedelta(days=7 * n) if cadence == Cadence.weekly
                   else add_months(first, STEP_MONTHS[cadence] * n)) <= end:
                out.append(Line(on, ForecastLineKind.scenario, amount, CERTAIN_BP, tag))
                n += 1
            return out
        case DelayReceivable(invoice_id, days):
            out = []
            for ln in _receivable_lines(base, invoice_id):
                out += [_reverse(ln), Line(ln.on + timedelta(days=days), ForecastLineKind.scenario, ln.face,
                                           ln.probability_bp, ln.source_ids, ln.counterparty_id)]
            return out
        case CollectReceivable(invoice_id, on):
            out = []
            for ln in _receivable_lines(base, invoice_id):
                out += [_reverse(ln), Line(on, ForecastLineKind.scenario, ln.face, CERTAIN_BP, ln.source_ids,
                                           ln.counterparty_id)]
            return out
        case RemoveSeries(series_id):
            source = f"recurring_series:{series_id}"
            found = [ln for ln in base.lines if ln.kind == ForecastLineKind.recurring and source in ln.source_ids]
            if not found:
                raise ScenarioError(f"series {series_id} has no occurrences in this forecast")
            return [_reverse(ln) for ln in found]
    raise ScenarioError(f"unsupported scenario {scenario!r}")


def run_what_if(base: Forecast, scenarios: list[Scenario]) -> WhatIfResult:
    extra = [ln for i, s in enumerate(scenarios) for ln in _adjustments(base, i, s)]
    described = [
        {"type": type(s).__name__, **{k: v.isoformat() if isinstance(v, date) else v for k, v in vars(s).items()}}
        for s in scenarios
    ]
    assumptions = {**base.assumptions, "scenarios": described}
    result = build(base.as_of, base.currency, base.min_cash_buffer, [*base.lines, *extra], assumptions)
    delta = tuple(s.closing - b.closing for s, b in zip(result.weeks, base.weeks))
    return WhatIfResult(base, result, delta)
