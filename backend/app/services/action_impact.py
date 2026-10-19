"""The 13-week cash effect of approving a proposed action, for its approval card. Read-only, no model.

The scenarios are the ones Today's "with fixes" verdict uses (`services/today.fixes`): a reminder →
the invoice is collected today; a terms request → the supplier's upcoming invoices are paid 30 days
later. Other actions have no modelled cash timing (a price email's answer is unknown), so no impact.
"""

from dataclasses import asdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Action, ActionStatus
from app.engine.forecast import project
from app.engine.impact import summarize
from app.engine.snapshot import load_snapshot
from app.engine.whatif import CollectReceivable, DelaySupplierPayments, Scenario, ScenarioError, run_what_if
from app.services.today import TERMS_EXTENSION_DAYS


def scenario_for(action: Action, today: date) -> Scenario | None:
    params = action.params or {}
    match action.tool:
        case "send_reminder" if isinstance(params.get("invoice_id"), int):
            return CollectReceivable(params["invoice_id"], today)
        case "send_terms_request" if isinstance(params.get("counterparty_id"), int):
            return DelaySupplierPayments(params["counterparty_id"], TERMS_EXTENSION_DAYS)
    return None


def impact(session: Session, action: Action, today: date) -> dict[str, Any] | None:
    if action.status != ActionStatus.proposed or (scenario := scenario_for(action, today)) is None:
        return None
    base = project(load_snapshot(session, action.business_id, today))
    try:
        return asdict(summarize(run_what_if(base, [scenario])))
    except ScenarioError:
        return None
