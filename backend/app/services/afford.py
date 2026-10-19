"""Can I afford it? (SPEC §6.9): a question → one what-if → the engine's verdict → one cited sentence.

The agent's only job is to turn the owner's words into one scenario (a new regular cost, a payroll
raise or a one-off purchase) and phrase the answer. It runs one turn limited to `check_affordability`,
with the same citation and claim checks, PII masking, time limits and AI budget as chat. The verdict
returned to the UI is recomputed here from the scenario the tool validated, never read from the text;
an answer that doesn't open with that verdict carries a warning. Nothing is stored.

A second verdict, also from the engine, answers the same plan in the world where Today's prepared
fixes succeed (services/today.fixes: the late invoice is paid, the supplier agrees to longer terms).
The AI sentence speaks only to today's verdict.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.agent.runner import ChatModel, Conversation, run_turn
from app.agent.tools import AgentMemory
from app.db.models import User
from app.engine.snapshot import load_snapshot
from app.services.action_service import utc_now
from app.services.llm_budget import LlmBudget
from app.engine.afford import Affordability
from app.services import today as today_service
from app.services.scenarios import AffordScenarioIn, assess

AFFORD_TOOLS = frozenset({"check_affordability"})
VERDICT_WORDS = {"yes": "Yes", "not_yet": "Not yet", "no": "No"}
MAX_QUESTION_CHARS = 300
REQUEST = (
    "The owner asks whether the business can afford something. Turn the question into exactly one scenario "
    "and call check_affordability once: a new hire or another new regular cost is add_recurring (negative "
    "amount_cents per occurrence, the cadence and start they give; start today if they give none); a raise for "
    "staff given as a percent is raise_payroll (percent as a whole number, start today if none given); a raise "
    "given as an amount for one person is add_recurring (negative amount_cents, that cadence); a one-time purchase is "
    "one_off (negative amount_cents, today unless they give a date). Then answer in ONE sentence that starts "
    "with the tool's verdict, written exactly \"Yes\", \"Not yet\" or \"No\". For Not yet, give the earliest safe "
    "start. For No, give the reason from the tool result (the week cash already falls below the cushion). "
    "Cite every figure. Do not restate the cost, amount or percent the owner gave (it is their assumption, not "
    "a figure from the records): call it \"the hire\", \"the raise\" or \"the purchase\". Do not draft or propose "
    "anything.\n\nThe owner's question: "
)
_adapter: TypeAdapter[Any] = TypeAdapter(AffordScenarioIn)


class AffordUnavailable(Exception):
    """The turn ended with an error (model unavailable, time limit, budget)."""


@dataclass(frozen=True)
class AffordAnswer:
    verdict: str | None  # yes | not_yet | no, from the engine; None if no plan was checked
    earliest_safe_start: date | None
    message: str
    citations: list[dict[str, Any]]
    warnings: list[str]
    scenarios: list[dict[str, Any]]  # the checked plan, for the before/after chart
    detail: Affordability | None = None  # today's verdict in full (requested start, first week already short)
    with_fixes: Affordability | None = None  # the verdict if Today's fixes succeed; None when there are none
    fixes: tuple[today_service.Decision, ...] = ()


def ask(session: Session, user: User, model: ChatModel, today: date, question: str, budget: LlmBudget | None = None,
        clock: Callable[[], datetime] = utc_now) -> AffordAnswer:
    """The caller checks role, rate limits and budget first (routes_chat.admit)."""
    conversation_id = str(uuid.uuid4())
    conversation = Conversation(conversation_id, user.id, AgentMemory(conversation_id))
    events = list(run_turn(session, user, conversation, REQUEST + question, model, today, clock, budget,
                           allowed_tools=AFFORD_TOOLS))
    last = events[-1]
    if last["event"] == "error":
        raise AffordUnavailable(last["data"]["message"])
    done = last["data"]
    warnings = list(done["warnings"])
    checked = [e["data"]["scenarios"] for e in events if e["event"] == "tool" and e["data"].get("name") ==
               "check_affordability" and e["data"].get("ok") and e["data"].get("scenarios")]
    if not checked:
        return AffordAnswer(None, None, done["message"], done["citations"],
                            [*warnings, "The question couldn't be turned into a plan to check."], [])
    plan = checked[-1][:1]
    snap, item = load_snapshot(session, user.business_id, today), _adapter.validate_python(plan[0])
    verdict = assess(session, snap, today, item)
    fixes = today_service.fixes(session, user.business_id, today)
    with_fixes = assess(session, snap, today, item, [s for _, s in fixes]) if fixes else None
    word = VERDICT_WORDS[verdict.verdict]
    opening = done["message"].lstrip(" *#_>\n")
    if not opening.startswith(word) or (word == "No" and opening.startswith("Not yet")):
        warnings.append(f"The answer doesn't open with the verdict from your forecast: {word}.")
    session.commit()
    return AffordAnswer(verdict.verdict, verdict.earliest_safe_start, done["message"], done["citations"], warnings, plan,
                        verdict, with_fixes, tuple(d for d, _ in fixes))
