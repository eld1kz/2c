"""POST /demo/reset: put the demo business back to its golden state (owner only, audited).

See services/demo_reset.py. The audit log is never touched except for the appended `demo_reset` event.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_session
from app.audit import log as audit
from app.config import Settings, get_settings
from app.db.models import Role, User
from app.services.action_service import actor_for, utc_now
from app.services.demo_reset import reset_demo

router = APIRouter(prefix="/demo", tags=["demo"])


class ResetOut(BaseModel):
    removed: dict[str, int]


@router.post("/reset", response_model=ResetOut)
def reset(user: User = Depends(current_user), session: Session = Depends(get_session),
          settings: Settings = Depends(get_settings)) -> ResetOut:
    actor, business_id = actor_for(user).label, user.business_id
    if user.role != Role.owner:
        audit.append(session, actor, "demo_reset_forbidden", {"business_id": business_id, "role": user.role.value},
                     now=utc_now())
        session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"role {user.role.value} may not reset the demo")
    return ResetOut(removed=reset_demo(session, business_id, actor, settings.demo_today))
