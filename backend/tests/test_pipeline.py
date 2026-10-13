"""Phase 1 acceptance: golden CSVs through the real pipeline (LLM mocked, no network)."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    Base,
    Business,
    CategorySource,
    Counterparty,
    Invoice,
    RecurringSeries,
    Transaction,
)
from app.engine.categorize import NullClassifier
from app.ingestion.pipeline import ingest_csv
from seed.generate_golden import GOLDEN_DIR, Q2_FILE, TARGET_CASH_AT_DEMO_TODAY
from seed.load import load
from tests.fakes import FakeClassifier


def test_at_least_90pct_categorized_by_rules_or_llm(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, _, _ = golden_db
    txs = list(session.scalars(select(Transaction)))
    assert len(txs) == 306
    categorized = [t for t in txs if t.category_source in (CategorySource.rule, CategorySource.llm)]
    assert len(categorized) / len(txs) >= 0.9
    assert len(categorized) == 306
    assert sum(t.category_source == CategorySource.rule for t in txs) == 300


def test_cash_reconciles(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, _, _ = golden_db
    account = session.scalar(select(Account))
    total = sum(t.amount for t in session.scalars(select(Transaction)))
    assert account.opening_balance + total == TARGET_CASH_AT_DEMO_TODAY


def test_payments_link_to_exactly_the_paid_invoices(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, _, _ = golden_db
    linked = [t.invoice_id for t in session.scalars(select(Transaction)) if t.invoice_id]
    paid = set(session.scalars(select(Invoice.id).where(Invoice.status == "paid")))
    assert len(linked) == len(set(linked)) == 40
    assert set(linked) == paid
    p1 = session.scalar(select(Invoice).where(Invoice.number == "INV-1042"))
    assert p1.id not in linked


def test_acceptance_series_present(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, _, _ = golden_db
    kinds = {(s.category, s.cadence) for s in session.scalars(select(RecurringSeries))}
    assert {("rent", "monthly"), ("payroll", "weekly"), ("equipment", "quarterly")} <= kinds
    assert sum(1 for s in session.scalars(select(RecurringSeries)) if s.category == "software") >= 2


def test_without_llm_quillbook_goes_to_review_and_planted_series_survive() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        load(s, classifier=NullClassifier())
        review = list(s.scalars(select(Transaction).where(Transaction.needs_review)))
        assert {t.raw_description.split()[-2] for t in review} == {"QUILLBOOK"}
        assert len(review) == 6 and all(t.category is None for t in review)
        names = {c.id: c.name for c in s.scalars(select(Counterparty))}
        series = {names[r.counterparty_id] for r in s.scalars(select(RecurringSeries))}
        assert {"Designly Pro", "Designly Team", "Crestline Equipment Finance", "Paystream Payroll"} <= series
        assert "Quillbook Accounting" not in series


def test_reupload_is_idempotent(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, _, classifier = golden_db
    account = session.scalar(select(Account))
    result = ingest_csv(session, account, Q2_FILE, (GOLDEN_DIR / Q2_FILE).read_bytes(), classifier)
    assert (result.rows, result.inserted, result.skipped_duplicates) == (148, 0, 148)
