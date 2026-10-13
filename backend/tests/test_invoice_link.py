"""Linking bank rows to invoices: only when reference, direction, counterparty and amount agree."""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Account, Base, Business, CategoryRule, Counterparty, Invoice, Transaction
from app.engine.categorize import DEFAULT_KEYWORD_RULES, NullClassifier
from app.ingestion.pipeline import ingest_csv


@pytest.fixture
def mini() -> Iterator[tuple[Session, Account]]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        biz = Business(name="T", base_currency="USD", industry="t", min_cash_buffer=0, settings={})
        s.add(biz)
        s.flush()
        acct = Account(business_id=biz.id, name="Chk", type="checking", currency="USD", opening_balance=0)
        harbor = Counterparty(business_id=biz.id, name="Harbor Lane Café", normalized_name="HARBOR LANE CAFE",
                              kind="customer", stats={})
        copper = Counterparty(business_id=biz.id, name="Copperleaf Bakery", normalized_name="COPPERLEAF BAKERY",
                              kind="customer", stats={})
        verde = Counterparty(business_id=biz.id, name="Verde Green Coffee Imports",
                             normalized_name="VERDE GREEN COFFEE IMPORTS", kind="supplier", stats={})
        s.add_all([acct, harbor, copper, verde])
        s.add_all(CategoryRule(business_id=biz.id, kind="keyword", pattern=p, direction=d, category=c,
                               source="seed", priority=i) for i, (p, d, c) in enumerate(DEFAULT_KEYWORD_RULES))
        s.flush()
        for number, direction, cp, total in [
            ("INV-1024", "receivable", copper, 222_000),
            ("INV-1037", "receivable", harbor, 468_000),
            ("INV-1026", "receivable", copper, 150_000),
            ("VGC-5512", "payable", verde, 210_600),
            ("INV-1025", "receivable", copper, 198_000),
        ]:
            s.add(Invoice(business_id=biz.id, direction=direction, counterparty_id=cp.id, number=number,
                          issue_date=date(2026, 4, 1), due_date=date(2026, 5, 1), total=total, currency="USD",
                          status="open", notes=None))
        s.flush()
        yield s, acct


def _ingest(session: Session, account: Account, *rows: tuple[str, str]) -> list[Transaction]:
    data = "Date,Description,Amount\n" + "".join(f"2026-05-01,{d},{a}\n" for d, a in rows)
    ingest_csv(session, account, "t.csv", data.encode(), NullClassifier())
    return list(session.scalars(select(Transaction).order_by(Transaction.id)))


def _number(session: Session, tx: Transaction) -> str | None:
    return session.get(Invoice, tx.invoice_id).number if tx.invoice_id else None


@pytest.mark.parametrize("desc, amount, number", [
    ("ACH CREDIT COPPERLEAF BAKERY REF INV-1024", "2220.00", "INV-1024"),
    ("HARBORLANE CAFE PMT INV1037", "4680.00", "INV-1037"),
    ("ACH CREDIT COPPERLEAF BAKERY INV 1026", "1500.00", "INV-1026"),
    ("ACH DEBIT VERDE GREEN COFFEE IMP VGC-5512", "-2106.00", "VGC-5512"),
])
def test_reference_formats_link(mini: tuple[Session, Account], desc: str, amount: str, number: str) -> None:
    session, account = mini
    (tx,) = _ingest(session, account, (desc, amount))
    assert _number(session, tx) == number
    assert not tx.needs_review


def test_harbor_counterparty_taken_from_invoice(mini: tuple[Session, Account]) -> None:
    session, account = mini
    (tx,) = _ingest(session, account, ("HARBORLANE CAFE PMT INV1037", "4680.00"))
    assert session.get(Counterparty, tx.counterparty_id).name == "Harbor Lane Café"


def test_unknown_reference_is_ignored(mini: tuple[Session, Account]) -> None:
    session, account = mini
    (tx,) = _ingest(session, account, ("ACH CREDIT COPPERLEAF BAKERY REF INV-9999", "10.00"))
    assert tx.invoice_id is None and tx.counterparty_id is not None


@pytest.mark.parametrize("desc, amount, why", [
    ("ACH DEBIT COPPERLEAF BAKERY INV-1024", "-2220.00", "outflow against a receivable"),
    ("ACH CREDIT VERDE GREEN COFFEE IMP VGC-5512", "2106.00", "inflow against a payable"),
    ("ACH CREDIT COPPERLEAF BAKERY REF INV-1037", "4680.00", "invoice belongs to Harbor Lane"),
    ("ACH CREDIT COPPERLEAF BAKERY REF INV-1024", "2220.01", "more than outstanding"),
    ("ACH CREDIT COPPERLEAF BAKERY INV-1024 INV-1025", "100.00", "two valid candidates"),
])
def test_invalid_link_goes_to_review(mini: tuple[Session, Account], desc: str, amount: str, why: str) -> None:
    session, account = mini
    (tx,) = _ingest(session, account, (desc, amount))
    assert tx.invoice_id is None, why
    assert tx.needs_review, why


def test_outstanding_counts_earlier_payments(mini: tuple[Session, Account]) -> None:
    session, account = mini
    first, second, third = _ingest(
        session, account,
        ("ACH CREDIT COPPERLEAF BAKERY REF INV-1024", "1500.00"),
        ("ACH CREDIT COPPERLEAF BAKERY REF INV-1024", "720.00"),
        ("ACH CREDIT COPPERLEAF BAKERY REF INV-1024", "0.01"),
    )
    assert _number(session, first) == _number(session, second) == "INV-1024"
    assert third.invoice_id is None and third.needs_review


def test_reimport_skips_duplicates(mini: tuple[Session, Account]) -> None:
    session, account = mini
    row = ("POS SETTLEMENT 0501 CLOUDPOS", "10.00")
    _ingest(session, account, row, row)
    txs = _ingest(session, account, row, row, row)  # third identical row on the day is new
    assert len(txs) == 3
