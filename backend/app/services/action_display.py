"""What an approval card shows for an Action: who, which invoice, how much, the draft email, and what
the sandbox did after approval. Read-only, scoped to the action's business, never returns contact
email addresses. Money stays integer cents; amounts come from the stored params, the draft and the
invoice, never from the proposer's free text.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Action, Business, Invoice
from app.policy.limits import OPEN_STATUSES, invoice_outstanding
from app.sandbox import records
from app.services import action_names, ledger

def _ref(session: Session, business_id: int, kind: str, id_: Any) -> dict[str, Any] | None:
    if not isinstance(id_, int):
        return None
    ref = f"{kind}:{id_}"
    return {"ref": ref, "label": ledger.labels(session, business_id, [ref]).get(ref)}


def _invoice(session: Session, business_id: int, invoice_id: Any) -> Invoice | None:
    invoice = session.get(Invoice, invoice_id) if isinstance(invoice_id, int) else None
    return invoice if invoice is not None and invoice.business_id == business_id else None


def _sandbox(session: Session, action: Action, counterparty_name: str | None) -> dict[str, Any] | None:
    row = records.for_action(session, action.id)
    if row is None:
        return None
    match row["kind"]:
        case "email":
            summary = f"Sandbox email #{row['id']} {row['status']} to {counterparty_name or 'the stored contact'}"
        case "payment":
            on = row.pop("scheduled_date")
            summary = (f"Sandbox payment #{row['id']} {row['status']} to {counterparty_name or 'the payee'}"
                       f" for {on:%b} {on.day}")
        case _:
            summary = f"Sandbox loan application #{row['id']} {row['status']}"
    return {**row, "summary": summary}


def display(session: Session, action: Action, today: Any) -> dict[str, Any]:
    params = action.params or {}
    business = session.get(Business, action.business_id)
    out: dict[str, Any] = {"title": None, "counterparty": None, "invoice": None,
                           "amount_cents": None, "currency": business.base_currency, "invoice_outstanding_cents": None,
                           "days_past_due": None, "scheduled_date": None, "email": None, "sandbox": None,
                           "denied_reason": (action.result or {}).get("denied"),
                           "evidence": [{"ref": r, "label": label} for r, label in _labels(session, action)]}
    invoice = _invoice(session, action.business_id, params.get("invoice_id"))
    if invoice is not None:
        out["invoice"] = _ref(session, action.business_id, "invoice", invoice.id)
        outstanding = invoice_outstanding(session, invoice)
        out["invoice_outstanding_cents"] = outstanding
        if invoice.status in OPEN_STATUSES and outstanding > 0:
            out["days_past_due"] = max((today - invoice.due_date).days, 0)
    counterparty = action_names.counterparty(session, action)
    name = counterparty.name if counterparty is not None else None
    if counterparty is not None:
        out["counterparty"] = _ref(session, action.business_id, "counterparty", counterparty.id)
    draft = action_names.draft_of(session, action)
    out["title"] = action_names.title(action, name, draft)

    match action.tool:
        case "send_reminder" | "draft_reminder" | "send_terms_request" | "draft_terms_request":
            if draft is not None and draft.result:
                out["email"] = {"to_name": name, "subject": draft.result.get("subject"), "body": draft.result.get("body")}
                if action.tool.endswith("_reminder"):
                    out["amount_cents"] = draft.result.get("outstanding")
        case "schedule_payment":
            out["amount_cents"] = params.get("amount") if isinstance(params.get("amount"), int) else None
            out["scheduled_date"] = params.get("date")
        case "submit_loan_application":
            out["amount_cents"] = params.get("amount") if isinstance(params.get("amount"), int) else None
    out["sandbox"] = _sandbox(session, action, name)
    return out


def _labels(session: Session, action: Action) -> list[tuple[str, str | None]]:
    refs = [r for r in (action.evidence_ids or []) if isinstance(r, str)][:20]
    names = ledger.labels(session, action.business_id, refs)
    return [(r, names.get(r)) for r in refs]
