"""Cash-basis statements (SPEC §6.8): "Close my month" and the bank-ready pack.

All figures are integer cents computed here from the ledger, the open invoices and the 13-week
forecast. Nothing is accrued: income is money received, expenses are money paid. There is no
balance sheet. Every transaction in a period lands in exactly one P&L line or in transfers, so
net profit + transfers == the period's net change in cash, and the cash figures agree with the
bank reconciliation and the dashboard by construction.

The running balance printed on a bank CSV row (`statement_balance`) is untrusted text from the
file: it is only compared with the book balance, never used as cash.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account, Category, ForecastLineKind, InvoiceDirection, Transaction
from app.engine.forecast import Forecast
from app.engine.recurring import add_months
from app.engine.snapshot import Snapshot, TxFacts

REVENUE = (Category.revenue_retail, Category.revenue_wholesale)
COGS = (Category.cogs_beans, Category.cogs_packaging)
OPERATING = (Category.rent, Category.utilities, Category.payroll, Category.software, Category.equipment,
             Category.logistics, Category.marketing, Category.fees, Category.taxes)
UNCATEGORIZED = "uncategorized"
OTHER = (Category.other.value, UNCATEGORIZED)  # split by direction: inflows → other income, outflows → expenses
OBLIGATION_CATEGORIES = (Category.rent, Category.equipment)
BUCKETS = ("current", "1_30", "31_60", "61_90", "over_90")
PACK_MONTHS = 3
DISCLAIMER = "Prepared from your records for review; not audited; not tax or legal advice."


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # inclusive

    @property
    def label(self) -> str:
        if (self.start.year, self.start.month) == (self.end.year, self.end.month):
            return f"{self.start:%B %Y}"
        return f"{self.start:%b %Y} – {self.end:%b %Y}"


def previous_month(today: date) -> Period:
    end = today.replace(day=1) - timedelta(days=1)
    return Period(end.replace(day=1), end)


def months_before(today: date, n: int) -> list[Period]:
    """The n full calendar months before `today`, oldest first."""
    last = previous_month(today)
    return [Period(add_months(last.start, -k), add_months(last.start, -k + 1) - timedelta(days=1))
            for k in range(n - 1, -1, -1)]


# --- profit and loss (cash basis) ---------------------------------------------------------


@dataclass(frozen=True)
class PnlLine:
    key: str  # a Category value or "uncategorized"
    amount: int  # revenue/other income: received; cogs/expenses: paid (positive = money out)
    count: int


@dataclass(frozen=True)
class ProfitAndLoss:
    period: Period
    revenue: tuple[PnlLine, ...]
    cogs: tuple[PnlLine, ...]
    operating_expenses: tuple[PnlLine, ...]
    other_income: tuple[PnlLine, ...]
    transfers: int  # signed, excluded from profit
    transfers_count: int
    transaction_count: int

    @property
    def total_revenue(self) -> int:
        return sum(ln.amount for ln in self.revenue)

    @property
    def total_cogs(self) -> int:
        return sum(ln.amount for ln in self.cogs)

    @property
    def gross_profit(self) -> int:
        return self.total_revenue - self.total_cogs

    @property
    def total_operating_expenses(self) -> int:
        return sum(ln.amount for ln in self.operating_expenses)

    @property
    def total_other_income(self) -> int:
        return sum(ln.amount for ln in self.other_income)

    @property
    def net_profit(self) -> int:
        return self.gross_profit - self.total_operating_expenses + self.total_other_income


def _in(snap: Snapshot, period: Period) -> list[TxFacts]:
    return [t for t in snap.transactions if period.start <= t.date <= period.end]


def profit_and_loss(snap: Snapshot, period: Period) -> ProfitAndLoss:
    sums: dict[tuple[str, str], list[int]] = {}  # (section, key) → [signed sum, count]

    def add(section: str, key: str, amount: int) -> None:
        entry = sums.setdefault((section, key), [0, 0])
        entry[0] += amount
        entry[1] += 1

    transfers = transfers_count = 0
    txs = _in(snap, period)
    for t in txs:
        key = t.category.value if t.category else UNCATEGORIZED
        if t.category == Category.transfer:
            transfers += t.amount
            transfers_count += 1
        elif t.category in REVENUE:
            add("revenue", key, t.amount)
        elif t.category in COGS:
            add("cogs", key, t.amount)
        elif t.category in OPERATING or (key in OTHER and t.amount < 0):
            add("operating", key, t.amount)
        else:
            add("other_income", key, t.amount)

    def section(name: str, sign: int, order: tuple[str, ...]) -> tuple[PnlLine, ...]:
        keys = [k for s, k in sums if s == name]
        keys.sort(key=lambda k: (order.index(k) if k in order else len(order), k))
        return tuple(PnlLine(k, sign * sums[(name, k)][0], sums[(name, k)][1]) for k in keys)

    values = tuple(c.value for c in (*REVENUE, *COGS, *OPERATING)) + OTHER
    return ProfitAndLoss(period, section("revenue", 1, values), section("cogs", -1, values),
                         section("operating", -1, values), section("other_income", 1, values),
                         transfers, transfers_count, len(txs))


# --- cash flow (direct method) ------------------------------------------------------------


def cash_at(snap: Snapshot, day: date) -> int:
    """Total book cash at the start of `day` (day ≤ snap.as_of)."""
    return snap.cash - sum(t.amount for t in snap.transactions if t.date >= day)


@dataclass(frozen=True)
class CashFlow:
    period: Period
    opening: int
    operating_in: int
    operating_out: int  # positive = money out
    transfers: int  # signed
    closing: int

    @property
    def net_operating(self) -> int:
        return self.operating_in - self.operating_out

    @property
    def net_change(self) -> int:
        return self.net_operating + self.transfers


def cash_flow(snap: Snapshot, period: Period) -> CashFlow:
    txs = _in(snap, period)
    flows = [t for t in txs if t.category != Category.transfer]
    transfers = sum(t.amount for t in txs if t.category == Category.transfer)
    return CashFlow(period, cash_at(snap, period.start), sum(t.amount for t in flows if t.amount > 0),
                    -sum(t.amount for t in flows if t.amount < 0), transfers,
                    cash_at(snap, period.end + timedelta(days=1)))


# --- bank reconciliation ------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerRow:
    id: int
    date: date
    amount: int
    statement_balance: int | None
    needs_review: bool


@dataclass(frozen=True)
class AccountLedger:
    account_id: int
    name: str
    opening_balance: int
    rows: tuple[LedgerRow, ...]  # in import order


def load_account_ledgers(session: Session, business_id: int, before: date) -> list[AccountLedger]:
    out = []
    for a in session.scalars(select(Account).where(Account.business_id == business_id).order_by(Account.id)):
        rows = tuple(LedgerRow(t.id, t.date, t.amount, t.statement_balance, t.needs_review) for t in session.scalars(
            select(Transaction).where(Transaction.account_id == a.id, Transaction.date < before)
            .order_by(Transaction.date, Transaction.id)))
        out.append(AccountLedger(a.id, a.name, a.opening_balance, rows))
    return out


@dataclass(frozen=True)
class AccountReconciliation:
    account_id: int
    name: str
    book_opening: int
    money_in: int
    money_out: int  # positive = money out
    book_closing: int
    statement_closing: int | None  # None: the statement gave no running balance
    statement_date: date | None
    to_review: tuple[int, ...]  # transaction ids in the period still marked needs_review

    @property
    def difference(self) -> int | None:
        return None if self.statement_closing is None else self.statement_closing - self.book_closing


@dataclass(frozen=True)
class Reconciliation:
    period: Period
    accounts: tuple[AccountReconciliation, ...]

    @property
    def book_opening(self) -> int:
        return sum(a.book_opening for a in self.accounts)

    @property
    def book_closing(self) -> int:
        return sum(a.book_closing for a in self.accounts)

    @property
    def reconciled(self) -> bool:
        return all(a.difference == 0 for a in self.accounts)


def reconcile(ledgers: list[AccountLedger], period: Period) -> Reconciliation:
    accounts = []
    for led in ledgers:
        before = [r for r in led.rows if r.date < period.start]
        inside = [r for r in led.rows if period.start <= r.date <= period.end]
        opening = led.opening_balance + sum(r.amount for r in before)
        money_in = sum(r.amount for r in inside if r.amount > 0)
        money_out = -sum(r.amount for r in inside if r.amount < 0)
        last = (before + inside)[-1] if before or inside else None
        statement = last.statement_balance if last is not None else None
        accounts.append(AccountReconciliation(
            led.account_id, led.name, opening, money_in, money_out, opening + money_in - money_out, statement,
            last.date if last is not None and statement is not None else None,
            tuple(r.id for r in inside if r.needs_review)))
    return Reconciliation(period, tuple(accounts))


# --- receivables / payables aging ---------------------------------------------------------


@dataclass(frozen=True)
class AgingRow:
    invoice_id: int
    number: str
    counterparty_id: int
    counterparty_name: str
    due_date: date
    days_past_due: int  # ≤ 0: not yet due
    outstanding: int
    bucket: str


@dataclass(frozen=True)
class Aging:
    direction: InvoiceDirection
    as_of: date
    rows: tuple[AgingRow, ...]  # most overdue first

    @property
    def totals(self) -> dict[str, int]:
        return {b: sum(r.outstanding for r in self.rows if r.bucket == b) for b in BUCKETS}

    @property
    def total(self) -> int:
        return sum(r.outstanding for r in self.rows)


def bucket(days_past_due: int) -> str:
    if days_past_due <= 0:
        return "current"
    if days_past_due <= 30:
        return "1_30"
    if days_past_due <= 60:
        return "31_60"
    return "61_90" if days_past_due <= 90 else "over_90"


def aging(snap: Snapshot, direction: InvoiceDirection) -> Aging:
    rows = []
    for i in snap.invoices:
        if i.direction != direction or not i.is_open:
            continue
        days = (snap.as_of - i.due_date).days
        rows.append(AgingRow(i.id, i.number, i.counterparty_id, snap.counterparties[i.counterparty_id].name,
                             i.due_date, days, i.outstanding, bucket(days)))
    rows.sort(key=lambda r: (-r.days_past_due, r.number))
    return Aging(direction, snap.as_of, tuple(rows))


# --- fixed obligations (from recurring rent and lease payments) ---------------------------


@dataclass(frozen=True)
class ObligationRow:
    on: date
    week: int
    series_id: int
    counterparty_id: int
    counterparty_name: str
    category: Category
    amount: int  # positive = money out


@dataclass(frozen=True)
class Obligations:
    rows: tuple[ObligationRow, ...]

    @property
    def total(self) -> int:
        return sum(r.amount for r in self.rows)


def obligations(snap: Snapshot, forecast: Forecast) -> Obligations:
    """The forecast's own recurring rent and equipment-lease lines, so they agree with it exactly."""
    series = {f"recurring_series:{s.id}": s for s in snap.series if s.category in OBLIGATION_CATEGORIES}
    rows = []
    for ln in forecast.lines:
        s = series.get(ln.source_ids[0]) if ln.kind == ForecastLineKind.recurring and ln.source_ids else None
        if s is not None:
            rows.append(ObligationRow(ln.on, forecast.week_of(ln.on), s.id, s.counterparty_id,
                                      snap.counterparties[s.counterparty_id].name, s.category, -ln.amount))
    return Obligations(tuple(rows))


