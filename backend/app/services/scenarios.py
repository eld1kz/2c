"""What-if scenario inputs, shared by the agent's run_what_if / rank_financing tools and the what-if API.

One schema and one set of checks for both callers: dates inside the 13-week horizon, typed-in amounts
non-zero and at most $1,000,000, and every target record (invoice, recurring series) in the caller's
business. Inputs are ids, dates, enums and integer cents only: no free text.
"""

from datetime import date, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.models import Cadence
from app.engine.insights.base import money
from app.engine.whatif import (
    AddRecurring,
    CollectReceivable,
    DelayReceivable,
    OneOff,
    RemoveSeries,
    Scenario,
    ScenarioError,
)
from app.services import ledger

MAX_SCENARIO_CENTS = 100_000_000  # $1,000,000
MAX_SCENARIO_DAYS = 91  # 13 weeks: the forecast horizon
MAX_SCENARIOS = 5


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CollectIn(_In):
    type: Literal["collect_receivable"]
    invoice_id: int
    on: date | None = Field(None, description="collection date; default today (collected now)")


class DelayIn(_In):
    type: Literal["delay_receivable"]
    invoice_id: int
    days: int = Field(ge=1, le=MAX_SCENARIO_DAYS)


class AddRecurringIn(_In):
    type: Literal["add_recurring"]
    amount_cents: int = Field(description="signed cents per occurrence: negative = cost, positive = income; "
                                          "at most $1,000,000 either way")
    cadence: Cadence
    start: date


class OneOffIn(_In):
    type: Literal["one_off"]
    amount_cents: int = Field(description="signed cents: negative = payment out, positive = money in; "
                                          "at most $1,000,000 either way")
    on: date


class RemoveSeriesIn(_In):
    type: Literal["remove_series"]
    series_id: int


ScenarioIn = Annotated[CollectIn | DelayIn | AddRecurringIn | OneOffIn | RemoveSeriesIn, Field(discriminator="type")]


def to_scenarios(items: list[ScenarioIn], today: date) -> list[Scenario]:
    out: list[Scenario] = []
    for s in items:
        match s:
            case CollectIn():
                out.append(CollectReceivable(s.invoice_id, s.on or today))
            case DelayIn():
                out.append(DelayReceivable(s.invoice_id, s.days))
            case AddRecurringIn():
                out.append(AddRecurring(s.amount_cents, s.cadence, s.start))
            case OneOffIn():
                out.append(OneOff(s.amount_cents, s.on))
            case RemoveSeriesIn():
                out.append(RemoveSeries(s.series_id))
    return out


def check_targets(session: Session, business_id: int, currency: str, today: date,
                  scenarios: list[Scenario]) -> None:
    last = today + timedelta(days=MAX_SCENARIO_DAYS)
    for s in scenarios:
        on = getattr(s, "on", None) or getattr(s, "start", None)
        if on is not None and not today <= on <= last:
            raise ScenarioError(f"scenario dates must be between {today} and {last}")
        if isinstance(s, (AddRecurring, OneOff)) and not 0 < abs(s.amount) <= MAX_SCENARIO_CENTS:
            raise ScenarioError(f"scenario amounts must be non-zero and at most "
                                f"{money(MAX_SCENARIO_CENTS, currency)} either way")
        if isinstance(s, (CollectReceivable, DelayReceivable)):
            ref = f"invoice:{s.invoice_id}"
        elif isinstance(s, RemoveSeries):
            ref = f"recurring_series:{s.series_id}"
        else:
            continue
        if not ledger.record_exists(session, business_id, ref):
            raise ScenarioError(f"{ref} not found")
