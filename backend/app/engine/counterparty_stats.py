"""Counterparty payment stats (SPEC §5): avg_days_late, on_time_rate, invoices_count.

Only fully paid invoices count. An invoice's paid date is its last linked bank transaction, so
days late = paid date − due date; "on time" means paid on or before the due date. The forecast
uses avg_days_late for timing; on_time_rate is for LATE_PAYER and display, not probability.
"""

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account, Counterparty, Invoice, Transaction


def payment_stats(days_late: list[int]) -> dict[str, Any]:
    if not days_late:
        return {}
    n = len(days_late)
    return {
        "invoices_count": n,
        "avg_days_late": round(sum(days_late) / n),
        "on_time_rate": round(sum(1 for d in days_late if d <= 0) / n, 2),
    }


def refresh_counterparty_stats(session: Session, business_id: int) -> dict[int, dict[str, Any]]:
    """Recompute and store stats for every counterparty of the business."""
    paid_amount: dict[int, int] = defaultdict(int)
    paid_on: dict[int, date] = {}
    for t in session.scalars(
        select(Transaction).join(Account, Transaction.account_id == Account.id)
        .where(Account.business_id == business_id, Transaction.invoice_id.is_not(None))
    ):
        paid_amount[t.invoice_id] += abs(t.amount)
        paid_on[t.invoice_id] = max(paid_on.get(t.invoice_id, t.date), t.date)

    days_late: dict[int, list[int]] = defaultdict(list)
    for inv in session.scalars(select(Invoice).where(Invoice.business_id == business_id).order_by(Invoice.due_date)):
        if inv.id in paid_on and paid_amount[inv.id] >= inv.total:
            days_late[inv.counterparty_id].append((paid_on[inv.id] - inv.due_date).days)

    stats: dict[int, dict[str, Any]] = {}
    for cp in session.scalars(select(Counterparty).where(Counterparty.business_id == business_id)):
        cp.stats = payment_stats(days_late[cp.id])
        stats[cp.id] = cp.stats
    session.flush()
    return stats
