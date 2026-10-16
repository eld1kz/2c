"""Daily AI budget (T10): a hard cap on what the app can spend on the LLM per UTC day.

Every billed model call (agent and categorizer) is recorded in `llm_usage` with its cost in integer
micro-dollars. Before each call the caller asks `exhausted()`; once today's recorded spend reaches
DAILY_LLM_BUDGET_USD, no further call is made until 00:00 UTC. A call already running can overshoot
by at most its own cost (bounded by max_tokens).
"""

from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import LlmUsage
from app.services.llm_cost import MICRO, cost_microusd

BUDGET_MESSAGE = "The daily AI budget ({limit}) is used up. The assistant is available again after 00:00 UTC."


def to_microusd(amount: Decimal) -> int:
    return int(amount * MICRO)


class LlmBudget:
    def __init__(self, session: Session, limit_microusd: int, clock: Callable[[], datetime]) -> None:
        self.session = session
        self.limit = limit_microusd
        self.clock = clock

    def _today(self) -> datetime:
        return self.clock().astimezone(timezone.utc)

    def spent_today(self) -> int:
        day = self._today().date()
        return int(self.session.scalar(
            select(func.coalesce(func.sum(LlmUsage.cost_microusd), 0)).where(LlmUsage.day == day)))

    def exhausted(self) -> bool:
        return self.spent_today() >= self.limit

    def seconds_until_reset(self) -> int:
        now = self._today()
        midnight = datetime.combine(now.date() + timedelta(days=1), time(), tzinfo=timezone.utc)
        return max(int((midnight - now).total_seconds()), 1)

    def message(self) -> str:
        return BUDGET_MESSAGE.format(limit=f"${self.limit // MICRO:,}.{self.limit % MICRO // 10_000:02d}")

    def record(self, source: str, model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0,
               cache_write_tokens: int = 0) -> int:
        """Store one call's usage (flushed with the caller's session); returns its cost in µUSD."""
        cost = cost_microusd(model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)
        now = self._today()
        self.session.add(LlmUsage(ts=now, day=now.date(), source=source, model=model, input_tokens=input_tokens,
                                  output_tokens=output_tokens, cache_read_tokens=cache_read_tokens,
                                  cache_write_tokens=cache_write_tokens, cost_microusd=cost))
        self.session.flush()
        return cost
