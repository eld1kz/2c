"""Recurring detection (SPEC §6.3) on golden data and synthetic edge cases."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Business, Cadence, Category, Counterparty, RecurringSeries
from app.engine.recurring import TxPoint, add_months, find_series
from tests.fakes import FakeClassifier

TODAY = date(2026, 10, 1)


def _series(session: Session) -> dict[tuple[str, str], RecurringSeries]:
    names = {c.id: c.name for c in session.scalars(select(Counterparty))}
    return {(names[s.counterparty_id], s.category): s for s in session.scalars(select(RecurringSeries))}


def test_golden_series(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, _, _ = golden_db
    found = {key: (s.cadence, len(s.transaction_ids)) for key, s in _series(session).items()}
    assert found == {
        ("Paystream Payroll", "payroll"): (Cadence.weekly, 26),
        ("Maplewood Property Group", "rent"): (Cadence.monthly, 6),
        ("Riverbend Utilities", "utilities"): (Cadence.monthly, 6),
        ("Designly Pro", "software"): (Cadence.monthly, 6),
        ("Designly Team", "software"): (Cadence.monthly, 6),
        ("Quillbook Accounting", "software"): (Cadence.monthly, 6),  # via mocked LLM
        ("CloudPOS", "software"): (Cadence.monthly, 6),
        ("CloudPOS", "fees"): (Cadence.monthly, 6),
        ("Northfold Packaging", "cogs_packaging"): (Cadence.monthly, 6),
        ("Crestline Equipment Finance", "equipment"): (Cadence.quarterly, 2),
    }


def test_golden_series_details(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, _, _ = golden_db
    series = _series(session)
    lease = series[("Crestline Equipment Finance", "equipment")]
    assert (lease.typical_amount, lease.next_expected_date) == (-1_200_000, date(2026, 11, 7))  # forecast week 6
    rent = series[("Maplewood Property Group", "rent")]
    assert (rent.typical_amount, rent.next_expected_date) == (-450_000, date(2026, 10, 1))
    assert series[("Paystream Payroll", "payroll")].next_expected_date == date(2026, 10, 2)
    for key in [("Designly Pro", "software"), ("Designly Team", "software")]:
        assert series[key].typical_amount == -2_999
    assert all(s.active and s.currency == "USD" for s in series.values())


def _pts(dates: list[date], amounts: list[int], invoice_id: int | None = None) -> list[TxPoint]:
    return [TxPoint(i, d, a, "USD", 1, Category.equipment, invoice_id) for i, (d, a) in enumerate(zip(dates, amounts))]


def _monthly(n: int, start: date = date(2026, 4, 5)) -> list[date]:
    return [add_months(start, i) for i in range(n)]


def test_quarterly_with_two_occurrences() -> None:
    (s,) = find_series(_pts([date(2026, 5, 8), date(2026, 8, 7)], [-1_000, -1_000]), TODAY)
    assert (s.cadence, s.next_expected_date) == (Cadence.quarterly, date(2026, 11, 7))


def test_monthly_needs_three() -> None:
    assert find_series(_pts(_monthly(2), [-500, -500]), TODAY) == []
    (s,) = find_series(_pts(_monthly(3, date(2026, 7, 5)), [-500, -500, -500]), TODAY)
    assert s.cadence == Cadence.monthly


def test_amount_band_is_ten_percent_of_median() -> None:
    assert find_series(_pts(_monthly(4), [-1_000, -1_000, -1_000, -1_100]), TODAY)  # exactly +10%: kept
    assert find_series(_pts(_monthly(4), [-1_000, -1_000, -1_000, -1_101]), TODAY) == []  # one outlier rejects


def test_irregular_gaps_rejected() -> None:
    dates = [date(2026, 4, 1), date(2026, 5, 1), date(2026, 5, 20), date(2026, 7, 1)]
    assert find_series(_pts(dates, [-100] * 4), TODAY) == []


def test_daily_and_biweekly_are_not_series() -> None:
    daily = [date(2026, 9, 1) + timedelta(i) for i in range(20)]
    biweekly = [date(2026, 4, 9) + timedelta(14 * i) for i in range(10)]
    assert find_series(_pts(daily, [-100] * 20), TODAY) == []
    assert find_series(_pts(biweekly, [-100] * 10), TODAY) == []


def test_invoice_linked_rows_excluded() -> None:
    assert find_series(_pts(_monthly(6), [-100] * 6, invoice_id=9), TODAY) == []


def test_stale_series_inactive() -> None:
    (s,) = find_series(_pts(_monthly(3, date(2026, 1, 5)), [-100] * 3), TODAY)
    assert not s.active


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
