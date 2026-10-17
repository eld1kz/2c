"""Weekly CFO memo (SPEC §10 `/memo`): written by the agent from engine facts, then cached.

Generating is one agent turn that may use only `draft_cfo_memo` (cash, the gap, top insights, pending
approvals), so it gets the same citation and claim checks, PII masking, time limits, daily AI budget
and audit trail as chat. Only a memo whose every citation checked out is stored; viewing the stored
memo never calls the model. `facts_digest` fingerprints the facts the memo was written from, so the UI
can say when the numbers have changed since. Demo reset deletes stored memos.
"""

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.runner import ChatModel, Conversation, run_turn
from app.agent.tools import AgentMemory
from app.audit import log as audit
from app.db.models import CfoMemo, User
from app.engine.forecast import project
from app.engine.memo import memo_facts
from app.engine.snapshot import load_snapshot
from app.services import ledger
from app.services.action_service import actor_for, utc_now
from app.services.llm_budget import LlmBudget

MEMO_TOOLS = frozenset({"draft_cfo_memo"})
MEMO_REQUEST = (
    "Write this week's CFO memo for the owner. Call draft_cfo_memo for the facts, then write the memo in "
    "markdown with these short sections: Cash today, The cash gap, Top issues, Waiting for your approval, "
    "Next steps. Start with the first section heading: no title, preamble or draft notice (the page shows "
    "that it was written by the assistant). Cite every figure. At most 250 words. Do not draft or propose any action."
)


class MemoUnavailable(Exception):
    """The turn ended with an error (model unavailable, time limit, budget); nothing was stored."""


@dataclass(frozen=True)
class MemoResult:
    message: str
    citations: list[dict[str, Any]]
    warnings: list[str]
    memo: CfoMemo | None  # the stored memo; None when the citation check failed (shown once, not cached)


def facts_digest(session: Session, business_id: int, today: date) -> str:
    snap = load_snapshot(session, business_id, today)
    forecast = project(snap)
    facts = memo_facts(snap, forecast, ledger.list_insights(session, business_id),
                       ledger.pending_actions(session, business_id))
    gap = facts.gap
    data = {
        "cash": facts.position.as_of_cash,
        "gap": None if gap is None else [gap.first_week, gap.last_week, gap.low_week, gap.amount],
        "lowest": [facts.lowest_week, facts.lowest_closing],
        "insights": [[i.id, i.type.value, i.impact_amount] for i in facts.insights],
        "pending": [[a.id, a.tool, a.status.value] for a in facts.pending_actions],
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def latest(session: Session, business_id: int, today: date) -> CfoMemo | None:
    return session.scalar(select(CfoMemo).where(CfoMemo.business_id == business_id, CfoMemo.as_of == today)
                          .order_by(CfoMemo.id.desc()).limit(1))


def generate(session: Session, user: User, model: ChatModel, today: date, budget: LlmBudget | None = None,
             clock: Callable[[], datetime] = utc_now) -> MemoResult:
    """Write the memo with the agent; store it only if every citation is valid. The caller checks role,
    rate limits and budget first (routes_chat.admit)."""
    conversation_id = str(uuid.uuid4())
    conversation = Conversation(conversation_id, user.id, AgentMemory(conversation_id))
    events = list(run_turn(session, user, conversation, MEMO_REQUEST, model, today, clock, budget,
                           allowed_tools=MEMO_TOOLS))
    last = events[-1]
    if last["event"] == "error":
        raise MemoUnavailable(last["data"]["message"])
    done = last["data"]
    actor = actor_for(user).label
    base = {"business_id": user.business_id, "conversation_id": conversation_id}
    if done["warnings"] or not all(c["valid"] for c in done["citations"]):
        audit.append(session, actor, "memo_not_cached", base | {"warnings": done["warnings"][:5]}, now=clock())
        session.commit()
        return MemoResult(done["message"], done["citations"], done["warnings"], None)
    memo = CfoMemo(business_id=user.business_id, as_of=today, generated_at=clock(), generated_by=user.id,
                   message=done["message"], citations=done["citations"],
                   facts_digest=facts_digest(session, user.business_id, today))
    session.add(memo)
    session.flush()
    audit.append(session, actor, "memo_generated", base | {"memo_id": memo.id, "facts_digest": memo.facts_digest},
                 now=clock())
    session.commit()
    return MemoResult(memo.message, memo.citations, [], memo)
