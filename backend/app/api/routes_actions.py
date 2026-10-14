"""Approvals API: list, propose, approve (executes), reject. All scoped to the caller's business."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import action_service, current_user, get_session, refusals_keep_audit
from app.api.schemas import ActionIn, ActionOut
from app.db.models import Action, ActionStatus, User
from app.services.action_service import ActionService, actor_for

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("", response_model=list[ActionOut])
def list_actions(action_status: ActionStatus | None = Query(None, alias="status"), user: User = Depends(current_user),
                 session: Session = Depends(get_session)) -> list[Action]:
    query = select(Action).where(Action.business_id == user.business_id).order_by(Action.id.desc())
    if action_status is not None:
        query = query.where(Action.status == action_status)
    return list(session.scalars(query))


@router.post("", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
def propose(body: ActionIn, user: User = Depends(current_user), session: Session = Depends(get_session),
            service: ActionService = Depends(action_service)) -> Action:
    with refusals_keep_audit(session):
        return service.propose(actor_for(user), body.tool, body.params, idempotency_key=body.idempotency_key,
                               rationale=body.rationale, evidence_ids=tuple(body.evidence_ids))


@router.post("/{action_id}/approve", response_model=ActionOut)
def approve(action_id: int, user: User = Depends(current_user), session: Session = Depends(get_session),
            service: ActionService = Depends(action_service)) -> Action:
    with refusals_keep_audit(session):
        return service.approve(user, action_id)


@router.post("/{action_id}/reject", response_model=ActionOut)
def reject(action_id: int, user: User = Depends(current_user), session: Session = Depends(get_session),
           service: ActionService = Depends(action_service)) -> Action:
    with refusals_keep_audit(session):
        return service.reject(user, action_id)
