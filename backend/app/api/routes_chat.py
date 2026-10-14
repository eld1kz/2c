"""POST /chat: one agent turn, streamed as server-sent events. Any signed-in role (tools are filtered
by role). Rate limited per user (T10): 10 turns a minute, 100 a day, one turn in flight at a time.

Limits count the `agent_turn_started` audit events, like the login lockout, so they survive restarts
and hold across workers. Refusals are audited.
"""

import json
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.runner import ChatModel, ConversationFull, ConversationNotFound, ConversationStore, run_turn
from app.api.deps import current_user, get_chat_model, get_session, get_session_factory
from app.api.schemas import ChatIn
from app.audit import log as audit
from app.config import Settings, get_settings
from app.db.models import AuditEvent, User
from app.services.action_service import utc_now

router = APIRouter(tags=["chat"])
conversations = ConversationStore()
LIMITS = ((timedelta(minutes=1), 10), (timedelta(days=1), 100))


def _turns_since(session: Session, actor: str, since: Any) -> int:
    return session.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.actor == actor, AuditEvent.event_type == "agent_turn_started", AuditEvent.ts >= since))


def _refuse(session: Session, user: User, code: int, reason: str, headers: dict[str, str] | None = None) -> None:
    audit.append(session, f"user:{user.id}", "chat_rate_limited" if code == 429 else "chat_refused",
                 {"business_id": user.business_id, "reason": reason}, now=utc_now())
    session.commit()
    raise HTTPException(code, reason, headers=headers)


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(current_user), session: Session = Depends(get_session),
         settings: Settings = Depends(get_settings), model: ChatModel = Depends(get_chat_model),
         session_factory: Callable[[], Session] = Depends(get_session_factory)) -> StreamingResponse:
    now = utc_now()
    for window, limit in LIMITS:
        if _turns_since(session, f"user:{user.id}", now - window) >= limit:
            _refuse(session, user, 429, f"chat limit reached ({limit} per {window})",
                    {"Retry-After": str(int(window.total_seconds()))})
    try:
        conversation = conversations.open(user.id, body.conversation_id)
    except ConversationNotFound:
        _refuse(session, user, 404, "conversation not found")
    except ConversationFull:
        _refuse(session, user, 409, "conversation is full; start a new one")
    if not conversations.begin(user.id):
        _refuse(session, user, 429, "a reply is still streaming", {"Retry-After": "5"})
    user_id, message, today = user.id, body.message, settings.demo_today

    def events() -> Iterator[str]:
        try:
            with session_factory() as turn_session:
                turn_user = turn_session.get(User, user_id)
                for event in run_turn(turn_session, turn_user, conversation, message, model, today):
                    yield _sse(event)
        finally:
            conversations.end(user_id)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
