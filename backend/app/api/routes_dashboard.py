"""Read API for the web UI: who am I, cash position, 13-week forecast, insights, AI budget.

Any signed-in role may read. Everything is scoped to the caller's business and computed by the
engine (`engine/`), so the frontend only formats integers. Never writes.
"""

from datetime import date, timedelta, timezone

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_session
from app.api.schemas import (
    EvidenceRef,
    ForecastLineOut,
    ForecastOut,
    ForecastWeekLinesOut,
    ForecastWeekOut,
    GapOut,
    InsightOut,
    LlmBudgetOut,
    LowestOut,
    MeBusiness,
    MeOut,
    MeUser,
    PositionOut,
)
from app.config import Settings, get_settings
from app.db.models import Business, InsightStatus, InsightType, User
from app.engine.forecast import HORIZON_WEEKS, Forecast, Week, project
from app.engine.position import cash_position
from app.engine.snapshot import load_snapshot
from app.services import ledger
from app.services.action_service import utc_now
from app.services.llm_budget import LlmBudget, to_microusd
from app.services.llm_cost import usd

router = APIRouter(tags=["dashboard"])


def _evidence(session: Session, business_id: int, refs: list[str]) -> list[EvidenceRef]:
    names = ledger.labels(session, business_id, refs)
    return [EvidenceRef(ref=r, label=names.get(r)) for r in refs]


def _week(w: Week) -> ForecastWeekOut:
    return ForecastWeekOut(week=w.week, label=f"Week {w.week} ({w.start:%b} {w.start.day})", start=w.start,
                           end=w.start + timedelta(days=6), opening_cents=w.opening, inflows_cents=w.inflows,
                           outflows_cents=w.outflows, closing_cents=w.closing, below_buffer=w.below_buffer)


def _forecast(session: Session, user: User, today: date) -> Forecast:
    return project(load_snapshot(session, user.business_id, today))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user), session: Session = Depends(get_session),
       settings: Settings = Depends(get_settings)) -> MeOut:
    business = session.get(Business, user.business_id)
    return MeOut(user=MeUser(id=user.id, name=user.name, email=user.email, role=user.role.value),
                 business=MeBusiness(id=business.id, name=business.name, industry=business.industry,
                                     currency=business.base_currency, min_cash_buffer_cents=business.min_cash_buffer),
                 as_of=settings.demo_today)


@router.get("/position", response_model=PositionOut)
def position(user: User = Depends(current_user), session: Session = Depends(get_session),
             settings: Settings = Depends(get_settings)) -> PositionOut:
    pos = cash_position(load_snapshot(session, user.business_id, settings.demo_today))
    return PositionOut(as_of=settings.demo_today, currency=pos.currency, cash_cents=pos.as_of_cash,
                       min_cash_buffer_cents=pos.min_cash_buffer, headroom_cents=pos.headroom,
                       evidence=_evidence(session, user.business_id, [f"account:{a}" for a in pos.account_ids]))


@router.get("/forecast", response_model=ForecastOut)
def forecast(user: User = Depends(current_user), session: Session = Depends(get_session),
             settings: Settings = Depends(get_settings)) -> ForecastOut:
    fc = _forecast(session, user, settings.demo_today)
    low = min(fc.weeks, key=lambda w: (w.closing, w.week))
    gap = fc.gap()
    return ForecastOut(
        as_of=fc.as_of, currency=fc.currency, min_cash_buffer_cents=fc.min_cash_buffer,
        weeks=[_week(w) for w in fc.weeks], lowest=LowestOut(week=low.week, closing_cents=low.closing),
        gap=None if gap is None else GapOut(
            first_week=gap.first_week, last_week=gap.last_week, low_week=gap.low_week, amount_cents=gap.amount,
            start=gap.start, low_week_end=gap.low_week_end,
            weeks_below=[w.week for w in fc.weeks if w.below_buffer]),
    )


@router.get("/forecast/weeks/{week}", response_model=ForecastWeekLinesOut)
def forecast_week(week: int = Path(ge=1, le=HORIZON_WEEKS), user: User = Depends(current_user),
                  session: Session = Depends(get_session),
                  settings: Settings = Depends(get_settings)) -> ForecastWeekLinesOut:
    fc = _forecast(session, user, settings.demo_today)
    lines = fc.lines_in(week)
    names = ledger.labels(session, user.business_id, [s for ln in lines for s in ln.source_ids])
    cps = ledger.labels(session, user.business_id,
                        [f"counterparty:{ln.counterparty_id}" for ln in lines if ln.counterparty_id])
    return ForecastWeekLinesOut(week=_week(fc.weeks[week - 1]), lines=[
        ForecastLineOut(date=ln.on, kind=ln.kind.value, amount_cents=ln.amount, face_cents=ln.face,
                        probability_bp=ln.probability_bp, probability_display=f"{ln.probability_bp / 100:g}%",
                        counterparty_name=cps.get(f"counterparty:{ln.counterparty_id}"),
                        sources=[EvidenceRef(ref=s, label=names.get(s)) for s in ln.source_ids])
        for ln in lines])


@router.get("/insights", response_model=list[InsightOut])
def insights(insight_status: InsightStatus = InsightStatus.open, insight_type: InsightType | None = None,
             user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[InsightOut]:
    rows = ledger.list_insights(session, user.business_id, type_=insight_type, status=insight_status)
    names = ledger.labels(session, user.business_id, [e for i in rows for e in i.evidence_ids])
    return [InsightOut(ref=f"insight:{i.id}", id=i.id, type=i.type.value, severity=i.severity.value, title=i.title,
                       impact_cents=i.impact_amount, currency=i.currency, impact_period=i.impact_period,
                       status=i.status.value, detected_at=i.detected_at,
                       evidence=[EvidenceRef(ref=e, label=names.get(e)) for e in i.evidence_ids])
            for i in rows]


@router.get("/llm-budget", response_model=LlmBudgetOut)
def llm_budget(_: User = Depends(current_user), session: Session = Depends(get_session),
               settings: Settings = Depends(get_settings)) -> LlmBudgetOut:
    budget = LlmBudget(session, to_microusd(settings.daily_llm_budget_usd), utc_now)
    spent = budget.spent_today()
    remaining = max(budget.limit - spent, 0)
    now = utc_now().astimezone(timezone.utc)
    return LlmBudgetOut(limit_microusd=budget.limit, spent_microusd=spent, remaining_microusd=remaining,
                        limit_display=usd(budget.limit), remaining_display=usd(remaining),
                        exhausted=budget.exhausted(),
                        resets_at=now + timedelta(seconds=budget.seconds_until_reset()))
