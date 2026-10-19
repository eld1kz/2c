"""Today's decisions (SPEC §6.9): the open insights worth the most, each with one prepared action.

`decisions` only reads: sentences come from engine figures, and nothing is drafted until someone
taps the button. `prepare` is that tap. It drafts from the fixed templates and proposes the EXECUTE
action through ActionService (gate, audit), with the signed-in person as proposer. A human still
approves on the approval card. A proposal already waiting for the same target is reused, and
nothing is proposed again while one just sent is inside the cooldown.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log as audit
from app.auth.rbac import can_propose
from app.db.models import Action, ActionStatus, Insight, InsightStatus, InsightType, Invoice, Policy, Tier, User
from app.engine.financing import rank_financing
from app.engine.forecast import Forecast, project
from app.engine.insights.base import money
from app.engine.insights.price_creep import price_rises
from app.engine.snapshot import Snapshot, load_snapshot
from app.engine.whatif import CollectReceivable, DelaySupplierPayments, Scenario, ScenarioError, run_what_if
from app.services import ledger
from app.services.action_service import ActionService, Forbidden, NotFound, actor_for, utc_now
from app.services.drafts import Tone

MAX_DECISIONS = 3
TERMS_EXTENSION_DAYS = 30
FIRM_AFTER_DAYS = 30  # a reminder more than 30 days late is firm, else polite
SEND_TOOL = {"reminder": "send_reminder", "price_email": "send_price_request", "terms_request": "send_terms_request"}


@dataclass(frozen=True)
class Decision:
    insight: Insight
    kind: str  # reminder | price_email | terms_request | ask
    text: str
    target: dict[str, int]  # the send tool's target param: {"invoice_id": …} or {"counterparty_id": …}
    target_name: str | None
    evidence_ids: tuple[str, ...]


def _id(ref: str, kind: str) -> int | None:
    prefix = f"{kind}:"
    return int(ref[len(prefix):]) if ref.startswith(prefix) and ref[len(prefix):].isdigit() else None


def _decision(insight: Insight, snap: Snapshot, forecast: Forecast) -> Decision:
    evidence = tuple(r for r in insight.evidence_ids if isinstance(r, str))
    cur = snap.currency
    invoice_ids = [i for r in evidence if (i := _id(r, "invoice")) is not None]
    first_invoice = snap.invoice_by_id.get(invoice_ids[0]) if invoice_ids else None
    if insight.type == InsightType.LATE_PAYER and first_invoice is not None:
        name = snap.counterparties[first_invoice.counterparty_id].name
        days = (snap.as_of - first_invoice.due_date).days
        late = f" and is {days} days late" if days > 0 else ""
        return Decision(insight, "reminder",
                        f"{name} owes you {money(first_invoice.outstanding, cur)}{late} on {first_invoice.number}.",
                        {"invoice_id": first_invoice.id}, name, evidence)
    if insight.type == InsightType.PRICE_CREEP and first_invoice is not None:
        cp_id = first_invoice.counterparty_id
        rise = next((r for r in price_rises(snap) if r.counterparty_id == cp_id), None)
        if rise is not None:
            name = snap.counterparties[cp_id].name
            return Decision(insight, "price_email",
                            f"{name} raised {rise.sku} by {rise.pct}%: about {money(insight.impact_amount, cur)} "
                            "a year more for you.", {"counterparty_id": cp_id}, name, evidence)
    if insight.type == InsightType.CASH_GAP and (gap := forecast.gap()) is not None:
        when = f"{gap.start:%b} {gap.start.day}"
        text = f"Your cash drops below your cushion from {when}, by up to {money(gap.amount, cur)}."
        terms = next((o for o in rank_financing(gap, forecast, snap).options
                      if o.option_id == "supplier_terms_extension" and o.by_counterparty), None)
        if terms is not None:
            cp_id = terms.by_counterparty[0].counterparty_id
            name = snap.counterparties[cp_id].name
            return Decision(insight, "terms_request", text, {"counterparty_id": cp_id}, name, evidence)
        return Decision(insight, "ask", text, {}, None, evidence)
    return Decision(insight, "ask", insight.title, {}, None, evidence)


def _open_insights(session: Session, business_id: int) -> list[Insight]:
    return ledger.list_insights(session, business_id, status=InsightStatus.open)  # largest impact first


def decisions(session: Session, business_id: int, today: date) -> list[Decision]:
    snap = load_snapshot(session, business_id, today)
    forecast = project(snap)
    return [_decision(i, snap, forecast) for i in _open_insights(session, business_id)[:MAX_DECISIONS]]


def fixes(session: Session, business_id: int, today: date) -> list[tuple[Decision, Scenario]]:
    """What Today's decisions would do to cash if they succeed, as engine what-if scenarios: a reminder →
    the invoice is paid today; a terms request → the supplier's upcoming invoices are paid 30 days later
    (the email asks for that on invoices issued from today). A price email has no figure: the supplier's
    answer is unknown. A scenario that no longer applies to the forecast is left out."""
    forecast = project(load_snapshot(session, business_id, today))
    out: list[tuple[Decision, Scenario]] = []
    for d in decisions(session, business_id, today):
        scenario: Scenario
        match d.kind:
            case "reminder":
                scenario = CollectReceivable(d.target["invoice_id"], today)
            case "terms_request":
                scenario = DelaySupplierPayments(d.target["counterparty_id"], TERMS_EXTENSION_DAYS)
            case _:
                continue
        try:
            run_what_if(forecast, [scenario])
        except ScenarioError:
            continue
        out.append((d, scenario))
    return out


@dataclass(frozen=True)
class Future:
    """Today's chart: the forecast with every fix already approved (sent), and with the rest too."""
    applied: Forecast
    pending: Forecast | None  # applied + the fixes not sent yet; None when none remain
    applied_fixes: tuple[Decision, ...]
    pending_fixes: tuple[Decision, ...]


