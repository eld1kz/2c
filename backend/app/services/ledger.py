"""Read-only ledger queries for the agent's READ tools (and later the UI). Never writes.

Everything is scoped to one business. Records are returned as plain dicts with a `ref` ("type:id"),
money as integer cents in `*_cents` keys, and third-party text (bank descriptions, invoice notes and
line descriptions, agent rationales) as `UntrustedText`, so callers can keep it marked as data (T1).
An action's params and rationale were chosen by whoever proposed it (often the agent), so they sit
under `supplied_input`: shown, but never counted as evidence. Contact emails are never returned.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    Action,
    ActionStatus,
    Category,
    Counterparty,
    Insight,
    InsightStatus,
    InsightType,
    Invoice,
    InvoiceDirection,
    InvoiceLine,
    InvoiceStatus,
    RecurringSeries,
    Transaction,
)
from app.policy.limits import OPEN_STATUSES, invoice_outstanding

MAX_ROWS = 50
MAX_SERIES_EVIDENCE = 12
REF_TYPES = ("transaction", "invoice", "counterparty", "recurring_series", "account", "insight", "action")


@dataclass(frozen=True)
class UntrustedText:
    text: str
    source: str


class RecordNotFound(LookupError):
    pass


def _stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Payment stats, with the on-time rate also as a ready-made percentage (no arithmetic for callers)."""
    out = dict(stats)
    if isinstance(stats.get("on_time_rate"), (int, float)):
        out["on_time_display"] = f"{round(stats['on_time_rate'] * 100)}%"
    return out


def ref(kind: str, id_: int | None) -> str | None:
    return None if id_ is None else f"{kind}:{id_}"


def _cp_name(session: Session, counterparty_id: int | None) -> str | None:
    cp = session.get(Counterparty, counterparty_id) if counterparty_id is not None else None
    return cp.name if cp else None


def _transaction(session: Session, t: Transaction) -> dict[str, Any]:
    return {
        "ref": ref("transaction", t.id),
        "date": t.date.isoformat(),
        "amount_cents": t.amount,
        "currency": t.currency,
        "category": t.category.value if t.category else None,
        "category_source": t.category_source.value if t.category_source else None,
        "needs_review": t.needs_review,
        "counterparty": ref("counterparty", t.counterparty_id),
        "counterparty_name": _cp_name(session, t.counterparty_id),
        "invoice": ref("invoice", t.invoice_id),
        "description": UntrustedText(t.raw_description, "bank statement description"),
    }


def _invoice(session: Session, i: Invoice, today: date) -> dict[str, Any]:
    outstanding = invoice_outstanding(session, i)
    is_open = i.status in OPEN_STATUSES and outstanding > 0
    return {
        "ref": ref("invoice", i.id),
        "number": i.number,
        "direction": i.direction.value,
        "counterparty": ref("counterparty", i.counterparty_id),
        "counterparty_name": _cp_name(session, i.counterparty_id),
        "issue_date": i.issue_date.isoformat(),
        "due_date": i.due_date.isoformat(),
        "total_cents": i.total,
        "outstanding_cents": outstanding,
        "currency": i.currency,
        "status": i.status.value,
        "days_past_due": max((today - i.due_date).days, 0) if is_open else 0,
        "has_notes": bool(i.notes),
    }


def _business_transactions(business_id: int):  # noqa: ANN202 - a select()
    return (select(Transaction).join(Account, Transaction.account_id == Account.id)
            .where(Account.business_id == business_id))


def query_transactions(session: Session, business_id: int, *, date_from: date | None = None,
                       date_to: date | None = None, category: Category | None = None,
                       counterparty_id: int | None = None, needs_review: bool | None = None,
                       limit: int = 20) -> list[dict[str, Any]]:
    query = _business_transactions(business_id)
    if date_from is not None:
        query = query.where(Transaction.date >= date_from)
    if date_to is not None:
        query = query.where(Transaction.date <= date_to)
    if category is not None:
        query = query.where(Transaction.category == category)
    if counterparty_id is not None:
        query = query.where(Transaction.counterparty_id == counterparty_id)
    if needs_review is not None:
        query = query.where(Transaction.needs_review == needs_review)
    rows = session.scalars(query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(min(limit, MAX_ROWS)))
    return [_transaction(session, t) for t in rows]