# --- the two packs ------------------------------------------------------------------------


@dataclass(frozen=True)
class MonthClose:
    period: Period
    reconciliation: Reconciliation
    profit_and_loss: ProfitAndLoss
    cash_flow: CashFlow
    receivables: Aging
    payables: Aging


def month_close(snap: Snapshot, ledgers: list[AccountLedger]) -> MonthClose:
    period = previous_month(snap.as_of)
    return MonthClose(period, reconcile(ledgers, period), profit_and_loss(snap, period), cash_flow(snap, period),
                      aging(snap, InvoiceDirection.receivable), aging(snap, InvoiceDirection.payable))


@dataclass(frozen=True)
class BankPack:
    months: tuple[Period, ...]
    profit_and_loss: tuple[ProfitAndLoss, ...]  # one per month, then the whole span
    cash_flow: tuple[CashFlow, ...]  # one per month, then the whole span
    forecast: Forecast
    obligations: Obligations
    receivables: Aging


def bank_pack(snap: Snapshot, forecast: Forecast) -> BankPack:
    months = months_before(snap.as_of, PACK_MONTHS)
    periods = [*months, Period(months[0].start, months[-1].end)]
    return BankPack(tuple(months), tuple(profit_and_loss(snap, p) for p in periods),
                    tuple(cash_flow(snap, p) for p in periods), forecast, obligations(snap, forecast),
                    aging(snap, InvoiceDirection.receivable))
