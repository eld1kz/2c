"""The "Today" home screen (SPEC §6.9): what is safe to spend this week and where last month's money went.

Integer cents, from the snapshot, the base forecast and the cash-basis P&L; nothing is stored.
Safe to spend = cash now − the cushion (minimum cash buffer) − bills due in the next 7 days, where
a bill is a recurring-series payment or an open supplier invoice in forecast week 1 (overdue ones
are already placed there). Expected money in and typical day-to-day spending are left out on
purpose: the figure is what could go out without touching the cushion even if nothing comes in.

The cushion outlook is the one-line headline over Today's 13-week chart: the first week that closes
below the cushion and the lowest week, with how far it is above or below the cushion.
"""

from dataclasses import dataclass
from datetime import date

from app.db.models import ForecastLineKind
from app.engine.forecast import Forecast
from app.engine.insights.base import money
from app.engine.snapshot import Snapshot
from app.engine.statements import PnlLine, ProfitAndLoss

BILL_KINDS = (ForecastLineKind.recurring, ForecastLineKind.ap_due)


@dataclass(frozen=True)
class Bill:
    on: date
    ref: str  # recurring_series:N or invoice:N
    counterparty_id: int | None
    amount: int  # positive = money out


@dataclass(frozen=True)
class SafeToSpend:
    cash: int
    cushion: int
    bills: tuple[Bill, ...]

    @property
    def bills_total(self) -> int:
        return sum(b.amount for b in self.bills)

    @property
    def amount(self) -> int:
        """Signed: below zero means this week's bills already eat into the cushion."""
        return self.cash - self.cushion - self.bills_total

    @property
    def short_by(self) -> int:
        return max(-self.amount, 0)


def _is_bill(line_source: str, kind: ForecastLineKind) -> bool:
    # Projected future invoices (invoice cycles) are `recurring` lines too, but not bills yet.
    return kind == ForecastLineKind.ap_due or line_source.startswith("recurring_series:")


def safe_to_spend(snap: Snapshot, forecast: Forecast) -> SafeToSpend:
    bills = tuple(
        Bill(ln.on, ln.source_ids[0], ln.counterparty_id, -ln.amount)
        for ln in forecast.lines_in(1)
        if ln.kind in BILL_KINDS and ln.amount < 0 and ln.source_ids and _is_bill(ln.source_ids[0], ln.kind)
    )
    return SafeToSpend(snap.cash, snap.min_cash_buffer, bills)


@dataclass(frozen=True)
class Spending:
    pnl: ProfitAndLoss
    lines: tuple[PnlLine, ...]  # COGS and operating expenses, largest first

    @property
    def total(self) -> int:
        return self.pnl.total_cogs + self.pnl.total_operating_expenses


def spending(pnl: ProfitAndLoss) -> Spending:
    lines = sorted((*pnl.cogs, *pnl.operating_expenses), key=lambda ln: (-ln.amount, ln.key))
    return Spending(pnl, tuple(lines))


@dataclass(frozen=True)
class CushionOutlook:
    first_below: date | None  # start of the first week closing below the cushion
    lowest_week: int
    lowest_start: date
    lowest_vs_cushion: int  # lowest closing − cushion (negative = below)
    headline: str
    detail: str


def _day(d: date) -> str:
    return f"{d:%b} {d.day}"


def outlook(forecast: Forecast) -> CushionOutlook:
    below = [w for w in forecast.weeks if w.below_buffer]
    low = min(forecast.weeks, key=lambda w: (w.closing, w.week))
    first = below[0] if below else None
    if first is None:
        headline = f"Cash stays above your cushion for all {len(forecast.weeks)} weeks."
    elif first.week == 1:
        headline = "Cash is below your cushion this week."
    else:
        headline = f"Cash stays above your cushion until {_day(first.start)}."
    gap = low.closing - forecast.min_cash_buffer
    side = "below" if gap < 0 else "above"
    detail = f"Lowest week: {_day(low.start)}, {money(abs(gap), forecast.currency)} {side} your cushion."
    return CushionOutlook(first.start if first else None, low.week, low.start, gap, headline, detail)
