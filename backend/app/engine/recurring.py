"""Recurring payment detection (SPEC §6.3).

Groups by (counterparty, category). A group is a series when every amount is within ±10% of the
median, the gaps match a weekly/monthly/quarterly cadence, and there are ≥3 occurrences (≥2 for
quarterly). Invoice-linked transactions are skipped: those flows are forecast as AR/AP, and
counting them here too would double them. Integer maths only.
"""

import calendar
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Account, Cadence, Category, RecurringSeries, Transaction

AMOUNT_TOLERANCE_PCT = 10
CADENCES: list[tuple[Cadence, int, int]] = [  # cadence, centre days, tolerance days
    (Cadence.weekly, 7, 2),
    (Cadence.monthly, 30, 4),
    (Cadence.quarterly, 91, 7),
]
MIN_OCCURRENCES = {Cadence.weekly: 3, Cadence.monthly: 3, Cadence.quarterly: 2}
STEP_MONTHS = {Cadence.monthly: 1, Cadence.quarterly: 3}


@dataclass(frozen=True)
class TxPoint:
    id: int
    date: date
    amount: int
    currency: str
    counterparty_id: int | None
    category: Category | None
    invoice_id: int | None


@dataclass(frozen=True)
class SeriesSpec:
    counterparty_id: int
    category: Category
    typical_amount: int  # signed median, same convention as Transaction.amount
    currency: str
    cadence: Cadence
    next_expected_date: date
    active: bool
    transaction_ids: list[int]


def add_months(d: date, months: int) -> date:
    years, month0 = divmod(d.month - 1 + months, 12)
    year, month = d.year + years, month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _cadence(gaps: list[int]) -> tuple[Cadence, int] | None:
    median_gap = statistics.median_low(gaps)
    for cadence, centre, tolerance in CADENCES:
        if abs(median_gap - centre) <= tolerance:
            if all(abs(g - median_gap) <= tolerance for g in gaps):
                return cadence, tolerance
            return None
    return None


def _series(counterparty_id: int, category: Category, points: list[TxPoint], today: date) -> SeriesSpec | None:
    points = sorted(points, key=lambda p: (p.date, p.id))
    if len(points) < 2:
        return None
    median = statistics.median_low([p.amount for p in points])
    if any(abs(p.amount - median) * 100 > abs(median) * AMOUNT_TOLERANCE_PCT for p in points):
        return None
    found = _cadence([(b.date - a.date).days for a, b in zip(points, points[1:])])
    if found is None:
        return None
    cadence, tolerance = found
    if len(points) < MIN_OCCURRENCES[cadence]:
        return None
    last = points[-1].date
    next_date = last + timedelta(days=7) if cadence is Cadence.weekly else add_months(last, STEP_MONTHS[cadence])
    return SeriesSpec(
        counterparty_id=counterparty_id,
        category=category,
        typical_amount=median,
        currency=points[0].currency,
        cadence=cadence,
        next_expected_date=next_date,
        active=today <= next_date + timedelta(days=tolerance),
        transaction_ids=[p.id for p in points],
    )


def find_series(points: list[TxPoint], today: date) -> list[SeriesSpec]:
    groups: dict[tuple[int, Category], list[TxPoint]] = defaultdict(list)
    for p in points:
        if p.counterparty_id is None or p.category is None or p.invoice_id is not None:
            continue
        groups[(p.counterparty_id, p.category)].append(p)
    found = (_series(cp_id, category, group, today) for (cp_id, category), group in sorted(groups.items()))
    return [s for s in found if s is not None]


def detect_recurring(session: Session, business_id: int, today: date) -> list[RecurringSeries]:
    """Recompute the business's series from its transactions, replacing any previous ones."""
    rows = session.scalars(
        select(Transaction).join(Account, Transaction.account_id == Account.id).where(Account.business_id == business_id)
    )
    points = [TxPoint(t.id, t.date, t.amount, t.currency, t.counterparty_id, t.category, t.invoice_id) for t in rows]
    session.execute(delete(RecurringSeries).where(RecurringSeries.business_id == business_id))
    series = [
        RecurringSeries(
            business_id=business_id,
            counterparty_id=s.counterparty_id,
            category=s.category,
            typical_amount=s.typical_amount,
            currency=s.currency,
            cadence=s.cadence,
            next_expected_date=s.next_expected_date,
            active=s.active,
            transaction_ids=s.transaction_ids,
        )
        for s in find_series(points, today)
    ]
    session.add_all(series)
    session.flush()
    return series
