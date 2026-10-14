"""Facts for the weekly CFO memo (SPEC §7 draft_cfo_memo). The agent writes them up; Phase 6 renders them.

Everything is taken from the engine as is: cash position, the forecast gap, open insights by
impact and the actions waiting for approval. Nothing here is stored.
"""

from dataclasses import dataclass

from app.db.models import Action, Insight
from app.engine.forecast import Forecast, Gap
from app.engine.position import CashPosition, cash_position
from app.engine.snapshot import Snapshot

TOP_INSIGHTS = 5


@dataclass(frozen=True)
class MemoFacts:
    position: CashPosition
    gap: Gap | None
    lowest_closing: int  # lowest weekly closing over the horizon
    lowest_week: int
    insights: tuple[Insight, ...]  # open, largest impact first
    pending_actions: tuple[Action, ...]  # proposed, waiting for a human


def memo_facts(snap: Snapshot, forecast: Forecast, insights: list[Insight], pending: list[Action]) -> MemoFacts:
    low = min(forecast.weeks, key=lambda w: (w.closing, w.week))
    top = sorted(insights, key=lambda i: (-i.impact_amount, i.id))[:TOP_INSIGHTS]
    return MemoFacts(cash_position(snap), forecast.gap(), low.closing, low.week, tuple(top), tuple(pending))
