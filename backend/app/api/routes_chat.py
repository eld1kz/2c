"""POST /chat: one agent turn, streamed as server-sent events. Any signed-in role (tools are filtered
by role). Rate limited per user (T10): 10 turns a minute, 100 a day, one turn in flight at a time.

Limits count the `agent_turn_started` audit events, like the login lockout, so they survive restarts
and hold across workers. The daily AI budget (DAILY_LLM_BUDGET_USD) is checked here and again before
every model call; once it is spent, chat answers "daily AI budget reached" (503, audited) without
calling the API. Every check runs before a conversation is created, so refused requests
leave nothing behind. The in-flight lock is released whenever the response ends, including when the
client disconnects before streaming starts. Refusals are audited: the first few per user per minute
in full, then one summary event, so a flood cannot grow the audit log without bound.
"""

import json
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from starlette.types import Receive, Scope, Send
from sqlalchemy.orm import Session

from app.agent.runner import ChatModel, ConversationFull, ConversationNotFound, ConversationStore, run_turn
from app.api.deps import current_user, get_chat_model, get_session, get_session_factory
from app.api.schemas import ChatIn
from app.audit import log as audit
from app.config import Settings, get_settings
from app.db.models import AuditEvent, Role, User
from app.services.action_service import utc_now
from app.services.demo_reset import last_reset
from app.services.llm_budget import LlmBudget, to_microusd

router = APIRouter(tags=["chat"])
conversations = ConversationStore()
LIMITS = ((timedelta(minutes=1), 10), (timedelta(days=1), 100))
CHAT_ROLES = (Role.owner, Role.accountant, Role.viewer)  # viewers chat with READ tools only
REFUSAL_EVENTS = ("chat_rate_limited", "chat_refused", "chat_budget_exhausted")
REFUSAL_AUDITS_PER_WINDOW = 5
REFUSAL_WINDOW = timedelta(minutes=1)
SUPPRESSED = "chat_refusals_suppressed"


def _count(session: Session, actor: str, event_types: tuple[str, ...], since: Any) -> int:
    return session.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.actor == actor, AuditEvent.event_type.in_(event_types), AuditEvent.ts >= since))


def _refuse(session: Session, user: User, code: int, reason: str, headers: dict[str, str] | None = None,
            event: str | None = None) -> NoReturn:
    actor, now = f"user:{user.id}", utc_now()
    logged = _count(session, actor, REFUSAL_EVENTS, now - REFUSAL_WINDOW)
    payload = {"business_id": user.business_id, "reason": reason}
    if logged < REFUSAL_AUDITS_PER_WINDOW:
        audit.append(session, actor, event or ("chat_rate_limited" if code == 429 else "chat_refused"), payload,
                     now=now)
    elif not _count(session, actor, (SUPPRESSED,), now - REFUSAL_WINDOW):
        audit.append(session, actor, SUPPRESSED, payload | {
            "note": f"more than {REFUSAL_AUDITS_PER_WINDOW} refusals in {REFUSAL_WINDOW}; the rest are not logged"},
            now=now)
    session.commit()
    raise HTTPException(code, reason, headers=headers)


class ReleasingStream(StreamingResponse):
    """A streaming response that runs `release` however it ends: finished, failed or disconnected
    (even before the first byte, when the body generator never starts)."""

    def __init__(self, content: Iterator[str], release: Callable[[], None], **kwargs: Any) -> None:
        super().__init__(content, **kwargs)
        self.release = release

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.release()


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(current_user), session: Session = Depends(get_session),
         settings: Settings = Depends(get_settings), model: ChatModel = Depends(get_chat_model),
         session_factory: Callable[[], Session] = Depends(get_session_factory)) -> StreamingResponse:
    if user.role not in CHAT_ROLES:
        _refuse(session, user, 403, f"role {user.role.value} may not use the assistant")
    now = utc_now()
    for window, limit in LIMITS:
        if _count(session, f"user:{user.id}", ("agent_turn_started",), now - window) >= limit:
            _refuse(session, user, 429, f"chat limit reached ({limit} per {window})",
                    {"Retry-After": str(int(window.total_seconds()))})
    budget = LlmBudget(session, to_microusd(settings.daily_llm_budget_usd), utc_now)
    if budget.exhausted():
        _refuse(session, user, 503, budget.message(), {"Retry-After": str(budget.seconds_until_reset())},
                event="chat_budget_exhausted")
    if not conversations.begin(user.id):
        _refuse(session, user, 429, "a reply is still streaming", {"Retry-After": "5"})
    limit = budget.limit
    user_id, message, today = user.id, body.message, settings.demo_today
    release = lambda: conversations.end(user_id)  # noqa: E731 - idempotent
    try:
        conversation = conversations.open(user.id, body.conversation_id,
                                          not_before=last_reset(session, user.business_id))
    except ConversationNotFound:
        release()
        _refuse(session, user, 404, "conversation not found")
    except ConversationFull:
        release()
        _refuse(session, user, 409, "conversation is full; start a new one")

    def events() -> Iterator[str]:
        try:
            with session_factory() as turn_session:
                turn_user = turn_session.get(User, user_id)
                turn_budget = LlmBudget(turn_session, limit, utc_now)
                for event in run_turn(turn_session, turn_user, conversation, message, model, today,
                                      budget=turn_budget):
                    yield _sse(event)
        finally:
            release()

    return ReleasingStream(events(), release, media_type="text/event-stream",
                           headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
