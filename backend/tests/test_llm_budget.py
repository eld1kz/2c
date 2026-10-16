"""Daily AI budget (T10) and the cheaper categorizer model: a hard cap on LLM spend per UTC day."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.agent.runner import Usage
from app.config import Settings, get_settings
from app.db.models import AuditEvent, Base, LlmUsage
from app.engine.categorize import ClassifyItem
from app.engine.llm_classifier import AnthropicClassifier, classifier_from_settings
from app.services.llm_budget import LlmBudget, to_microusd
from app.services.llm_cost import FALLBACK, PRICES, cost_microusd
from tests.conftest import ChatHarness
from tests.fakes import ScriptedModel

NOW = datetime(2026, 10, 16, 23, 0, tzinfo=timezone.utc)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_cost_is_integer_micro_dollars() -> None:
    # Sonnet 5.5: $2 in, $10 out, $0.20 cache read, $2.50 cache write per million tokens.
    assert cost_microusd("claude-sonnet-5-5", 10_000, 1_000, 50_000, 5_000) == 52_500
    assert cost_microusd("claude-haiku-5-5", 10_000, 1_000) == 1_500
    assert cost_microusd("claude-sonnet-5-5", 1, 0) == 2 and cost_microusd("claude-haiku-5-5", 1, 0) == 1  # rounds up
    assert PRICES.get("some-new-model") is None and cost_microusd("some-new-model", 1_000, 0) == 1_000 * FALLBACK.input // 1_000_000
    assert to_microusd(Decimal("2")) == 2_000_000 and to_microusd(Decimal("0.05")) == 50_000


def test_budget_counts_today_utc_only(session: Session) -> None:
    clock = SimpleNamespace(now=NOW)
    budget = LlmBudget(session, 100_000, lambda: clock.now)
    assert budget.record("agent", "claude-sonnet-5-5", 40_000, 2_000) == 100_000  # $0.08 + $0.02
    assert budget.spent_today() == 100_000 and budget.exhausted()
    assert budget.seconds_until_reset() == 3_600 and "$0.10" in budget.message()
    clock.now = NOW + timedelta(hours=1, seconds=1)  # 00:00:01 UTC next day
    assert budget.spent_today() == 0 and not budget.exhausted()
    assert session.scalar(select(func.count()).select_from(LlmUsage)) == 1


def _set_budget(monkeypatch: pytest.MonkeyPatch, usd: str) -> None:
    monkeypatch.setattr(get_settings(), "daily_llm_budget_usd", Decimal(usd))


def test_chat_refuses_without_calling_the_api_once_the_budget_is_spent(chat: ChatHarness,
                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    _set_budget(monkeypatch, "0.05")
    with chat.factory() as s:
        LlmBudget(s, 0, lambda: datetime.now(timezone.utc)).record("agent", "claude-sonnet-5-5", 25_000, 0)  # $0.05
        s.commit()
    r = chat.client.post("/chat", headers=chat.login("owner"), json={"message": "Why will I be short?"})
    assert r.status_code == 503 and "daily AI budget ($0.05) is used up" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) > 0
    assert chat.model.requests == []  # the model was never called
    assert "chat_budget_exhausted" in chat.events()


def test_a_running_turn_stops_before_the_next_call(chat: ChatHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_budget(monkeypatch, "0.05")
    chat.model = ScriptedModel([("get_cash_position", {})], ["Cash is fine."],
                               usage=Usage(input_tokens=20_000, output_tokens=2_000))  # $0.06 per call
    events = chat.chat(chat.login("owner"), "Cash?")
    assert len(chat.model.requests) == 1
    assert events[-1][0] == "error" and "daily AI budget" in events[-1][1]["message"]
    assert "agent_budget_exhausted" in chat.events()
    with chat.factory() as s:
        (row,) = s.scalars(select(LlmUsage))
        assert (row.source, row.model, row.cost_microusd) == ("agent", "claude-sonnet-5-5", 60_000)


def test_every_agent_call_is_recorded_under_budget(chat: ChatHarness) -> None:
    chat.model = ScriptedModel([("get_cash_position", {})], ["Okay."], usage=Usage(1_000, 100, 5_000, 0))
    chat.chat(chat.login("owner"), "Cash?")
    with chat.factory() as s:
        rows = list(s.scalars(select(LlmUsage)))
        finished = s.scalar(select(AuditEvent).where(AuditEvent.event_type == "agent_turn_finished"))
    assert [r.cost_microusd for r in rows] == [4_000, 4_000]  # 1,000×2 + 100×10 + 5,000×0.2 µUSD
    assert finished.payload["usage"] == {"input_tokens": 2_000, "output_tokens": 200, "cache_read_tokens": 10_000,
                                         "cache_write_tokens": 0}


class _Messages:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=10_000, output_tokens=1_000, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0),
            content=[SimpleNamespace(type="text", text='{"results": [{"index": 0, "category": "software", '
                                                       '"confidence": 0.9}]}')])


def test_classifier_records_spend_and_stops_at_the_budget(session: Session) -> None:
    client = SimpleNamespace(messages=_Messages())
    budget = LlmBudget(session, 1_500, lambda: NOW)  # one Haiku batch costs exactly $0.0015
    classifier = AnthropicClassifier(client, "claude-haiku-5-5", budget)
    assert [r.category for r in classifier.classify([ClassifyItem(0, "QUILLBOOK ACCOUNTING", "out")])] == ["software"]
    assert classifier.classify([ClassifyItem(0, "QUILLBOOK ACCOUNTING", "out")]) == []  # budget spent: no call
    assert client.messages.calls == 1
    (row,) = session.scalars(select(LlmUsage))
    assert (row.source, row.model, row.cost_microusd) == ("classifier", "claude-haiku-5-5", 1_500)


def test_classifier_uses_its_own_cheaper_model() -> None:
    both = Settings(anthropic_api_key="test-key", llm_model="claude-sonnet-5-5", llm_model_classifier="claude-haiku-5-5")
    assert classifier_from_settings(both).model == "claude-haiku-5-5"
    agent_only = Settings(anthropic_api_key="test-key", llm_model="claude-sonnet-5-5", llm_model_classifier="")
    assert classifier_from_settings(agent_only).model == "claude-sonnet-5-5"  # falls back to LLM_MODEL
    classifier_only = Settings(anthropic_api_key="test-key", llm_model="", llm_model_classifier="claude-haiku-5-5")
    assert classifier_from_settings(classifier_only).model == "claude-haiku-5-5"
