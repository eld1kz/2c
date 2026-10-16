"""Agent runner (SPEC §7): the tool-use loop for one user turn, as a stream of events.

At most MAX_ITERATIONS (6) model calls per turn; the last one is made with tool_choice "none" so the
model must answer with what it has. Tool calls go through agent.tools.dispatch (audited, committed
one by one, so proposals and audit events survive a dropped stream). The final answer is checked
by agent.citations; one failed check gets one rewrite, after which the answer is shown with its
unverified figures flagged. Conversations live in server memory only: the client never sends
history, so it cannot forge tool results.
"""

import threading
import uuid
from collections.abc import Iterator
from dataclasses import asdict, astuple, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol

import anthropic
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.citations import UNVERIFIED_NOTICE, CheckResult, validate
from app.agent.pii import strip_token_marks
from app.agent.prompts import render_system
from app.agent.tools import AgentMemory, ToolContext, dispatch, strip_invisible, tools_for
from app.audit import log as audit
from app.db.models import Business, User
from app.services.action_service import ActionService, actor_for, utc_now
from app.services.ledger import record_exists
from app.services.llm_budget import LlmBudget

MAX_ITERATIONS = 6  # live smoke: no question needs more than 5 calls, including a rewrite
MAX_TOKENS = 3072  # live smoke: the largest single call (thinking included) used ~1.2k output tokens
MAX_TURNS = 30
CONVERSATION_TTL = timedelta(hours=2)
MAX_CONVERSATIONS = 200
MAX_CONVERSATIONS_PER_USER = 20
MAX_AUDITED_MESSAGE_CHARS = 500
UNAVAILABLE = ("The assistant is unavailable right now. Anything already proposed is still in the approvals "
               "inbox.")
STEP_LIMIT = "I stopped after the maximum number of steps for one question; ask me to continue if needed."
CUT_OFF = "(The answer was cut off.)"
REFUSED = "I can't help with that request."


# --- model seam ----------------------------------------------------------------------------


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Usage:
    """Tokens billed for model calls (cache reads and writes are billed at their own rates)."""

    input_tokens: int = 0
    output_tokens: int = 0  # includes thinking
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(*(a + b for a, b in zip(astuple(self), astuple(other))))


@dataclass(frozen=True)
class Final:
    content: list[dict[str, Any]]  # content blocks as plain dicts, replayed unchanged next call
    stop_reason: str
    usage: Usage = Usage()


class ModelUnavailable(Exception):
    pass


class ChatModel(Protocol):
    def stream(self, *, system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]],
               tool_choice: dict[str, Any]) -> Iterator[TextDelta | Final]: ...


class AnthropicChatModel:
    def __init__(self, client: anthropic.Anthropic, model: str) -> None:
        self.client = client
        self.model = model

    @classmethod
    def connect(cls, api_key: str, model: str) -> "AnthropicChatModel":
        return cls(anthropic.Anthropic(api_key=api_key, max_retries=2), model)

    def stream(self, *, system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]],
               tool_choice: dict[str, Any]) -> Iterator[TextDelta | Final]:
        cached_tools = [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}] if tools else tools
        try:
            with self.client.messages.stream(  # cached: tools + system (shared) and the conversation so far
                model=self.model,
                max_tokens=MAX_TOKENS,
                cache_control={"type": "ephemeral"},
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=cached_tools,
                tool_choice=tool_choice,
                messages=messages,
            ) as stream:
                for event in stream:
                    if event.type == "text":
                        yield TextDelta(event.text)
                message = stream.get_final_message()
        except anthropic.APIError as e:
            raise ModelUnavailable(type(e).__name__) from e
        u = message.usage
        usage = Usage(u.input_tokens, u.output_tokens, u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0)
        yield Final([block.to_dict() for block in message.content], message.stop_reason or "end_turn", usage)


# --- conversations -------------------------------------------------------------------------


@dataclass
class Conversation:
    id: str
    user_id: int
    memory: AgentMemory
    messages: list[dict[str, Any]] = field(default_factory=list)
    turns: int = 0
    last_used: datetime = field(default_factory=utc_now)


