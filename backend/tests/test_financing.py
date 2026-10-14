"""Financing ranking (SPEC §6.7) and the P4 demo sequence on both classifier paths."""

import dataclasses

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Business, Counterparty, Insight, Invoice
from app.engine.financing import NOT_FINANCIAL_ADVICE, rank_financing
from app.engine.snapshot import load_snapshot
from app.engine.whatif import CollectReceivable, run_what_if
from seed.generate_golden import DEMO_TODAY
from tests.test_forecast import golden_forecast

# (option_id, cost cents, max cents, covers gap)
BASE_RANKING = {
    "null": [("overdraft", 19_834, 1_500_000, True), ("short_term_loan", 21_486, 5_000_000, True),
             ("supplier_terms_extension", 0, 485_700, False), ("accelerate_receivables", 9_000, 450_000, False),
             ("invoice_factoring", 22_500, 382_500, False)],
    "llm": [("overdraft", 20_082, 1_500_000, True), ("short_term_loan", 21_756, 5_000_000, True),
            ("supplier_terms_extension", 0, 485_700, False), ("accelerate_receivables", 9_000, 450_000, False),
            ("invoice_factoring", 22_500, 382_500, False)],
}
BASE_GAP = {"null": 718_199, "llm": 727_199}
LEFTOVER_GAP = {"null": 238_199, "llm": 247_199}
LEFTOVER_RANKING = {
    "null": [("supplier_terms_extension", 0), ("overdraft", 4_111), ("accelerate_receivables", 4_763),
             ("short_term_loan", 7_126), ("invoice_factoring", 14_011)],
    "llm": [("supplier_terms_extension", 0), ("overdraft", 4_266), ("accelerate_receivables", 4_943),
            ("short_term_loan", 7_395), ("invoice_factoring", 14_541)],
}


def _rows(ranking: object) -> list[tuple[str, int, int, bool]]:
    return [(o.option_id, o.cost, o.max_amount, o.covers_gap) for o in ranking.options]


def test_base_gap_ranking(golden_path: tuple[str, Session, Business]) -> None:
    path, session, business = golden_path
    forecast = golden_forecast(session, business)
    gap = forecast.gap()
    assert (gap.first_week, gap.last_week, gap.low_week, gap.amount, gap.days) == (6, 13, 9, BASE_GAP[path], 56)
    ranking = rank_financing(gap, forecast, load_snapshot(session, business.id, DEMO_TODAY))
    assert _rows(ranking) == BASE_RANKING[path]
    assert ranking.disclaimer == NOT_FINANCIAL_ADVICE and "not financial advice" in ranking.disclaimer.lower()
    assert all(isinstance(v, int) for o in ranking.options for v in (o.cost, o.max_amount))


def test_p4_demo_sequence(golden_path: tuple[str, Session, Business]) -> None:
    """CASH_GAP → what-if "collect INV-1042" → rank the leftover gap → supplier terms first, overdraft second."""
    path, session, business = golden_path
    snap = load_snapshot(session, business.id, DEMO_TODAY)
    base = golden_forecast(session, business)

    cash_gap = session.scalar(select(Insight).where(Insight.type == "CASH_GAP"))
    assert cash_gap.impact_amount == base.gap().amount == BASE_GAP[path]

    inv_1042 = session.scalar(select(Invoice).where(Invoice.number == "INV-1042"))
    scenario = run_what_if(base, [CollectReceivable(inv_1042.id, DEMO_TODAY)]).scenario
    leftover = scenario.gap()
    assert (leftover.first_week, leftover.last_week, leftover.low_week, leftover.amount) == (6, 10, 9, LEFTOVER_GAP[path])

    ranking = rank_financing(leftover, scenario, snap)
    assert [(o.option_id, o.cost) for o in ranking.options] == LEFTOVER_RANKING[path]
    first, second = ranking.options[:2]
    assert first.option_id == "supplier_terms_extension" and first.covers_gap and first.max_amount >= leftover.amount
    assert second.option_id == "overdraft" and second.covers_gap
    suppliers = {session.get(Invoice, int(e.split(":")[1])).counterparty_id for e in first.evidence_ids}
    assert {session.get(Counterparty, c).name for c in suppliers} == {"Verde Green Coffee Imports", "QuickShip Logistics"}


def test_supplier_terms_need_a_good_payment_history(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    snap = load_snapshot(session, business.id, DEMO_TODAY)
    late = {cp_id: dataclasses.replace(cp, stats={**cp.stats, "on_time_rate": 0.5})
            for cp_id, cp in snap.counterparties.items()}
    forecast = golden_forecast(session, business)
    ranking = rank_financing(forecast.gap(), forecast, dataclasses.replace(snap, counterparties=late))
    (supplier,) = [o for o in ranking.options if o.option_id == "supplier_terms_extension"]
    assert (supplier.max_amount, supplier.covers_gap, supplier.evidence_ids) == (0, False, ())


def test_receivable_moved_by_scenario_is_not_offered_again(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    snap = load_snapshot(session, business.id, DEMO_TODAY)
    inv_1052 = session.scalar(select(Invoice.id).where(Invoice.number == "INV-1052"))
    scenario = run_what_if(golden_forecast(session, business), [CollectReceivable(inv_1052, DEMO_TODAY)]).scenario
    options = {o.option_id: o for o in rank_financing(scenario.gap(), scenario, snap).options}
    assert options["accelerate_receivables"].max_amount == 0
    assert options["invoice_factoring"].max_amount == 0


def test_supplier_terms_breakdown_by_supplier(golden_path: tuple[str, Session, Business]) -> None:
    """P4: after collecting INV-1042, Verde's deferrable payables alone cover the leftover gap."""
    path, session, business = golden_path
    snap = load_snapshot(session, business.id, DEMO_TODAY)
    inv_1042 = session.scalar(select(Invoice.id).where(Invoice.number == "INV-1042"))
    scenario = run_what_if(golden_forecast(session, business), [CollectReceivable(inv_1042, DEMO_TODAY)]).scenario
    (terms,) = [o for o in rank_financing(scenario.gap(), scenario, snap).options
                if o.option_id == "supplier_terms_extension"]
    names = {c.id: c.name for c in session.scalars(select(Counterparty))}
    shares = [(names[s.counterparty_id], s.amount, s.covers_gap) for s in terms.by_counterparty]
    assert shares == [("Verde Green Coffee Imports", 439_200, True), ("QuickShip Logistics", 46_500, False)]
    assert sum(s.amount for s in terms.by_counterparty) == terms.max_amount
    assert set().union(*(s.evidence_ids for s in terms.by_counterparty)) == set(terms.evidence_ids)
