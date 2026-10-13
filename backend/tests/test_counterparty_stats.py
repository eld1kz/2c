"""Counterparty.stats (SPEC §5) on golden data: computed from fully paid invoices only."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Business, Counterparty
from app.engine.counterparty_stats import payment_stats

EXPECTED = {
    "Harbor Lane Café": {"invoices_count": 3, "avg_days_late": 28, "on_time_rate": 0.0},
    "Copperleaf Bakery": {"invoices_count": 5, "avg_days_late": 0, "on_time_rate": 0.4},
    "Juniper Street Diner": {"invoices_count": 5, "avg_days_late": 1, "on_time_rate": 0.4},
    "Tidewater Co-work": {"invoices_count": 5, "avg_days_late": 1, "on_time_rate": 0.6},
    "Little Fern Bookshop Café": {"invoices_count": 5, "avg_days_late": 3, "on_time_rate": 0.2},
    "Verde Green Coffee Imports": {"invoices_count": 12, "avg_days_late": 0, "on_time_rate": 1.0},
    "QuickShip Logistics": {"invoices_count": 5, "avg_days_late": 0, "on_time_rate": 1.0},
}


def test_golden_stats(golden_path: tuple[str, Session, Business]) -> None:
    _, session, _ = golden_path
    stats = {c.name: c.stats for c in session.scalars(select(Counterparty))}
    assert {name: s for name, s in stats.items() if s} == EXPECTED  # unpaid INV-1042/1047/1052 excluded
    assert stats["Crestline Equipment Finance"] == {}  # no invoices → no stats


def test_payment_stats() -> None:
    assert payment_stats([]) == {}
    assert payment_stats([25, 31, 28]) == {"invoices_count": 3, "avg_days_late": 28, "on_time_rate": 0.0}
    assert payment_stats([-2, 0, 3]) == {"invoices_count": 3, "avg_days_late": 0, "on_time_rate": 0.67}
