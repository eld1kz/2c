"""Audit log read + chain verification (any signed-in role).

The chain is global (one sequence for the whole deployment) so `verify` covers every event, but the
event list only shows events whose payload names the caller's business.
"""

from itertools import islice

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_session
from app.api.schemas import AuditEventOut, VerifyOut
from app.audit.verify import verify_chain
from app.db.models import AuditEvent, User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
def list_events(after_seq: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[AuditEvent]:
    events = session.scalars(select(AuditEvent).where(AuditEvent.seq > after_seq).order_by(AuditEvent.seq))
    return list(islice((e for e in events if e.payload.get("business_id") == user.business_id), limit))


@router.get("/verify", response_model=VerifyOut)
def verify(_: User = Depends(current_user), session: Session = Depends(get_session)) -> VerifyOut:
    result = verify_chain(session)
    return VerifyOut(ok=result.ok, checked=result.checked, broken_at_seq=result.broken_at_seq, reason=result.reason)
