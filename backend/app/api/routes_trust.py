"""Trust & guardrails: GET /trust (services/trust.py). Any signed-in role, read-only, no model."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_session
from app.api.schemas import TrustOut, VerifyOut
from app.config import Settings, get_settings
from app.db.models import User
from app.services.trust import trust

router = APIRouter(tags=["trust"])


@router.get("/trust", response_model=TrustOut)
def get_trust(user: User = Depends(current_user), session: Session = Depends(get_session),
              settings: Settings = Depends(get_settings)) -> TrustOut:
    t = trust(session, user.business_id)
    p = t.policy
    return TrustOut(
        boundaries=t.boundaries,
        agent_can_approve=False,
        limits={"max_single_payment": p.max_single_payment, "max_daily_payments": p.max_daily_payments,
                "currency": p.currency, "reminder_cooldown_days": p.reminder_cooldown_days,
                "require_owner_for": list(p.require_owner_for or []),
                "daily_ai_budget_cents": int(settings.daily_llm_budget_usd * 100), **t.agent_limits},
        activity=t.activity,
        recent_denials=t.recent_denials,
        chain=VerifyOut(ok=t.chain.ok, checked=t.chain.checked, broken_at_seq=t.chain.broken_at_seq,
                        reason=t.chain.reason),
    )