def query_invoices(session: Session, business_id: int, today: date, *, direction: InvoiceDirection | None = None,
                   status: InvoiceStatus | None = None, counterparty_id: int | None = None,
                   date_from: date | None = None, date_to: date | None = None,
                   limit: int = 20) -> list[dict[str, Any]]:
    """Invoices without their notes (`has_notes` says whether there are any; explain() shows them)."""
    query = select(Invoice).where(Invoice.business_id == business_id)
    if direction is not None:
        query = query.where(Invoice.direction == direction)
    if status is not None:
        query = query.where(Invoice.status == status)
    if counterparty_id is not None:
        query = query.where(Invoice.counterparty_id == counterparty_id)
    if date_from is not None:
        query = query.where(Invoice.due_date >= date_from)
    if date_to is not None:
        query = query.where(Invoice.due_date <= date_to)
    rows = session.scalars(query.order_by(Invoice.due_date.desc(), Invoice.id.desc()).limit(min(limit, MAX_ROWS)))
    return [_invoice(session, i, today) for i in rows]


def insight_dict(i: Insight) -> dict[str, Any]:
    return {
        "ref": ref("insight", i.id),
        "type": i.type.value,
        "severity": i.severity.value,
        "title": i.title,
        "impact_cents": i.impact_amount,
        "currency": i.currency,
        "impact_period": i.impact_period,
        "status": i.status.value,
        "detected_at": i.detected_at.isoformat(),
        "evidence_ids": list(i.evidence_ids),
    }


def list_insights(session: Session, business_id: int, *, type_: InsightType | None = None,
                  status: InsightStatus = InsightStatus.open) -> list[Insight]:
    query = select(Insight).where(Insight.business_id == business_id, Insight.status == status)
    if type_ is not None:
        query = query.where(Insight.type == type_)
    return list(session.scalars(query.order_by(Insight.impact_amount.desc(), Insight.id)))


def pending_actions(session: Session, business_id: int) -> list[Action]:
    return list(session.scalars(select(Action).where(
        Action.business_id == business_id, Action.status == ActionStatus.proposed).order_by(Action.id)))


def action_dict(a: Action) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ref": ref("action", a.id),
        "tool": a.tool,
        "tier": a.tier.value,
        "status": a.status.value,
        "proposed_by": a.proposed_by.value,
        "evidence_ids": list(a.evidence_ids),
        "result": dict(a.result) if a.result else None,
        "supplied_input": {
            "params": {k: UntrustedText(v, "parameter supplied by the proposer") if isinstance(v, str) else v
                       for k, v in a.params.items()},
            "rationale": UntrustedText(a.rationale, "rationale written by the proposer") if a.rationale else None,
        },
    }
    return out


def explain(session: Session, business_id: int, record_ref: str, today: date) -> dict[str, Any]:
    """One record in detail, by "type:id". Raises RecordNotFound if missing or another business's."""
    kind, _, raw_id = record_ref.partition(":")
    if kind not in REF_TYPES or not raw_id.isdigit():
        raise RecordNotFound(record_ref)
    record_id = int(raw_id)
    match kind:
        case "transaction":
            t = session.scalar(_business_transactions(business_id).where(Transaction.id == record_id))
            if t is None:
                raise RecordNotFound(record_ref)
            return _transaction(session, t)
        case "invoice":
            i = session.get(Invoice, record_id)
            if i is None or i.business_id != business_id:
                raise RecordNotFound(record_ref)
            linked = session.scalars(select(Transaction.id).where(Transaction.invoice_id == i.id)
                                     .order_by(Transaction.id))
            lines = session.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == i.id).order_by(InvoiceLine.id))
            out = _invoice(session, i, today)
            out["lines"] = [{"description": UntrustedText(ln.description, "invoice line description"),
                             "sku": ln.sku, "quantity": ln.quantity, "unit_price_cents": ln.unit_price}
                            for ln in lines]
            if i.notes:
                out["notes"] = UntrustedText(i.notes, "invoice notes written by the counterparty")
            out["evidence_ids"] = [out["counterparty"], *(f"transaction:{t}" for t in linked)]
            return out
        case "counterparty":
            c = session.get(Counterparty, record_id)
            if c is None or c.business_id != business_id:
                raise RecordNotFound(record_ref)
            open_invoices = session.scalars(select(Invoice).where(
                Invoice.counterparty_id == c.id, Invoice.status.in_(OPEN_STATUSES)).order_by(Invoice.due_date))
            return {
                "ref": ref("counterparty", c.id),
                "name": c.name,
                "kind": c.kind.value,
                "is_allowed_payee": c.is_allowed_payee,
                "has_contact_email": bool(c.contact_email),
                "stats": _stats(c.stats or {}),
                "open_invoices": [_invoice(session, i, today) for i in open_invoices],
            }
        case "recurring_series":
            s = session.get(RecurringSeries, record_id)
            if s is None or s.business_id != business_id:
                raise RecordNotFound(record_ref)
            return {
                "ref": ref("recurring_series", s.id),
                "counterparty": ref("counterparty", s.counterparty_id),
                "counterparty_name": _cp_name(session, s.counterparty_id),
                "category": s.category.value,
                "typical_amount_cents": s.typical_amount,
                "currency": s.currency,
                "cadence": s.cadence.value,
                "next_expected_date": s.next_expected_date.isoformat(),
                "active": s.active,
                "evidence_ids": [f"transaction:{t}" for t in s.transaction_ids[-MAX_SERIES_EVIDENCE:]],
            }
        case "account":
            a = session.get(Account, record_id)
            if a is None or a.business_id != business_id:
                raise RecordNotFound(record_ref)
            return {"ref": ref("account", a.id), "name": a.name, "type": a.type.value, "currency": a.currency,
                    "opening_balance_cents": a.opening_balance}
        case "insight":
            ins = session.get(Insight, record_id)
            if ins is None or ins.business_id != business_id:
                raise RecordNotFound(record_ref)
            return insight_dict(ins)
        case "action":
            act = session.get(Action, record_id)
            if act is None or act.business_id != business_id:
                raise RecordNotFound(record_ref)
            return action_dict(act)
    raise RecordNotFound(record_ref)  # pragma: no cover


