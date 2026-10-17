"""Plain-language names for Actions, shared by the approvals inbox (`action_display.display`: the card
title) and evidence chips (`ledger.labels`: "Reminder to Harbor Lane Café").

Names come from the stored params and records (the counterparty, the draft's extension days), never
from the proposer's rationale. Depends only on the models, so `ledger` can use it without a cycle.
"""

from sqlalchemy.orm import Session

from app.db.models import Action, Counterparty, Invoice

LOAN_NAMES = {
    "overdraft": "sandbox overdraft",
    "short_term_loan": "sandbox short-term loan",
    "invoice_factoring": "sandbox invoice factoring",
}
CHIP_NOUNS = {
    "send_reminder": "Reminder to",
    "draft_reminder": "Reminder draft for",
    "send_terms_request": "Terms request to",
    "draft_terms_request": "Terms-request draft for",
    "schedule_payment": "Payment to",
}


def counterparty(session: Session, action: Action) -> Counterparty | None:
    """Who the action is about: the payee or supplier in its params, else its invoice's counterparty."""
    params = action.params or {}
    cp_id = params.get("payee_counterparty_id") or params.get("counterparty_id")
    if cp_id is None and isinstance(params.get("invoice_id"), int):
        invoice = session.get(Invoice, params["invoice_id"])
        cp_id = invoice.counterparty_id if invoice is not None and invoice.business_id == action.business_id else None
    cp = session.get(Counterparty, cp_id) if isinstance(cp_id, int) else None
    return cp if cp is not None and cp.business_id == action.business_id else None


def draft_of(session: Session, action: Action) -> Action | None:
    """The draft an action sends (or the action itself, for a draft), within the same business."""
    if action.tool.startswith("draft_"):
        return action
    draft_id = (action.params or {}).get("draft_id")
    draft = session.get(Action, draft_id) if isinstance(draft_id, int) else None
    return draft if draft is not None and draft.business_id == action.business_id else None


def title(action: Action, name: str | None, draft: Action | None) -> str:
    """The approval card heading, e.g. "Send a payment reminder to Harbor Lane Café"."""
    params = action.params or {}
    match action.tool:
        case "send_reminder" | "draft_reminder":
            noun = "Reminder draft for" if action.tool == "draft_reminder" else "Send a payment reminder to"
            return f"{noun} {name}" if name else noun.rsplit(" ", 1)[0]
        case "send_terms_request" | "draft_terms_request":
            days = (draft.params or {}).get("extension_days") if draft is not None else None
            terms = f"+{days} days on payment terms" if isinstance(days, int) else "longer payment terms"
            supplier = name or "a supplier"
            return (f"Ask {supplier} for {terms}" if action.tool == "send_terms_request"
                    else f"Terms-request draft for {supplier}")
        case "schedule_payment":
            return f"Pay {name}" if name else "Pay a supplier"
        case "submit_loan_application":
            return f"Apply for a {LOAN_NAMES.get(str(params.get('option_id')), 'loan')}"
    return action.tool.replace("_", " ").capitalize()


def chip_label(action: Action, name: str | None) -> str:
    """A short evidence-chip label, e.g. "Reminder to Harbor Lane Café" or "Payment to QuickShip Logistics"."""
    if action.tool in CHIP_NOUNS:
        noun = CHIP_NOUNS[action.tool]
        return f"{noun} {name}" if name else noun.rsplit(" ", 1)[0]
    if action.tool == "submit_loan_application":
        product = LOAN_NAMES.get(str((action.params or {}).get("option_id")), "loan")
        return f"{product[0].upper()}{product[1:]} application"
    return f"Action #{action.id}"
