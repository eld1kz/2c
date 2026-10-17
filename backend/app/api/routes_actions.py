"""Approvals API: list, propose, approve (executes), reject. All scoped to the caller's business."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import action_service, current_user, get_session, refusals_keep_audit
from app.api.schemas import ActionDisplayOut, ActionIn, ActionOut
from app.config import Settings, get_settings
from app.db.models import Action, ActionStatus, User
from app.services.action_display import display
from app.services.action_service import ActionService, actor_for

router = APIRouter(prefix="/actions", tags=["actions"])


def _out(session: Session, action: Action, settings: Settings) -> ActionOut:
    shown = ActionDisplayOut.model_validate(display(session, action, settings.demo_today))
    return ActionOut.model_validate(action).model_copy(update={"display": shown})


@router.get("", response_model=list[ActionOut])
def list_actions(action_status: ActionStatus | None = Query(None, alias="status"), user: User = Depends(current_user),
                 session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> list[ActionOut]:
    query = select(Action).where(Action.business_id == user.business_id).order_by(Action.id.desc())
    if action_status is not None:
        query = query.where(Action.status == action_status)
    return [_out(session, a, settings) for a in session.scalars(query)]


@router.post("", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
def propose(body: ActionIn, user: User = Depends(current_user), session: Session = Depends(get_session),
            service: ActionService = Depends(action_service)) -> Action:
    with refusals_keep_audit(session):
        return service.propose(actor_for(user), body.tool, body.params, idempotency_key=body.idempotency_key,
                               rationale=body.rationale, evidence_ids=tuple(body.evidence_ids))


@router.post("/{action_id}/approve", response_model=ActionOut)
def approve(action_id: int, user: User = Depends(current_user), session: Session = Depends(get_session),
            service: ActionService = Depends(action_service), settings: Settings = Depends(get_settings)) -> ActionOut:
    with refusals_keep_audit(session):
        return _out(session, service.approve(user, action_id), settings)


@router.post("/{action_id}/reject", response_model=ActionOut)
def reject(action_id: int, user: User = Depends(current_user), session: Session = Depends(get_session),
           service: ActionService = Depends(action_service), settings: Settings = Depends(get_settings)) -> ActionOut:
    with refusals_keep_audit(session):
        return _out(session, service.reject(user, action_id), settings)
