"""The weekly CFO memo (SPEC §10 `/memo`), see services/cfo_memo.py.

GET /memo: any signed-in role; returns this week's stored memo and whether its facts have changed
since. Never calls the model. POST /memo: owner or accountant (it spends AI budget; viewers get an
audited 403), with the same rate limits, daily budget and one-turn-in-flight lock as chat.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent.runner import ChatModel
from app.api import routes_chat
from app.api.deps import Principal, current_principal, current_user, get_chat_model, get_session
from app.api.schemas import CitationOut, MemoBody, MemoOut
from app.audit import log as audit
from app.config import Settings, get_settings
from app.db.models import CfoMemo, Role, User
from app.services import cfo_memo
from app.services.action_service import actor_for, utc_now
from app.services.cfo_memo import MemoUnavailable

router = APIRouter(tags=["memo"])
MEMO_ROLES = (Role.owner, Role.accountant)


def _body(session: Session, memo: CfoMemo) -> MemoBody:
    author = session.get(User, memo.generated_by)
    return MemoBody(message=memo.message, citations=[CitationOut(**c) for c in memo.citations], warnings=[],
                    as_of=memo.as_of, generated_at=memo.generated_at, generated_by=author.name if author else None)


@router.get("/memo", response_model=MemoOut)
def get_memo(user: User = Depends(current_user), session: Session = Depends(get_session),
             settings: Settings = Depends(get_settings)) -> MemoOut:
    memo = cfo_memo.latest(session, user.business_id, settings.demo_today)
    if memo is None:
        return MemoOut(memo=None, stale=False)
    stale = memo.facts_digest != cfo_memo.facts_digest(session, user.business_id, settings.demo_today)
    return MemoOut(memo=_body(session, memo), stale=stale)


@router.post("/memo", response_model=MemoOut)
def generate_memo(principal: Principal = Depends(current_principal), session: Session = Depends(get_session),
                  settings: Settings = Depends(get_settings), model: ChatModel = Depends(get_chat_model)) -> MemoOut:
    user, owner = principal.user, routes_chat.chat_owner(principal, settings)
    if user.role not in MEMO_ROLES:
        audit.append(session, actor_for(user).label, "memo_forbidden",
                     {"business_id": user.business_id, "role": user.role.value}, now=utc_now())
        session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"role {user.role.value} may not generate the memo")
    budget = routes_chat.admit(session, user, settings, owner)
    try:
        result = cfo_memo.generate(session, user, model, settings.demo_today, budget)
    except MemoUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
    finally:
        routes_chat.conversations.end(owner)
    if result.memo is not None:
        return MemoOut(memo=_body(session, result.memo), stale=False)
    return MemoOut(memo=MemoBody(message=result.message, citations=[CitationOut(**c) for c in result.citations],
                                 warnings=result.warnings, as_of=settings.demo_today, generated_at=None,
                                 generated_by=None), stale=False)