class ConversationNotFound(LookupError):
    pass


class ConversationFull(Exception):
    pass


class ConversationStore:
    """In-memory, per user, expiring. Also tracks which users have a turn in flight (one at a time)."""

    def __init__(self, clock=utc_now) -> None:  # noqa: ANN001 - a () -> datetime callable
        self.clock = clock
        self._items: dict[str, Conversation] = {}
        self._busy: set[int] = set()
        self._lock = threading.Lock()

    def open(self, user_id: int, conversation_id: str | None) -> Conversation:
        now = self.clock()
        with self._lock:
            for key in [k for k, c in self._items.items() if now - c.last_used > CONVERSATION_TTL]:
                del self._items[key]
            if conversation_id is not None:
                conv = self._items.get(conversation_id)
                if conv is None or conv.user_id != user_id:
                    raise ConversationNotFound(conversation_id)
                if conv.turns >= MAX_TURNS:
                    raise ConversationFull(conversation_id)
            else:
                mine = [k for k, c in self._items.items() if c.user_id == user_id]
                if len(mine) >= MAX_CONVERSATIONS_PER_USER:  # a user only ever evicts their own
                    del self._items[min(mine, key=lambda k: self._items[k].last_used)]
                elif len(self._items) >= MAX_CONVERSATIONS:
                    del self._items[min(self._items, key=lambda k: self._items[k].last_used)]
                new_id = str(uuid.uuid4())
                conv = self._items[new_id] = Conversation(new_id, user_id, AgentMemory(new_id))
            conv.last_used = now
            return conv

    def begin(self, user_id: int) -> bool:
        with self._lock:
            if user_id in self._busy:
                return False
            self._busy.add(user_id)
            return True

    def end(self, user_id: int) -> None:
        with self._lock:
            self._busy.discard(user_id)


# --- the loop ------------------------------------------------------------------------------


def _event(name: str, /, **data: Any) -> dict[str, Any]:
    return {"event": name, "data": data}


def _text_of(content: list[dict[str, Any]]) -> str:
    return "".join(b.get("text", "") for b in content if b.get("type") == "text")


def _skipped(tool_uses: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    """tool_results for tool calls that were not run, so the history stays well formed."""
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": b["id"], "is_error": True,
                                         "content": reason} for b in tool_uses]}


