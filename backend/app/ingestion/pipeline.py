"""CSV → Transactions: parse, normalize, link invoices, match counterparties, categorize, insert.

Writes only the `transactions` table. Never creates counterparties from description text:
counterparties feed the payment gate, so untrusted text must not mint them (T1).
"""

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    CategoryRule,
    CategorySource,
    Counterparty,
    Invoice,
    InvoiceDirection,
    Transaction,
)
from app.engine.categorize import Classifier, RowFacts, categorize
from app.ingestion.csv_parser import ParsedRow, parse_csv
from app.ingestion.normalizer import extract_invoice_refs, invoice_key, match_counterparty, normalize


@dataclass(frozen=True)
class IngestResult:
    rows: int
    inserted: int
    skipped_duplicates: int
    linked: int
    by_rule: int
    by_llm: int
    needs_review: int


@dataclass(frozen=True)
class _Link:
    invoice: Invoice | None
    conflict: bool  # a reference was found but failed validation → review


def _link(row: ParsedRow, currency: str, matched_cp: int | None, invoices: dict[str, Invoice],
          applied: Counter[int]) -> _Link:
    candidates = {invoices[k].id: invoices[k] for k in extract_invoice_refs(row.description) if k in invoices}
    if not candidates:
        return _Link(None, conflict=False)
    wanted = InvoiceDirection.receivable if row.amount > 0 else InvoiceDirection.payable
    valid = [
        inv for inv in candidates.values()
        if inv.direction == wanted
        and inv.currency == currency
        and (matched_cp is None or inv.counterparty_id == matched_cp)
        and abs(row.amount) <= inv.total - applied[inv.id]
    ]
    if len(valid) == 1:
        return _Link(valid[0], conflict=False)
    return _Link(None, conflict=True)


def ingest_csv(session: Session, account: Account, filename: str, data: bytes, classifier: Classifier) -> IngestResult:
    parsed = parse_csv(filename, data)
    business_id = account.business_id

    counterparties = {
        c.id: c.normalized_name
        for c in session.scalars(select(Counterparty).where(Counterparty.business_id == business_id))
    }
    invoices = {
        invoice_key(i.number): i for i in session.scalars(select(Invoice).where(Invoice.business_id == business_id))
    }
    applied: Counter[int] = Counter(dict(session.execute(
        select(Transaction.invoice_id, func.sum(func.abs(Transaction.amount)))
        .where(Transaction.invoice_id.is_not(None))
        .group_by(Transaction.invoice_id)
    ).all()))
    rules = list(session.scalars(select(CategoryRule).where(CategoryRule.business_id == business_id)))
    existing = Counter(
        (t.date, t.amount, t.raw_description)
        for t in session.scalars(select(Transaction).where(Transaction.account_id == account.id))
    )

    seen: Counter[tuple] = Counter()
    fresh: list[ParsedRow] = []
    for row in parsed:
        key = (row.date, row.amount, row.description)
        seen[key] += 1
        if seen[key] > existing[key]:  # nth occurrence not already imported
            fresh.append(row)

    facts: list[RowFacts] = []
    links: list[_Link] = []
    cp_ids: list[int | None] = []
    for row in fresh:
        name = normalize(row.description)
        match = match_counterparty(name, counterparties)
        link = _link(row, account.currency, match.counterparty_id if match else None, invoices, applied)
        if link.invoice is not None:
            applied[link.invoice.id] += abs(row.amount)
        cp_id = match.counterparty_id if match else (link.invoice.counterparty_id if link.invoice else None)
        links.append(link)
        cp_ids.append(cp_id)
        facts.append(RowFacts(
            normalized=name,
            amount=row.amount,
            counterparty_name=counterparties.get(cp_id) if cp_id else None,
            linked_receivable=link.invoice is not None and link.invoice.direction == InvoiceDirection.receivable,
        ))

    results = categorize(facts, rules, classifier)
    transactions = [
        Transaction(
            account_id=account.id,
            date=row.date,
            amount=row.amount,
            currency=account.currency,
            raw_description=row.description,
            counterparty_id=cp_id,
            category=c.category,
            category_source=c.source,
            confidence=c.confidence,
            needs_review=c.needs_review or link.conflict,
            source_file=filename[:255],
            invoice_id=link.invoice.id if link.invoice else None,
        )
        for row, cp_id, link, c in zip(fresh, cp_ids, links, results)
    ]
    session.add_all(transactions)
    session.flush()
    return IngestResult(
        rows=len(parsed),
        inserted=len(transactions),
        skipped_duplicates=len(parsed) - len(fresh),
        linked=sum(1 for t in transactions if t.invoice_id is not None),
        by_rule=sum(1 for t in transactions if t.category_source == CategorySource.rule),
        by_llm=sum(1 for t in transactions if t.category_source == CategorySource.llm),
        needs_review=sum(1 for t in transactions if t.needs_review),
    )
