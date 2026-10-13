"""What-if simulator (SPEC §6.5): P4 scenario on both classifier paths + each scenario type."""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Business, Cadence, Counterparty, ForecastLineKind, Invoice, RecurringSeries, Transaction
from app.engine.whatif import (
    AddRecurring,
    CollectReceivable,
    DelayReceivable,
    OneOff,
    RemoveSeries,
    ScenarioError,
    run_what_if,
)
from seed.generate_golden import DEMO_TODAY
from tests.test_forecast import expected_closings, golden_forecast

WEEK6_AFTER_COLLECTING_P1 = {"null": 280_233, "llm": 271_233}


def _invoice_id(session: Session, number: str) -> int:
    return session.scalar(select(Invoice.id).where(Invoice.number == number))


def test_p4_collect_inv_1042(golden_path: tuple[str, Session, Business]) -> None:
    path, session, business = golden_path
    base = golden_forecast(session, business)
    inv = session.scalar(select(Invoice).where(Invoice.number == "INV-1042"))
    result = run_what_if(base, [CollectReceivable(inv.id, inv.due_date)])  # "paid on its due date"
    assert result.closing_delta == (480_000,) * 13
    week6 = result.scenario.weeks[5]
    assert week6.closing == WEEK6_AFTER_COLLECTING_P1[path]
    assert 0 < week6.closing < business.min_cash_buffer
    assert [w.week for w in result.scenario.weeks if w.below_buffer] == [6, 9, 10]
    scenario_lines = [ln for ln in result.scenario.lines if ln.kind == ForecastLineKind.scenario]
    assert {ln.source_ids for ln in scenario_lines} == {(f"invoice:{inv.id}",)}
    assert result.base is base and [w.closing for w in base.weeks] == expected_closings(path)


def test_what_if_never_mutates_data(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    base = golden_forecast(session, business)
    counts = lambda: [session.scalar(select(func.count()).select_from(m)) for m in (Transaction, Invoice, RecurringSeries)]  # noqa: E731
    before = counts()
    run_what_if(base, [CollectReceivable(_invoice_id(session, "INV-1042"), DEMO_TODAY), OneOff(-100_000, DEMO_TODAY)])
    assert counts() == before
    assert session.scalar(select(Invoice.status).where(Invoice.number == "INV-1042")) == "overdue"
    assert not session.dirty and not session.new
    assert golden_forecast(session, business) == base


def test_scenario_lines_keep_the_sum_invariant(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    base = golden_forecast(session, business)
    f = run_what_if(base, [OneOff(-123_456, date(2026, 10, 20)), RemoveSeries(1)]).scenario
    for w in f.weeks:
        assert sum(ln.amount for ln in f.lines if f.week_of(ln.on) <= w.week) == w.closing
    assert all(ln.source_ids for ln in f.lines)


def test_one_off_and_add_recurring(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    base = golden_forecast(session, business)
    assert run_what_if(base, [OneOff(-100_000, date(2026, 10, 16))]).closing_delta == (0, 0) + (-100_000,) * 11
    monthly = run_what_if(base, [AddRecurring(-50_000, Cadence.monthly, date(2026, 11, 1))]).closing_delta
    assert monthly == (0,) * 4 + (-50_000,) * 4 + (-100_000,) * 5  # Nov 1 (week 5), Dec 1 (week 9)
    weekly = run_what_if(base, [AddRecurring(10_000, Cadence.weekly, date(2026, 9, 1))]).closing_delta
    assert weekly == tuple(10_000 * k for k in range(1, 14))  # past start clamps to as_of


def test_delay_receivable(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    base = golden_forecast(session, business)
    inv_1052 = _invoice_id(session, "INV-1052")  # expected Nov 15 (week 7) at 70% → 315,000
    delta = run_what_if(base, [DelayReceivable(inv_1052, 14)]).closing_delta
    assert delta == (0,) * 6 + (-315_000,) * 2 + (0,) * 5  # lands Nov 29, week 9


def test_remove_series(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    base = golden_forecast(session, business)
    lease = session.scalar(
        select(RecurringSeries.id).join(Counterparty, RecurringSeries.counterparty_id == Counterparty.id)
        .where(Counterparty.name == "Crestline Equipment Finance")
    )
    result = run_what_if(base, [RemoveSeries(lease)])
    assert result.closing_delta == (0,) * 5 + (1_200_000,) * 8
    assert not any(w.below_buffer for w in result.scenario.weeks[:8])


def test_unknown_targets_raise(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    base = golden_forecast(session, business)
    paid = _invoice_id(session, "INV-1027")
    for scenario in (CollectReceivable(paid, DEMO_TODAY), DelayReceivable(999_999, 3), RemoveSeries(999_999)):
        with pytest.raises(ScenarioError):
            run_what_if(base, [scenario])
