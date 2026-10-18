"""Paperwork Center (SPEC §6.8): "Close my month" and the bank-ready pack.

GET only, any signed-in role. Every figure comes from engine/statements.py (integer cents, cash
basis); this module only shapes it. Never writes and never calls the model.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_session
from app.api.routes_dashboard import week_out
from app.api.schemas import (
    AccountReconciliationOut,
    AgingOut,
    AgingRowOut,
    BankPackOut,
    CashFlowOut,
    EvidenceRef,
    MonthCloseOut,
    ObligationOut,
    ObligationsOut,
    PeriodOut,
    PnlLineOut,
    ProfitAndLossOut,
    ReconciliationOut,
)
from app.config import Settings, get_settings
from app.db.models import Business, User
from app.engine import statements as st
from app.engine.forecast import project
from app.engine.snapshot import load_snapshot
from app.services import ledger

router = APIRouter(prefix="/paperwork", tags=["paperwork"])
BASIS = "Cash basis: income is money received and expenses are money paid in the period. Not a balance sheet."


class _Refs:
    """Collects refs while shaping, then labels them all with one lookup."""

    def __init__(self) -> None:
        self.refs: list[EvidenceRef] = []

    def __call__(self, kind: str, id_: int) -> EvidenceRef:
        r = EvidenceRef(ref=f"{kind}:{id_}", label=None)
        self.refs.append(r)
        return r

    def label(self, session: Session, business_id: int) -> None:
        names = ledger.labels(session, business_id, sorted({r.ref for r in self.refs}))
        for r in self.refs:
            r.label = names.get(r.ref)


def _period(p: st.Period) -> PeriodOut:
    return PeriodOut(start=p.start, end=p.end, label=p.label)


def _lines(lines: tuple[st.PnlLine, ...]) -> list[PnlLineOut]:
    return [PnlLineOut(key=ln.key, amount_cents=ln.amount, count=ln.count) for ln in lines]


def _pnl(p: st.ProfitAndLoss) -> ProfitAndLossOut:
    return ProfitAndLossOut(
        period=_period(p.period), revenue=_lines(p.revenue), cogs=_lines(p.cogs),
        operating_expenses=_lines(p.operating_expenses), other_income=_lines(p.other_income),
        total_revenue_cents=p.total_revenue, total_cogs_cents=p.total_cogs, gross_profit_cents=p.gross_profit,
        total_operating_expenses_cents=p.total_operating_expenses, total_other_income_cents=p.total_other_income,
        net_profit_cents=p.net_profit, transfers_cents=p.transfers, transaction_count=p.transaction_count)


def _cash_flow(c: st.CashFlow) -> CashFlowOut:
    return CashFlowOut(period=_period(c.period), opening_cents=c.opening, operating_in_cents=c.operating_in,
                       operating_out_cents=c.operating_out, net_operating_cents=c.net_operating,
                       transfers_cents=c.transfers, net_change_cents=c.net_change, closing_cents=c.closing)


def _reconciliation(r: st.Reconciliation, ref: _Refs) -> ReconciliationOut:
    return ReconciliationOut(period=_period(r.period), book_opening_cents=r.book_opening,
                             book_closing_cents=r.book_closing, reconciled=r.reconciled, accounts=[
        AccountReconciliationOut(
            account=ref("account", a.account_id), book_opening_cents=a.book_opening, money_in_cents=a.money_in,
            money_out_cents=a.money_out, book_closing_cents=a.book_closing,
            statement_closing_cents=a.statement_closing, statement_date=a.statement_date,
            difference_cents=a.difference, to_review=[ref("transaction", t) for t in a.to_review])
        for a in r.accounts])


def _aging(a: st.Aging, ref: _Refs) -> AgingOut:
    return AgingOut(direction=a.direction.value, as_of=a.as_of, totals_cents=a.totals, total_cents=a.total, rows=[
        AgingRowOut(invoice=ref("invoice", r.invoice_id), number=r.number,
                    counterparty=ref("counterparty", r.counterparty_id), due_date=r.due_date,
                    days_past_due=r.days_past_due, outstanding_cents=r.outstanding, bucket=r.bucket)
        for r in a.rows])


@router.get("/month-close", response_model=MonthCloseOut)
def month_close(user: User = Depends(current_user), session: Session = Depends(get_session),
                settings: Settings = Depends(get_settings)) -> MonthCloseOut:
    today = settings.demo_today
    snap = load_snapshot(session, user.business_id, today)
    mc = st.month_close(snap, st.load_account_ledgers(session, user.business_id, today))
    ref = _Refs()
    out = MonthCloseOut(
        as_of=today, currency=snap.currency, basis=BASIS, disclaimer=st.DISCLAIMER, period=_period(mc.period),
        reconciliation=_reconciliation(mc.reconciliation, ref), profit_and_loss=_pnl(mc.profit_and_loss),
        cash_flow=_cash_flow(mc.cash_flow), receivables=_aging(mc.receivables, ref),
        payables=_aging(mc.payables, ref))
    ref.label(session, user.business_id)
    return out


@router.get("/bank-pack", response_model=BankPackOut)
def bank_pack(user: User = Depends(current_user), session: Session = Depends(get_session),
              settings: Settings = Depends(get_settings)) -> BankPackOut:
    today = settings.demo_today
    snap = load_snapshot(session, user.business_id, today)
    pack = st.bank_pack(snap, project(snap))
    business = session.get(Business, user.business_id)
    ref = _Refs()
    out = BankPackOut(
        as_of=today, currency=snap.currency, business_name=business.name if business else "", basis=BASIS,
        disclaimer=st.DISCLAIMER, months=[_period(m) for m in pack.months],
        profit_and_loss=[_pnl(p) for p in pack.profit_and_loss], cash_flow=[_cash_flow(c) for c in pack.cash_flow],
        min_cash_buffer_cents=snap.min_cash_buffer, forecast=[week_out(w) for w in pack.forecast.weeks],
        obligations=ObligationsOut(total_cents=pack.obligations.total, rows=[
            ObligationOut(date=o.on, week=o.week, series=ref("recurring_series", o.series_id),
                          counterparty=ref("counterparty", o.counterparty_id), category=o.category.value,
                          amount_cents=o.amount)
            for o in pack.obligations.rows]),
        receivables=_aging(pack.receivables, ref))
    ref.label(session, user.business_id)
    return out
