"""Demo reset: put one business back to the golden demo state.

Deletes everything the business owns except its Business row, its users, the audit log and LLM usage
(real spend), then reloads the golden data through the same path as `seed.load` (no LLM: the
deterministic no-classifier path). AuditEvents are never deleted or changed: the reset appends a
`demo_reset` event, so the chain keeps verifying. Chat conversations started before the reset are
refused afterwards (routes_chat compares them with the latest `demo_reset` event).

Ids: for the golden input tables, Postgres id sequences restart when the table is empty after the
delete, so reloaded records get their original ids and older audit references keep pointing at the
same golden record. Actions, sandbox rows and derived tables keep counting up, so an id seen before
the reset never names a different record after it.
"""

import json
from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.audit import log as audit
from app.db.models import (
    Account,
    Action,
    AuditEvent,
    Business,
    CategoryRule,
    Counterparty,
    ForecastLine,
    ForecastRun,
    Insight,
    Invoice,
    InvoiceLine,
    Policy,
    RecurringSeries,
    Transaction,
)
from app.engine.categorize import Classifier, NullClassifier
from app.sandbox import reset as sandbox_reset
from app.services.action_service import utc_now
from seed.generate_golden import GOLDEN_DIR
from seed.load import load_business_data

RESTART_IDS = (Account, Counterparty, Invoice, InvoiceLine, Transaction, CategoryRule)


def _restart_ids(session: Session) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return  # SQLite reuses max(rowid) + 1, i.e. 1 for an emptied table
    for model in RESTART_IDS:
        table = model.__tablename__
        if session.scalar(select(func.count()).select_from(model)) == 0:
            session.execute(text("SELECT setval(pg_get_serial_sequence(:t, 'id'), 1, false)"), {"t": table})


def reset_demo(session: Session, business_id: int, actor: str, today: date,
               classifier: Classifier | None = None) -> dict[str, int]:
    """Returns rows removed per table. The caller checks permission and commits."""
    accounts = select(Account.id).where(Account.business_id == business_id)
    invoices = select(Invoice.id).where(Invoice.business_id == business_id)
    runs = select(ForecastRun.id).where(ForecastRun.business_id == business_id)
    counts = sandbox_reset.clear(session, business_id)
    for name, stmt in (
        ("actions", delete(Action).where(Action.business_id == business_id)),
        ("insights", delete(Insight).where(Insight.business_id == business_id)),
        ("forecast_lines", delete(ForecastLine).where(ForecastLine.run_id.in_(runs))),
        ("forecast_runs", delete(ForecastRun).where(ForecastRun.business_id == business_id)),
        ("recurring_series", delete(RecurringSeries).where(RecurringSeries.business_id == business_id)),
        ("transactions", delete(Transaction).where(Transaction.account_id.in_(accounts))),
        ("invoice_lines", delete(InvoiceLine).where(InvoiceLine.invoice_id.in_(invoices))),
        ("invoices", delete(Invoice).where(Invoice.business_id == business_id)),
        ("category_rules", delete(CategoryRule).where(CategoryRule.business_id == business_id)),
        ("counterparties", delete(Counterparty).where(Counterparty.business_id == business_id)),
        ("accounts", delete(Account).where(Account.business_id == business_id)),
        ("policy", delete(Policy).where(Policy.business_id == business_id)),
    ):
        counts[name] = session.execute(stmt, execution_options={"synchronize_session": False}).rowcount
    session.expunge_all()  # bulk deletes: drop stale objects before reloading
    _restart_ids(session)

    business = session.get(Business, business_id)
    golden = json.loads((GOLDEN_DIR / "business.json").read_text(encoding="utf-8"))["business"]
    for key, value in golden.items():
        setattr(business, key, value)
    load_business_data(session, business, GOLDEN_DIR, classifier or NullClassifier())
    audit.append(session, actor, "demo_reset", {"business_id": business_id, "removed": counts}, now=utc_now())
    return counts


def last_reset(session: Session, business_id: int) -> datetime | None:
    """When this business was last reset (conversations older than this are refused)."""
    events = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "demo_reset")
                             .order_by(AuditEvent.seq.desc()))
    ts = next((e.ts for e in events if e.payload.get("business_id") == business_id), None)
    return ts.replace(tzinfo=timezone.utc) if ts is not None and ts.tzinfo is None else ts  # SQLite drops the zone
