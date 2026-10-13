"""Read-only, in-memory view of one business's ledger for the deterministic engine.

Forecast, what-if, insights and financing all work on a Snapshot so they stay pure and testable.
Invoice `notes` are deliberately NOT loaded: they are untrusted text and no engine rule needs them (T1).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    Business,
    Cadence,
    Category,
    Counterparty,
    CounterpartyKind,
    Invoice,
    InvoiceDirection,
    InvoiceLine,
    InvoiceStatus,
    RecurringSeries,
    Transaction,
)


@dataclass(frozen=True)
class CounterpartyFacts:
    id: int
    name: str
    normalized_name: str
    kind: CounterpartyKind
    stats: dict[str, Any]


@dataclass(frozen=True)
class InvoiceLineFacts:
    sku: str | None
    quantity: int
    unit_price: int


@dataclass(frozen=True)
class InvoiceFacts:
    id: int
    number: str
    counterparty_id: int
    direction: InvoiceDirection
    issue_date: date
    due_date: date
    total: int
    outstanding: int  # total minus linked bank payments, never negative
    status: InvoiceStatus
    lines: tuple[InvoiceLineFacts, ...]

    @property
    def is_open(self) -> bool:
        return self.status in (InvoiceStatus.open, InvoiceStatus.overdue) and self.outstanding > 0


@dataclass(frozen=True)
class SeriesFacts:
    id: int
    counterparty_id: int
    category: Category
    amount: int  # signed typical amount
    cadence: Cadence
    last_date: date
    transaction_ids: tuple[int, ...]


@dataclass(frozen=True)
class TxFacts:
    id: int
    date: date
    amount: int
    category: Category | None
    counterparty_id: int | None
    invoice_id: int | None


@dataclass(frozen=True)
class Snapshot:
    business_id: int
    as_of: date
    currency: str
    min_cash_buffer: int
    cash: int  # sum of account balances at the start of `as_of`
    account_ids: tuple[int, ...]
    counterparties: dict[int, CounterpartyFacts]
    invoices: tuple[InvoiceFacts, ...]
    series: tuple[SeriesFacts, ...]  # active series only
    transactions: tuple[TxFacts, ...]  # dated before `as_of`
    invoice_by_id: dict[int, InvoiceFacts] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "invoice_by_id", {i.id: i for i in self.invoices})


def load_snapshot(session: Session, business_id: int, as_of: date) -> Snapshot:
    business = session.get(Business, business_id)
    if business is None:
        raise ValueError(f"unknown business {business_id}")
    accounts = list(session.scalars(select(Account).where(Account.business_id == business_id).order_by(Account.id)))
    account_ids = [a.id for a in accounts]
    txs = [
        TxFacts(t.id, t.date, t.amount, t.category, t.counterparty_id, t.invoice_id)
        for t in session.scalars(
            select(Transaction).where(Transaction.account_id.in_(account_ids), Transaction.date < as_of).order_by(Transaction.id)
        )
    ]
    paid: dict[int, int] = defaultdict(int)
    for t in txs:
        if t.invoice_id is not None:
            paid[t.invoice_id] += abs(t.amount)

    lines: dict[int, list[InvoiceLineFacts]] = defaultdict(list)
    for line in session.scalars(
        select(InvoiceLine).join(Invoice, InvoiceLine.invoice_id == Invoice.id)
        .where(Invoice.business_id == business_id).order_by(InvoiceLine.id)
    ):
        lines[line.invoice_id].append(InvoiceLineFacts(line.sku, line.quantity, line.unit_price))
    invoices = [
        InvoiceFacts(
            id=i.id, number=i.number, counterparty_id=i.counterparty_id, direction=i.direction,
            issue_date=i.issue_date, due_date=i.due_date, total=i.total,
            outstanding=max(i.total - paid[i.id], 0), status=i.status, lines=tuple(lines[i.id]),
        )
        for i in session.scalars(select(Invoice).where(Invoice.business_id == business_id).order_by(Invoice.id))
    ]

    tx_dates = {t.id: t.date for t in txs}
    series = []
    for s in session.scalars(
        select(RecurringSeries).where(RecurringSeries.business_id == business_id, RecurringSeries.active)
        .order_by(RecurringSeries.id)
    ):
        dates = [tx_dates[i] for i in s.transaction_ids if i in tx_dates]
        if dates:
            series.append(SeriesFacts(s.id, s.counterparty_id, s.category, s.typical_amount, s.cadence, max(dates),
                                      tuple(s.transaction_ids)))

    counterparties = {
        c.id: CounterpartyFacts(c.id, c.name, c.normalized_name, c.kind, dict(c.stats or {}))
        for c in session.scalars(select(Counterparty).where(Counterparty.business_id == business_id))
    }
    return Snapshot(
        business_id=business_id,
        as_of=as_of,
        currency=business.base_currency,
        min_cash_buffer=business.min_cash_buffer,
        cash=sum(a.opening_balance for a in accounts) + sum(t.amount for t in txs),
        account_ids=tuple(account_ids),
        counterparties=counterparties,
        invoices=tuple(invoices),
        series=tuple(series),
        transactions=tuple(txs),
    )