def record_exists(session: Session, business_id: int, record_ref: str) -> bool:
    """Whether "type:id" names a record of this business (cheap: no detail is loaded)."""
    kind, _, raw_id = record_ref.partition(":")
    if kind not in REF_TYPES or not raw_id.isdigit():
        return False
    if kind == "transaction":
        return session.scalar(_business_transactions(business_id).where(Transaction.id == int(raw_id))) is not None
    model = {"invoice": Invoice, "counterparty": Counterparty, "recurring_series": RecurringSeries,
             "account": Account, "insight": Insight, "action": Action}[kind]
    row = session.get(model, int(raw_id))
    return row is not None and row.business_id == business_id


def labels(session: Session, business_id: int, refs: list[str]) -> dict[str, str]:
    """Short display labels for "type:id" refs of this business (e.g. invoice → its number).

    One query per record type. Refs that are malformed, unknown or another business's are left out.
    """
    ids: dict[str, set[int]] = {}
    for r in refs:
        kind, _, raw_id = r.partition(":")
        if kind in REF_TYPES and raw_id.isdigit():
            ids.setdefault(kind, set()).add(int(raw_id))
    txs: list[Transaction] = []
    if "transaction" in ids:
        txs = list(session.scalars(_business_transactions(business_id).where(Transaction.id.in_(ids["transaction"]))))
    series: list[RecurringSeries] = []
    if "recurring_series" in ids:
        series = list(session.scalars(select(RecurringSeries).where(
            RecurringSeries.business_id == business_id, RecurringSeries.id.in_(ids["recurring_series"]))))
    cp_ids = (set(ids.get("counterparty", ())) | {t.counterparty_id for t in txs if t.counterparty_id}
              | {s.counterparty_id for s in series})
    names = {c.id: c.name for c in session.scalars(select(Counterparty).where(
        Counterparty.business_id == business_id, Counterparty.id.in_(cp_ids)))} if cp_ids else {}
    out: dict[str, str] = {}
    for c_id in ids.get("counterparty", ()):
        if c_id in names:
            out[f"counterparty:{c_id}"] = names[c_id]
    for t in txs:
        who = names.get(t.counterparty_id or 0, "Transaction")
        out[f"transaction:{t.id}"] = f"{who} · {t.date:%b} {t.date.day}"
    for s in series:
        out[f"recurring_series:{s.id}"] = f"{names.get(s.counterparty_id, 'Series')} · {s.cadence.value}"
    simple = {"invoice": (Invoice, lambda i: i.number), "account": (Account, lambda a: a.name),
              "insight": (Insight, lambda i: i.title), "action": (Action, lambda a: f"Action #{a.id} · {a.tool}")}
    for kind, (model, label) in simple.items():
        if kind in ids:
            for row in session.scalars(select(model).where(model.business_id == business_id, model.id.in_(ids[kind]))):
                out[f"{kind}:{row.id}"] = label(row)
    return out
