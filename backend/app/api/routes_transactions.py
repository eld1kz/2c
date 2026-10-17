"""Transactions for the web UI: the ledger table, the review queue, and human recategorization.

Reading is open to any signed-in role. Changing a category is owner/accountant only and goes through
services/categorization.py (audited; writes only the transaction's categorization and one rule).
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_session, refusals_keep_audit
from app.api.schemas import CategoryIn, EvidenceRef, TransactionOut, TransactionPageOut, UntrustedOut
from app.config import Settings, get_settings
from app.db.models import Category, User
from app.services import categorization, ledger

router = APIRouter(prefix="/transactions", tags=["transactions"])
PAGE = ledger.MAX_ROWS


def _rows(session: Session, business_id: int, rows: list[dict[str, Any]]) -> list[TransactionOut]:
    names = ledger.labels(session, business_id, [r[k] for r in rows for k in ("counterparty", "invoice") if r[k]])
    return [TransactionOut(
        ref=r["ref"], id=int(r["ref"].split(":")[1]), date=r["date"], amount_cents=r["amount_cents"], currency=r["currency"],
        category=r["category"], category_source=r["category_source"], needs_review=r["needs_review"],
        counterparty=EvidenceRef(ref=r["counterparty"], label=r["counterparty_name"] or names.get(r["counterparty"]))
        if r["counterparty"] else None,
        invoice=EvidenceRef(ref=r["invoice"], label=names.get(r["invoice"])) if r["invoice"] else None,
        description=UntrustedOut(untrusted_text=r["description"].text, source=r["description"].source),
    ) for r in rows]


@router.get("", response_model=TransactionPageOut)
def list_transactions(needs_review: bool | None = None, category: Category | None = None,
                      offset: int = Query(0, ge=0, le=100_000), user: User = Depends(current_user),
                      session: Session = Depends(get_session)) -> TransactionPageOut:
    rows = ledger.query_transactions(session, user.business_id, needs_review=needs_review, category=category,
                                     limit=PAGE, offset=offset)
    return TransactionPageOut(rows=_rows(session, user.business_id, rows), has_more=len(rows) == PAGE)


@router.post("/{transaction_id}/category", response_model=TransactionOut)
def set_category(transaction_id: int, body: CategoryIn, user: User = Depends(current_user),
                 session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> TransactionOut:
    with refusals_keep_audit(session):
        t = categorization.recategorize(session, user, transaction_id, body.category, settings.demo_today)
    detail = ledger.explain(session, user.business_id, f"transaction:{t.id}", settings.demo_today)
    return _rows(session, user.business_id, [detail])[0]
