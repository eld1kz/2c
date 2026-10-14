"""Normalizer + counterparty matching, with real golden descriptions."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Business, Counterparty, Transaction
from app.ingestion.normalizer import extract_invoice_refs, invoice_key, match_counterparty, normalize
from seed.generate_golden import COUNTERPARTIES
from tests.fakes import FakeClassifier

CPS = {i: nn for i, (_, nn, *_) in enumerate(COUNTERPARTIES, start=1)}
BY_NAME = {nn: i for i, nn in CPS.items()}


@pytest.mark.parametrize("raw, normalized, matched, how", [
    ("POS SETTLEMENT 0923 CLOUDPOS", "POS SETTLEMENT CLOUDPOS", "CLOUDPOS", "fuzzy"),
    ("CARD 4417 0903 DESIGNLY PRO DESIGNLY.IO", "DESIGNLY PRO", "DESIGNLY PRO", "exact"),
    ("CARD 4417 0917 DESIGNLY*TEAM SUB", "DESIGNLY TEAM SUB", "DESIGNLY TEAM", "fuzzy"),
    ("ACH DEBIT MAPLEWOOD PROPERTY GRP RENT", "MAPLEWOOD PROPERTY GROUP RENT", "MAPLEWOOD PROPERTY GROUP", "fuzzy"),
    ("PAYSTREAM PAYROLL PPD ID:4410 NET PAY", "PAYSTREAM PAYROLL NET PAY", "PAYSTREAM PAYROLL", "fuzzy"),
    ("RIVERBEND UTIL AUTOPAY", "RIVERBEND UTILITIES AUTOPAY", "RIVERBEND UTILITIES", "fuzzy"),
    ("POS PURCHASE TID 88213 NORTHFOLD PKG", "NORTHFOLD PACKAGING", "NORTHFOLD PACKAGING", "exact"),
    ("CRESTLINE EQUIP FIN LEASE PMT", "CRESTLINE EQUIPMENT FINANCE LEASE PMT", "CRESTLINE EQUIPMENT FINANCE", "fuzzy"),
    ("CLOUDPOS MERCHANT FEES SEP26", "CLOUDPOS MERCHANT FEES", "CLOUDPOS", "fuzzy"),
    ("CLOUDPOS SUBSCRIPTION 800-555-0142", "CLOUDPOS SUBSCRIPTION", "CLOUDPOS", "fuzzy"),
    ("CARD 4417 0909 QUILLBOOK ACCTG", "QUILLBOOK ACCOUNTING", "QUILLBOOK ACCOUNTING", "exact"),
    ("ACH DEBIT VERDE GREEN COFFEE IMP VGC-5512", "VERDE GREEN COFFEE IMPORTS", "VERDE GREEN COFFEE IMPORTS", "exact"),
    ("ACH CREDIT COPPERLEAF BAKERY REF INV-1024", "COPPERLEAF BAKERY REF", "COPPERLEAF BAKERY", "fuzzy"),
    ("JUNIPER ST DINER PAYMENT INV1025", "JUNIPER STREET DINER PAYMENT", "JUNIPER STREET DINER", "fuzzy"),
    ("ACH CREDIT TIDEWATER COWORK LLC INV 1026", "TIDEWATER COWORK LLC", "TIDEWATER COWORK", "fuzzy"),
    ("MOBILE XFER LITTLE FERN BOOKSHOP INV-1028", "LITTLE FERN BOOKSHOP", "LITTLE FERN BOOKSHOP", "exact"),
    ("ACH DEBIT QUICKSHIP LOGISTICS QS-2286", "QUICKSHIP LOGISTICS", "QUICKSHIP LOGISTICS", "exact"),
    ("HARBORLANE CAFE PMT INV1037", "HARBORLANE CAFE PMT", None, None),  # 85.7 < 90: invoice fallback
    ("MONTHLY SERVICE FEE", "MONTHLY SERVICE FEE", None, None),
])
def test_golden_descriptions(raw: str, normalized: str, matched: str | None, how: str | None) -> None:
    assert normalize(raw) == normalized
    m = match_counterparty(normalized, CPS)
    if matched is None:
        assert m is None
    else:
        assert m is not None and (CPS[m.counterparty_id], m.how) == (matched, how)


def test_normalize_folds_accents_and_hyphens() -> None:
    assert normalize("Harbor Lane Café") == "HARBOR LANE CAFE"
    assert normalize("Tidewater Co-work") == "TIDEWATER COWORK"


def test_ambiguous_match_is_no_match() -> None:
    assert match_counterparty("DESIGNLY", CPS) is None  # Pro and Team both score 100


def test_empty_name_never_matches() -> None:
    assert match_counterparty("", CPS) is None


@pytest.mark.parametrize("raw, refs", [
    ("ACH CREDIT COPPERLEAF BAKERY REF INV-1024", ["INV1024"]),
    ("HARBORLANE CAFE PMT INV1037", ["INV1037"]),
    ("ACH CREDIT TIDEWATER COWORK LLC INV 1026", ["INV1026"]),
    ("ACH DEBIT VERDE GREEN COFFEE IMP VGC-5512", ["VGC5512"]),
    ("ACH DEBIT QUICKSHIP LOGISTICS QS-2286", ["QS2286"]),
])
def test_invoice_refs(raw: str, refs: list[str]) -> None:
    assert [r for r in extract_invoice_refs(raw) if r.startswith(("INV", "VGC", "QS"))] == refs
    assert invoice_key(refs[0][:-4] + "-" + refs[0][-4:]) == refs[0]


def test_harbor_lane_matched_via_invoice(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, _, _ = golden_db
    harbor = session.scalar(select(Counterparty).where(Counterparty.name == "Harbor Lane Café"))
    txs = list(session.scalars(select(Transaction).where(Transaction.raw_description.like("HARBORLANE%"))))
    assert len(txs) == 3
    assert {t.counterparty_id for t in txs} == {harbor.id}


def test_unmatched_rows_never_create_counterparties(golden_db: tuple[Session, Business, FakeClassifier]) -> None:
    session, _, _ = golden_db
    assert session.scalar(select(func.count()).select_from(Counterparty)) == len(COUNTERPARTIES)
    fees = list(session.scalars(select(Transaction).where(Transaction.raw_description == "MONTHLY SERVICE FEE")))
    assert len(fees) == 6
    assert all(t.counterparty_id is None and t.category == "fees" and not t.needs_review for t in fees)
