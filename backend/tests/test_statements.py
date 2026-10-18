"""Phase 6b: cash-basis statements reconcile to the ledger to the cent and agree across reports."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account, Business, Category, InvoiceDirection, Transaction
from app.engine import statements as st
from app.engine.forecast import ForecastLineKind, project
from app.engine.snapshot import load_snapshot
from app.services import ledger
from tests.fakes import FakeClassifier
from tests.test_api import _login, client, db  # noqa: F401 - fixtures

TODAY = date(2026, 10, 1)
SEPT = st.Period(date(2026, 9, 1), date(2026, 9, 30))


def _close(session: Session, business_id: int) -> st.MonthClose:
    return st.month_close(load_snapshot(session, business_id, TODAY), st.load_account_ledgers(session, business_id, TODAY))


def _sept_txs(session: Session) -> list[Transaction]:
    return list(session.scalars(select(Transaction).where(Transaction.date >= SEPT.start, Transaction.date <= SEPT.end)))


def test_periods_come_from_demo_today() -> None:
    assert st.previous_month(TODAY) == SEPT
    assert st.previous_month(date(2026, 3, 15)) == st.Period(date(2026, 2, 1), date(2026, 2, 28))
    assert [p.label for p in st.months_before(TODAY, 3)] == ["July 2026", "August 2026", "September 2026"]
    assert st.Period(date(2026, 7, 1), SEPT.end).label == "Jul 2026 – Sep 2026"


def test_every_transaction_lands_in_exactly_one_line(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    pnl = _close(session, business.id).profit_and_loss
    txs = _sept_txs(session)
    lines = (*pnl.revenue, *pnl.cogs, *pnl.operating_expenses, *pnl.other_income)
    assert sum(ln.count for ln in lines) + pnl.transfers_count == pnl.transaction_count == len(txs)
    assert pnl.net_profit + pnl.transfers == sum(t.amount for t in txs)  # to the cent


def test_cash_flow_reconciles_with_pnl_snapshot_and_bank(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    mc = _close(session, business.id)
    cf, rec = mc.cash_flow, mc.reconciliation
    assert cf.opening + cf.net_change == cf.closing
    assert cf.net_operating == mc.profit_and_loss.net_profit
    assert cf.net_change == mc.profit_and_loss.net_profit + mc.profit_and_loss.transfers
    assert cf.closing == rec.book_closing == load_snapshot(session, business.id, TODAY).cash
    assert cf.opening == rec.book_opening == load_snapshot(session, business.id, SEPT.start).cash


def test_bank_statement_balance_matches_the_books(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, business, _ = golden_db
    (acct,) = _close(session, business.id).reconciliation.accounts
    assert acct.statement_closing == acct.book_closing == 865_000  # Q3 CSV running balance on Sept 30
    assert acct.statement_date == SEPT.end
    assert acct.difference == 0
    assert acct.money_in - acct.money_out == acct.book_closing - acct.book_opening


def test_a_statement_that_disagrees_is_reported(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, business, _ = golden_db
    last = session.scalars(select(Transaction).where(Transaction.date <= SEPT.end)
                           .order_by(Transaction.date.desc(), Transaction.id.desc())).first()
    assert last is not None and last.statement_balance is not None
    last.statement_balance += 1_234
    rec = _close(session, business.id).reconciliation
    assert rec.accounts[0].difference == 1_234
    assert not rec.reconciled


def test_a_statement_without_running_balance_cannot_reconcile(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, business, _ = golden_db
    for t in session.scalars(select(Transaction)):
        t.statement_balance = None
    (acct,) = _close(session, business.id).reconciliation.accounts
    assert acct.statement_closing is None and acct.statement_date is None and acct.difference is None
    assert acct.book_closing == 865_000


def test_transfers_move_cash_but_not_profit(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, business, _ = golden_db
    before = _close(session, business.id)
    account = session.scalars(select(Account).where(Account.business_id == business.id)).one()
    for amount in (-50_000, 20_000):
        session.add(Transaction(account_id=account.id, date=date(2026, 9, 15), amount=amount, currency="USD",
                                raw_description="TRANSFER", category=Category.transfer, source_file="t.csv"))
    session.add(Transaction(account_id=account.id, date=date(2026, 9, 16), amount=7_000, currency="USD",
                            raw_description="MYSTERY CREDIT", category=None, needs_review=True, source_file="t.csv"))
    session.flush()
    after = _close(session, business.id)
    assert after.profit_and_loss.transfers == -30_000
    assert after.profit_and_loss.net_profit == before.profit_and_loss.net_profit + 7_000
    assert [(ln.key, ln.amount) for ln in after.profit_and_loss.other_income] == [("uncategorized", 7_000)]
    assert after.cash_flow.closing == before.cash_flow.closing - 23_000
    assert len(after.reconciliation.accounts[0].to_review) == 1


def test_aging_matches_the_open_invoices(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, business, _ = golden_db
    mc = _close(session, business.id)
    for aging, direction in ((mc.receivables, InvoiceDirection.receivable), (mc.payables, InvoiceDirection.payable)):
        open_rows = [i for i in ledger.query_invoices(session, business.id, TODAY, direction=direction)
                     if i["outstanding_cents"] > 0 and i["status"] in ("open", "overdue")]
        assert aging.total == sum(i["outstanding_cents"] for i in open_rows) == sum(aging.totals.values())
        assert {r.number for r in aging.rows} == {i["number"] for i in open_rows}
    inv_1042 = next(r for r in mc.receivables.rows if r.number == "INV-1042")
    assert (inv_1042.days_past_due, inv_1042.bucket, inv_1042.outstanding) == (45, "31_60", 480_000)
    assert mc.receivables.rows[0].number == "INV-1042"  # most overdue first


@pytest.mark.parametrize(("days", "bucket"), [(-3, "current"), (0, "current"), (1, "1_30"), (30, "1_30"),
                                              (31, "31_60"), (60, "31_60"), (61, "61_90"), (91, "over_90")])
def test_aging_buckets(days: int, bucket: str) -> None:
    assert st.bucket(days) == bucket


def test_bank_pack_agrees_with_month_close_and_forecast(golden_path: tuple[str, Session, Business]) -> None:
    _, session, business = golden_path
    snap = load_snapshot(session, business.id, TODAY)
    forecast = project(snap)
    pack, mc = st.bank_pack(snap, forecast), _close(session, business.id)
    *months, span = pack.profit_and_loss
    assert [p.period for p in months] == st.months_before(TODAY, 3)
    assert months[-1] == mc.profit_and_loss
    assert span.net_profit == sum(p.net_profit for p in months)
    assert span.transaction_count == sum(p.transaction_count for p in months)
    *cf_months, cf_span = pack.cash_flow
    assert cf_months[-1] == mc.cash_flow
    assert cf_span.opening == cf_months[0].opening and cf_span.closing == cf_months[-1].closing == mc.cash_flow.closing
    assert pack.receivables == mc.receivables
    assert [w.closing for w in pack.forecast.weeks] == [w.closing for w in forecast.weeks]
    assert pack.forecast.weeks[0].opening == mc.cash_flow.closing  # forecast starts where September ended


def test_obligations_are_the_forecasts_rent_and_lease_lines(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, business, _ = golden_db
    snap = load_snapshot(session, business.id, TODAY)
    forecast = project(snap)
    ob = st.obligations(snap, forecast)
    lease = [r for r in ob.rows if r.category == Category.equipment]
    assert [(r.week, r.amount) for r in lease] == [(6, 1_200_000)]
    assert {r.category for r in ob.rows} == {Category.rent, Category.equipment}
    series = {f"recurring_series:{s.id}" for s in snap.series if s.category in st.OBLIGATION_CATEGORIES}
    matching = [ln for ln in forecast.lines if ln.kind == ForecastLineKind.recurring and ln.source_ids[0] in series]
    assert ob.total == -sum(ln.amount for ln in matching)


def test_ingestion_stores_the_statement_balance(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, _, _ = golden_db
    txs = list(session.scalars(select(Transaction)))
    assert txs and all(t.statement_balance is not None for t in txs)


# --- API ----------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/paperwork/month-close", "/paperwork/bank-pack"])
def test_paperwork_needs_sign_in(client: TestClient, path: str) -> None:  # noqa: F811
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("role", ["owner", "accountant", "viewer"])
def test_every_role_reads_paperwork(client: TestClient, role: str) -> None:  # noqa: F811
    headers = _login(client, role)
    for path in ("/paperwork/month-close", "/paperwork/bank-pack"):
        assert client.get(path, headers=headers).status_code == 200, path


def test_api_figures_agree_with_the_dashboard(client: TestClient) -> None:  # noqa: F811
    headers = _login(client, "viewer")
    mc = client.get("/paperwork/month-close", headers=headers).json()
    pack = client.get("/paperwork/bank-pack", headers=headers).json()
    cash = client.get("/position", headers=headers).json()["cash_cents"]
    forecast = client.get("/forecast", headers=headers).json()
    assert mc["period"]["label"] == "September 2026"
    assert mc["disclaimer"] == pack["disclaimer"] == st.DISCLAIMER
    assert "Cash basis" in mc["basis"] and "Not a balance sheet" in mc["basis"]
    rec = mc["reconciliation"]
    assert rec["reconciled"] and rec["book_closing_cents"] == mc["cash_flow"]["closing_cents"] == cash
    assert rec["accounts"][0]["account"]["label"]
    assert pack["profit_and_loss"][2] == mc["profit_and_loss"]
    assert pack["receivables"] == mc["receivables"]
    assert [w["closing_cents"] for w in pack["forecast"]] == [w["closing_cents"] for w in forecast["weeks"]]
    assert all(r["invoice"]["label"] and r["counterparty"]["label"] for r in mc["receivables"]["rows"])
    assert pack["obligations"]["rows"] and all(r["series"]["label"] for r in pack["obligations"]["rows"])
