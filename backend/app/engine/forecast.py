"""13-week cash forecast with traceable lines (SPEC §6.4).

Weeks start on `as_of` (week k covers as_of + 7(k−1) … +6), so no week lies in the past. Week 1
holds one `opening` line (cash at as_of); every week's closing is the sum of all lines up to it.
Each line's `amount` is its face amount weighted by `probability_bp` (basis points), integer only.

Flows and how they are projected:
- recurring: active RecurringSeries stepped on from their last transaction, plus future invoices
  from regular invoicing cycles (app.engine.invoice_cycles).
- ar_expected: open receivables, collected on due date + the customer's avg_days_late. If that
  date has already passed the invoice is at risk: kept in week 1 with probability 0.
- ap_due: open payables on their due date (week 1 if already overdue), probability 1.
- baseline_in / baseline_out: median weekly amount per (category, direction) over the last 8 weeks
  of transactions that are neither invoice-linked nor in an active series (those are above).

Probability is the likelihood of eventual collection, not of on-time payment: timing already
carries the lateness.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Cadence, Category, ForecastLine, ForecastLineKind, ForecastRun, InvoiceDirection
from app.engine.invoice_cycles import project_invoices
from app.engine.recurring import add_months
from app.engine.snapshot import Snapshot

HORIZON_WEEKS = 13
BASELINE_WEEKS = 8
CERTAIN_BP = 10_000
ESTABLISHED_CUSTOMER_BP = 9_500  # has paid history, nothing seriously overdue
AT_RISK_CUSTOMER_BP = 7_000  # has an open receivable more than AT_RISK_DAYS past due
NEW_CUSTOMER_BP = 8_000  # no paid history
AT_RISK_DAYS = 30
BASELINE_EXCLUDED = {Category.transfer}
STEP_MONTHS = {Cadence.monthly: 1, Cadence.quarterly: 3}


@dataclass(frozen=True)
class Line:
    on: date
    kind: ForecastLineKind
    face: int  # signed, before probability
    probability_bp: int
    source_ids: tuple[str, ...]
    counterparty_id: int | None = None

    @property
    def amount(self) -> int:
        weighted = abs(self.face) * self.probability_bp // CERTAIN_BP
        return weighted if self.face >= 0 else -weighted


@dataclass(frozen=True)
class Week:
    week: int
    start: date
    opening: int
    inflows: int
    outflows: int  # negative
    closing: int
    below_buffer: bool


@dataclass(frozen=True)
class Gap:
    """Span from the first to the last week closing below the buffer."""

    first_week: int
    last_week: int
    low_week: int
    amount: int  # buffer − lowest closing
    start: date
    low_week_end: date

    @property
    def days(self) -> int:
        return 7 * (self.last_week - self.first_week + 1)


@dataclass(frozen=True)
class Forecast:
    as_of: date
    currency: str
    min_cash_buffer: int
    lines: tuple[Line, ...]
    weeks: tuple[Week, ...]
    assumptions: dict[str, Any]

    def week_of(self, on: date) -> int:
        return week_of(self.as_of, on)

    def lines_in(self, week: int) -> list[Line]:
        return [ln for ln in self.lines if self.week_of(ln.on) == week]

    def gap(self) -> Gap | None:
        below = [w for w in self.weeks if w.below_buffer]
        if not below:
            return None
        low = min(below, key=lambda w: (w.closing, w.week))
        return Gap(
            first_week=below[0].week,
            last_week=below[-1].week,
            low_week=low.week,
            amount=self.min_cash_buffer - low.closing,
            start=below[0].start,
            low_week_end=low.start + timedelta(days=6),
        )


def week_of(as_of: date, on: date) -> int:
    return max((on - as_of).days, 0) // 7 + 1


def horizon_end(as_of: date) -> date:
    return as_of + timedelta(days=7 * HORIZON_WEEKS - 1)


def build(as_of: date, currency: str, min_cash_buffer: int, lines: list[Line], assumptions: dict[str, Any]) -> Forecast:
    """Clamp lines into the horizon (past → week 1, beyond → dropped) and roll up the weeks."""
    end = horizon_end(as_of)
    kept = sorted(
        (ln if ln.on >= as_of else Line(as_of, ln.kind, ln.face, ln.probability_bp, ln.source_ids, ln.counterparty_id)
         for ln in lines if ln.on <= end),
        key=lambda ln: (ln.on, ln.kind != ForecastLineKind.opening, ln.kind, ln.source_ids, ln.face),
    )
    weeks: list[Week] = []
    balance = 0
    for k in range(1, HORIZON_WEEKS + 1):
        in_week = [ln for ln in kept if week_of(as_of, ln.on) == k]
        opening = balance + sum(ln.amount for ln in in_week if ln.kind == ForecastLineKind.opening)
        flows = [ln.amount for ln in in_week if ln.kind != ForecastLineKind.opening]
        inflows = sum(a for a in flows if a > 0)
        outflows = sum(a for a in flows if a < 0)
        balance = opening + inflows + outflows
        weeks.append(Week(k, as_of + timedelta(days=7 * (k - 1)), opening, inflows, outflows, balance,
                          balance < min_cash_buffer))
    return Forecast(as_of, currency, min_cash_buffer, tuple(kept), tuple(weeks), assumptions)


def collection_bp(snap: Snapshot, counterparty_id: int, at_risk_customers: set[int]) -> int:
    if counterparty_id in at_risk_customers:
        return AT_RISK_CUSTOMER_BP
    if snap.counterparties[counterparty_id].stats.get("invoices_count"):
        return ESTABLISHED_CUSTOMER_BP
    return NEW_CUSTOMER_BP


def _series_lines(snap: Snapshot, end: date) -> list[Line]:
    lines = []
    for s in snap.series:
        n = 1
        while True:
            if s.cadence == Cadence.weekly:
                on = s.last_date + timedelta(days=7 * n)
            else:
                on = add_months(s.last_date, STEP_MONTHS[s.cadence] * n)
            if on > end:
                break
            lines.append(Line(on, ForecastLineKind.recurring, s.amount, CERTAIN_BP, (f"recurring_series:{s.id}",),
                              s.counterparty_id))
            n += 1
    return lines


def _invoice_lines(snap: Snapshot, end: date) -> tuple[list[Line], list[str]]:
    at_risk_customers = {
        i.counterparty_id for i in snap.invoices
        if i.is_open and i.direction == InvoiceDirection.receivable and (snap.as_of - i.due_date).days > AT_RISK_DAYS
    }
    lines: list[Line] = []
    at_risk: list[str] = []
    for inv in snap.invoices:
        if not inv.is_open:
            continue
        source = (f"invoice:{inv.id}",)
        if inv.direction == InvoiceDirection.payable:
            lines.append(Line(inv.due_date, ForecastLineKind.ap_due, -inv.outstanding, CERTAIN_BP, source,
                              inv.counterparty_id))
            continue
        late = snap.counterparties[inv.counterparty_id].stats.get("avg_days_late", 0)
        expected = inv.due_date + timedelta(days=late)
        if expected < snap.as_of:
            at_risk.append(source[0])
            lines.append(Line(snap.as_of, ForecastLineKind.ar_expected, inv.outstanding, 0, source, inv.counterparty_id))
        else:
            bp = collection_bp(snap, inv.counterparty_id, at_risk_customers)
            lines.append(Line(expected, ForecastLineKind.ar_expected, inv.outstanding, bp, source, inv.counterparty_id))

    for p in project_invoices(snap.invoices, snap.as_of, end):
        source = tuple(f"invoice:{i}" for i in p.basis_ids)
        if p.direction == InvoiceDirection.payable:
            lines.append(Line(p.due_date, ForecastLineKind.recurring, -p.amount, CERTAIN_BP, source, p.counterparty_id))
        else:
            late = snap.counterparties[p.counterparty_id].stats.get("avg_days_late", 0)
            bp = collection_bp(snap, p.counterparty_id, at_risk_customers)
            lines.append(Line(p.due_date + timedelta(days=late), ForecastLineKind.recurring, p.amount, bp, source,
                              p.counterparty_id))
    return lines, at_risk


def _baseline_lines(snap: Snapshot) -> list[Line]:
    in_series = {tx_id for s in snap.series for tx_id in s.transaction_ids}
    start = snap.as_of - timedelta(days=7 * BASELINE_WEEKS)
    weekly: dict[tuple[str, bool], list[int]] = defaultdict(lambda: [0] * BASELINE_WEEKS)
    sources: dict[tuple[str, bool], list[str]] = defaultdict(list)
    for t in snap.transactions:
        if not start <= t.date < snap.as_of or t.invoice_id is not None or t.id in in_series:
            continue
        if t.category in BASELINE_EXCLUDED:
            continue
        key = (t.category.value if t.category else "uncategorized", t.amount > 0)
        weekly[key][(t.date - start).days // 7] += t.amount
        sources[key].append(f"transaction:{t.id}")

    lines = []
    for key in sorted(weekly):
        median = statistics.median_low(weekly[key])
        if median == 0:
            continue
        kind = ForecastLineKind.baseline_in if key[1] else ForecastLineKind.baseline_out
        for k in range(HORIZON_WEEKS):
            lines.append(Line(snap.as_of + timedelta(days=7 * k), kind, median, CERTAIN_BP, tuple(sources[key])))
    return lines


def project(snap: Snapshot) -> Forecast:
    end = horizon_end(snap.as_of)
    opening = Line(snap.as_of, ForecastLineKind.opening, snap.cash, CERTAIN_BP,
                   tuple(f"account:{a}" for a in snap.account_ids))
    invoice_lines, at_risk = _invoice_lines(snap, end)
    lines = [opening, *_series_lines(snap, end), *invoice_lines, *_baseline_lines(snap)]
    assumptions = {
        "horizon_weeks": HORIZON_WEEKS,
        "baseline_weeks": BASELINE_WEEKS,
        "week_starts_on": snap.as_of.isoformat(),
        "at_risk_receivables": at_risk,
        "collection_probability_bp": {
            "established_customer": ESTABLISHED_CUSTOMER_BP,
            "customer_with_receivable_over_30d_past_due": AT_RISK_CUSTOMER_BP,
            "no_history": NEW_CUSTOMER_BP,
            "at_risk_receivable": 0,
        },
    }
    return build(snap.as_of, snap.currency, snap.min_cash_buffer, lines, assumptions)


def save_forecast(session: Session, business_id: int, forecast: Forecast, scenario_name: str | None = None) -> ForecastRun:
    run = ForecastRun(business_id=business_id, as_of=forecast.as_of, horizon_weeks=HORIZON_WEEKS,
                      assumptions=forecast.assumptions, scenario_name=scenario_name)
    session.add(run)
    session.flush()
    session.add_all(
        ForecastLine(
            run_id=run.id,
            week_start=forecast.weeks[forecast.week_of(ln.on) - 1].start,
            kind=ln.kind,
            amount=ln.amount,
            currency=forecast.currency,
            probability=ln.probability_bp / CERTAIN_BP,
            source_ids=list(ln.source_ids),
        )
        for ln in forecast.lines
    )
    session.flush()
    return run
