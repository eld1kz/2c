"""Today (SPEC §6.9): the home screen and its one-tap prepared actions.

GET /today: any signed-in role; computed by the engine, never writes and never calls the model.
POST /today/decisions/{insight_id}/prepare: drafts from a fixed template and proposes the action
through ActionService (gate, audit); owner, or accountant for reminders. It returns the proposal for
the approval card; nothing is sent until a human approves it.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import action_service, current_user, get_session, refusals_keep_audit
from app.api.routes_actions import _out
from app.api.routes_paperwork import _lines, _period
from app.api.schemas import (
    ActionOut,
    BillOut,
    EvidenceRef,
    FutureFixOut,
    FutureOut,
    FutureWeekOut,
    TeamSummaryOut,
    SafeToSpendOut,
    SpendingOut,
    TodayDecisionOut,
    TodayOut,
)
from app.config import Settings, get_settings
from app.db.models import User
from app.engine import statements as st
from app.engine.forecast import project
from app.engine.snapshot import load_snapshot
from app.engine.today import outlook, safe_to_spend, spending
from app.api.routes_team import pay_visible
from app.services import ledger, today
from app.services.team import team
from app.services.action_service import ActionService, utc_now

router = APIRouter(prefix="/today", tags=["today"])


@router.get("", response_model=TodayOut)
def get_today(user: User = Depends(current_user), session: Session = Depends(get_session),
              settings: Settings = Depends(get_settings)) -> TodayOut:
    day = settings.demo_today
    snap = load_snapshot(session, user.business_id, day)
    safe = safe_to_spend(snap, project(snap))
    spent = spending(st.profit_and_loss(snap, st.previous_month(day)))
    decisions = today.decisions(session, user.business_id, day)
    refs = [f"account:{a}" for a in snap.account_ids] + [b.ref for b in safe.bills]
    refs += [f"insight:{d.insight.id}" for d in decisions] + [r for d in decisions for r in d.evidence_ids]
    names = ledger.labels(session, user.business_id, sorted(set(refs)))

    def ev(ref: str) -> EvidenceRef:
        return EvidenceRef(ref=ref, label=names.get(ref))

    def out(d: today.Decision) -> TodayDecisionOut:
        pending, sent = today.pending_for(session, user.business_id, d), today.sent_for(session, user.business_id, d, utc_now())
        return TodayDecisionOut(
            insight=ev(f"insight:{d.insight.id}"), type=d.insight.type.value, kind=d.kind, text=d.text,
            impact_cents=d.insight.impact_amount, impact_period=d.insight.impact_period, target_name=d.target_name,
            evidence=[ev(r) for r in d.evidence_ids[:6]], pending_action_id=pending.id if pending else None,
            sent_action_id=sent.id if sent else None)

    crew = team(snap)
    ahead = today.future(session, user.business_id, day, utc_now())
    now_view, then = outlook(ahead.applied), outlook(ahead.pending) if ahead.pending else None
    pending_weeks = ahead.pending.weeks if ahead.pending else [None] * len(ahead.applied.weeks)

    def fix(d: today.Decision) -> FutureFixOut:
        return FutureFixOut(insight_id=d.insight.id, kind=d.kind, name=d.target_name or "")

    future = FutureOut(
        cushion_cents=ahead.applied.min_cash_buffer,
        weeks=[FutureWeekOut(week=w.week, start=w.start, closing_cents=w.closing,
                             pending_closing_cents=p.closing if p else None, below_cushion=w.below_buffer)
               for w, p in zip(ahead.applied.weeks, pending_weeks)],
        headline=now_view.headline, detail=now_view.detail, pending_headline=then.headline if then else None,
        applied=[fix(d) for d in ahead.applied_fixes], pending=[fix(d) for d in ahead.pending_fixes])

    return TodayOut(
        as_of=day, currency=snap.currency, name=user.name, future=future,
        team=TeamSummaryOut(people=len(crew.members), weekly_total_cents=crew.weekly_total if pay_visible(user) else None),
        decisions=[out(d) for d in decisions],
        safe_to_spend=SafeToSpendOut(
            cash_cents=safe.cash, cushion_cents=safe.cushion, bills_total_cents=safe.bills_total,
            amount_cents=safe.amount, short_by_cents=safe.short_by, accounts=[ev(f"account:{a}") for a in snap.account_ids],
            bills=[BillOut(date=b.on, source=ev(b.ref), amount_cents=b.amount) for b in safe.bills]),
        spending=SpendingOut(period=_period(spent.pnl.period), lines=_lines(spent.lines), total_cents=spent.total))


@router.post("/decisions/{insight_id}/prepare", response_model=ActionOut)
def prepare(insight_id: int, user: User = Depends(current_user), session: Session = Depends(get_session),
            service: ActionService = Depends(action_service), settings: Settings = Depends(get_settings)) -> ActionOut:
    with refusals_keep_audit(session):
        action = today.prepare(session, service, user, insight_id, settings.demo_today)
        return _out(session, action, settings)
