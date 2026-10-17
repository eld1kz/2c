"""What an approval card shows for an Action: who, which invoice, how much, the draft email, and what
the sandbox did after approval. Read-only, scoped to the action's business, never returns contact
email addresses. Money stays integer cents; amounts come from the stored params, the draft and the
invoice, never from the proposer's free text.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Action, Business, Counterparty, Invoice, SandboxEmail, SandboxLoanApplication, SandboxPayment
from app.policy.limits import OPEN_STATUSES, invoice_outstanding
from app.services import ledger

LOAN_NAMES = {
    "overdraft": "sandbox overdraft",
    "short_term_loan": "sandbox short-term loan",
    "invoice_factoring": "sandbox invoice factoring",
}


def _ref(session: Session, business_id: int, kind: str, id_: Any) -> dict[str, Any] | None:
    if not isinstance(id_, int):
        return None
    ref = f"{kind}:{id_}"
    return {"ref": ref, "label": ledger.labels(session, business_id, [ref]).get(ref)}


def _invoice(session: Session, business_id: int, invoice_id: Any) -> Invoice | None:
    invoice = session.get(Invoice, invoice_id) if isinstance(invoice_id, int) else None
    return invoice if invoice is not None and invoice.business_id == business_id else None


def _own_action(session: Session, action: Action, action_id: Any) -> Action | None:
    other = session.get(Action, action_id) if isinstance(action_id, int) else None
    return other if other is not None and other.business_id == action.business_id else None


def _sandbox(session: Session, action: Action, counterparty_name: str | None) -> dict[str, Any] | None:
    email = session.scalar(select(SandboxEmail).where(SandboxEmail.action_id == action.id))
    if email is not None:
        return {"kind": "email", "id": email.id, "status": email.status.value,
                "summary": f"Sandbox email #{email.id} {email.status.value} to {counterparty_name or 'the stored contact'}",
                "subject": email.subject, "at": email.sent_at or email.created_at}
    payment = session.scalar(select(SandboxPayment).where(SandboxPayment.action_id == action.id))
    if payment is not None:
        return {"kind": "payment", "id": payment.id, "status": payment.status.value,
                "summary": f"Sandbox payment #{payment.id} {payment.status.value} to {counterparty_name or 'the payee'}"
                           f" for {payment.scheduled_date:%b} {payment.scheduled_date.day}",
                "subject": None, "at": payment.executed_at or payment.created_at}
    loan = session.scalar(select(SandboxLoanApplication).where(SandboxLoanApplication.action_id == action.id))
    if loan is not None:
        return {"kind": "loan_application", "id": loan.id, "status": loan.status.value,
                "summary": f"Sandbox loan application #{loan.id} {loan.status.value}",
                "subject": None, "at": loan.decided_at or loan.created_at}
    return None


def display(session: Session, action: Action, today: Any) -> dict[str, Any]:
    params = action.params or {}
    business = session.get(Business, action.business_id)
    out: dict[str, Any] = {"title": action.tool.replace("_", " ").capitalize(), "counterparty": None, "invoice": None,
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
    cp_id = params.get("payee_counterparty_id") or (invoice.counterparty_id if invoice is not None else None)
    counterparty = session.get(Counterparty, cp_id) if isinstance(cp_id, int) else None
    if counterparty is not None and counterparty.business_id != action.business_id:
        counterparty = None
    name = counterparty.name if counterparty is not None else None
    if counterparty is not None:
        out["counterparty"] = _ref(session, action.business_id, "counterparty", counterparty.id)

    match action.tool:
        case "send_reminder" | "draft_reminder":
            draft = action if action.tool == "draft_reminder" else _own_action(session, action, params.get("draft_id"))
            if draft is not None and draft.result:
                out["email"] = {"to_name": name, "subject": draft.result.get("subject"), "body": draft.result.get("body")}
                out["amount_cents"] = draft.result.get("outstanding")
            noun = "Reminder draft for" if action.tool == "draft_reminder" else "Send a payment reminder to"
            out["title"] = f"{noun} {name}" if name else noun.rsplit(" ", 1)[0]
        case "schedule_payment":
            out["amount_cents"] = params.get("amount") if isinstance(params.get("amount"), int) else None
            out["scheduled_date"] = params.get("date")
            out["title"] = f"Pay {name}" if name else "Pay a supplier"
        case "submit_loan_application":
            out["amount_cents"] = params.get("amount") if isinstance(params.get("amount"), int) else None
            out["title"] = f"Apply for a {LOAN_NAMES.get(str(params.get('option_id')), 'loan')}"
    out["sandbox"] = _sandbox(session, action, name)
    return out


def _labels(session: Session, action: Action) -> list[tuple[str, str | None]]:
    refs = [r for r in (action.evidence_ids or []) if isinstance(r, str)][:20]
    names = ledger.labels(session, action.business_id, refs)
    return [(r, names.get(r)) for r in refs]