def future(session: Session, business_id: int, today: date, now: datetime) -> Future:
    """A fix counts as applied once its email went out (the decision shows "Sent"); its what-if is the
    same one the "with fixes" verdict uses (`fixes`). A demo reset clears the actions, so the chart
    goes back to the base forecast."""
    base = project(load_snapshot(session, business_id, today))
    done, todo = [], []
    for d, s in fixes(session, business_id, today):
        (done if sent_for(session, business_id, d, now) is not None else todo).append((d, s))
    applied = run_what_if(base, [s for _, s in done]).scenario if done else base
    pending = run_what_if(applied, [s for _, s in todo]).scenario if todo else None
    return Future(applied, pending, tuple(d for d, _ in done), tuple(d for d, _ in todo))


def _targets(action: Action, target: dict[str, int]) -> bool:
    return all((action.params or {}).get(k) == v for k, v in target.items())


def pending_for(session: Session, business_id: int, d: Decision) -> Action | None:
    tool = SEND_TOOL.get(d.kind)
    if tool is None:
        return None
    for a in session.scalars(select(Action).where(Action.business_id == business_id, Action.tool == tool,
                                                  Action.status == ActionStatus.proposed).order_by(Action.id.desc())):
        if _targets(a, d.target):
            return a
    return None


def sent_for(session: Session, business_id: int, d: Decision, now: datetime) -> Action | None:
    """An email of this kind to this target sent within the reminder cooldown (the gate would refuse another)."""
    tool = SEND_TOOL.get(d.kind)
    policy = session.get(Policy, business_id)
    if tool is None or policy is None:
        return None
    since = now - timedelta(days=policy.reminder_cooldown_days)
    for a in session.scalars(select(Action).where(Action.business_id == business_id, Action.tool == tool,
                                                  Action.status == ActionStatus.executed, Action.decided_at >= since)
                             .order_by(Action.id.desc())):
        if _targets(a, d.target):
            return a
    return None


def prepare(session: Session, service: ActionService, user: User, insight_id: int, today: date) -> Action:
    """Draft and propose the decision's action (or return the one already waiting)."""
    decision = next((d for d in decisions(session, user.business_id, today) if d.insight.id == insight_id), None)
    actor = actor_for(user)
    base = {"business_id": user.business_id, "insight_id": insight_id}
    if decision is None or decision.kind not in SEND_TOOL:
        audit.append(session, actor.label, "today_prepare_refused", base | {"reason": "no action for this insight"},
                     now=utc_now())
        raise NotFound(f"no action to prepare for insight {insight_id}")
    tool = SEND_TOOL[decision.kind]
    if not can_propose(user.role, Tier.EXECUTE, tool):
        audit.append(session, actor.label, "today_prepare_forbidden", base | {"tool": tool, "role": user.role.value},
                     now=utc_now())
        raise Forbidden(f"role {user.role.value} may not propose {tool}")
    existing = pending_for(session, user.business_id, decision)
    if existing is not None:
        return existing
    match decision.kind:
        case "reminder":
            invoice = session.get(Invoice, decision.target["invoice_id"])
            days = (today - invoice.due_date).days if invoice is not None else 0
            draft = service.record_draft(actor, decision.target["invoice_id"],
                                         Tone.firm if days > FIRM_AFTER_DAYS else Tone.polite)
            params = {"invoice_id": decision.target["invoice_id"], "draft_id": draft.id}
        case "price_email":
            draft = service.record_price_draft(actor, decision.target["counterparty_id"])
            params = {"counterparty_id": decision.target["counterparty_id"], "draft_id": draft.id}
        case _:
            draft = service.record_terms_draft(actor, decision.target["counterparty_id"], TERMS_EXTENSION_DAYS)
            params = {"counterparty_id": decision.target["counterparty_id"], "draft_id": draft.id}
    return service.propose(actor, tool, params, idempotency_key=f"today:{insight_id}:{draft.id}",
                           rationale=decision.text,
                           evidence_ids=(f"insight:{insight_id}", *decision.evidence_ids[:19]))