def run_turn(session: Session, user: User, conversation: Conversation, user_text: str, model: ChatModel,
             today: date, clock=utc_now, budget: LlmBudget | None = None) -> Iterator[dict[str, Any]]:  # noqa: ANN001
    business = session.get(Business, user.business_id)
    memory = conversation.memory
    service = ActionService(session, today, clock)
    ctx = ToolContext(session, user, business, today, service, memory)
    conversation.turns += 1
    base = {"business_id": business.id, "conversation_id": conversation.id}
    masked = memory.vault.mask_text(strip_token_marks(strip_invisible(user_text)))
    audit.append(session, actor_for(user).label, "agent_turn_started",
                 {**base, "turn": conversation.turns, "chars": len(user_text),
                  "message": masked[:MAX_AUDITED_MESSAGE_CHARS]}, now=clock())
    session.commit()
    yield _event("turn", conversation_id=conversation.id, turn=conversation.turns)

    messages = conversation.messages
    messages.append({"role": "user", "content": masked})
    system = render_system(business, user.role, today)
    tools = [spec.definition() for spec in tools_for(user)]
    exists = lambda ref: record_exists(session, business.id, ref)  # noqa: E731

    action_ids: list[int] = []
    executed = False
    repaired = False
    answer, stop_reason, notice = "", "", ""
    check: CheckResult | None = None
    usage = Usage()
    max_call_output = 0
    iterations = 0
    for iterations in range(1, MAX_ITERATIONS + 1):
        last = iterations == MAX_ITERATIONS
        if budget is not None and budget.exhausted():  # checked before every call, not only per turn
            audit.append(session, actor_for(user, via_agent=True).label, "agent_budget_exhausted",
                         {**base, "iteration": iterations, "spent_microusd": budget.spent_today()}, now=clock())
            session.commit()
            yield _event("error", message=budget.message(), action_ids=action_ids)
            return
        final: Final | None = None
        try:
            for item in model.stream(system=system, tools=tools, messages=messages,
                                     tool_choice={"type": "none" if last else "auto"}):
                if isinstance(item, TextDelta):
                    yield _event("text", delta=item.text)
                else:
                    final = item
        except ModelUnavailable as e:
            audit.append(session, actor_for(user, via_agent=True).label, "agent_error",
                         {**base, "error": str(e)[:100], "iteration": iterations}, now=clock())
            session.commit()
            yield _event("error", message=UNAVAILABLE, action_ids=action_ids)
            return
        if final is None:  # pragma: no cover - a model must end with Final
            raise RuntimeError("model stream ended without a final message")
        usage += final.usage
        max_call_output = max(max_call_output, final.usage.output_tokens)
        if budget is not None:
            u = final.usage
            budget.record("agent", getattr(model, "model", "unknown"), u.input_tokens, u.output_tokens,
                          u.cache_read_tokens, u.cache_write_tokens)
        messages.append({"role": "assistant", "content": final.content})
        stop_reason = final.stop_reason
        answer = _text_of(final.content)
        tool_uses = [b for b in final.content if b.get("type") == "tool_use"]

        if tool_uses and stop_reason == "tool_use" and not last:
            results = []
            for n, block in enumerate(tool_uses):
                try:
                    outcome = dispatch(ctx, block["name"], block.get("input"))
                    session.commit()
                except SQLAlchemyError as e:
                    session.rollback()
                    messages.append(_skipped(tool_uses[n:], "internal error; not run"))
                    audit.append(session, actor_for(user, via_agent=True).label, "agent_error",
                                 {**base, "error": type(e).__name__, "tool": block["name"]}, now=clock())
                    session.commit()
                    yield _event("error", message=UNAVAILABLE, action_ids=action_ids)
                    return
                if outcome.action:
                    action_ids.append(outcome.action["action_id"])
                    executed = executed or outcome.action["status"] == "executed"
                    yield _event("action", **outcome.action)
                yield _event("tool", name=block["name"], tier=outcome.tier.value if outcome.tier else None,
                             ok=not outcome.is_error)
                results.append({"type": "tool_result", "tool_use_id": block["id"], "content": outcome.content,
                                "is_error": outcome.is_error})
            messages.append({"role": "user", "content": results})
            continue
        if tool_uses:
            messages.append(_skipped(tool_uses, "not run: step limit or truncated answer"))
            notice = STEP_LIMIT if stop_reason == "tool_use" else CUT_OFF
            break
        if stop_reason == "refusal":
            answer, notice = answer or REFUSED, ""
            break
        if stop_reason == "max_tokens":
            notice = CUT_OFF
        check = validate(answer, memory.index, exists, executed)
        if check.ok or repaired or last or stop_reason == "max_tokens":
            break
        repaired = True
        yield _event("reset", reason="citation_check", problems=check.warnings)
        messages.append({"role": "user", "content": check.feedback()})

    if check is None:
        check = validate(answer, memory.index, exists, executed)
    shown = answer.rstrip()
    if not check.ok:
        shown += f"\n\n{UNVERIFIED_NOTICE}"
        audit.append(session, actor_for(user, via_agent=True).label, "agent_citation_failed",
                     {**base, "problems": [p.kind for p in check.problems]}, now=clock())
    if notice:
        shown += f"\n\n{notice}"
    audit.append(session, actor_for(user, via_agent=True).label, "agent_turn_finished",
                 {**base, "iterations": iterations, "stop_reason": stop_reason, "citations_ok": check.ok,
                  "action_ids": action_ids, "usage": asdict(usage), "max_call_output_tokens": max_call_output},
                 now=clock())
    session.commit()
    yield _event("done", message=memory.vault.unmask(shown.strip()),
                 citations=[{"ref": c.ref, "valid": c.valid, "label": c.label, "reason": c.reason}
                            for c in check.citations],
                 warnings=check.warnings, action_ids=action_ids, iterations=iterations)
