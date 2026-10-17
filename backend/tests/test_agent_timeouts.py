"""Time limits on the agent: each API attempt (CALL_SECONDS, at most CALL_RETRIES retry) and each
whole turn (TURN_SECONDS). A timed-out turn ends with a clean, audited error, keeps the conversation
usable, and releases the per-user chat lock. Time is faked (runner._monotonic): nothing sleeps."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest
from sqlalchemy import select

from app.agent import runner
from app.agent.runner import TIMED_OUT, AnthropicChatModel, ModelTimeout, ModelUnavailable
from app.db.models import AuditEvent, User
from tests.conftest import ChatHarness
from tests.fakes import ScriptedModel


class FakeTime:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_time(monkeypatch: pytest.MonkeyPatch) -> FakeTime:
    t = FakeTime()
    monkeypatch.setattr(runner, "_monotonic", t)
    return t


def _slow(t: FakeTime, seconds: float, blocks: list[Any]):  # noqa: ANN202 - a ScriptedModel step
    def step(_messages: list[dict]) -> list[Any]:
        t.advance(seconds)
        return blocks
    return step


def _well_formed(messages: list[dict]) -> bool:
    """Every tool_use is answered by a tool_result in the next message."""
    for i, m in enumerate(messages):
        if m["role"] == "assistant" and isinstance(m["content"], list):
            uses = {b["id"] for b in m["content"] if b.get("type") == "tool_use"}
            if uses:
                nxt = messages[i + 1]["content"] if i + 1 < len(messages) else []
                if uses - {b.get("tool_use_id") for b in nxt if isinstance(b, dict)}:
                    return False
    return True


def _user_id(chat: ChatHarness, role: str) -> int:
    with chat.factory() as s:
        return s.scalar(select(User.id).where(User.email == f"{role}@emberoak.demo"))


def test_turn_stops_at_the_limit_cleanly_and_releases_the_lock(chat: ChatHarness, fake_time: FakeTime) -> None:
    from app.api import routes_chat

    chat.model = ScriptedModel(
        _slow(fake_time, 70, [("get_cash_position", {})]),
        _slow(fake_time, 70, ["Cash will be short in week 6 because"]),  # crosses 120 s while streaming
    )
    owner = chat.login("owner")
    events = chat.chat(owner, "Why will I be short on cash?")
    names = [e for e, _ in events]
    assert names[-1] == "error" and events[-1][1]["message"] == TIMED_OUT
    assert "done" not in names
    assert len(chat.model.requests) == 2
    assert chat.model.timeouts == [120.0, 50.0]  # the second call only got what was left of the turn
    with chat.factory() as s:
        event = s.scalar(select(AuditEvent).where(AuditEvent.event_type == "agent_turn_timeout"))
        assert event is not None and event.payload["limit_seconds"] == 120.0 and event.payload["iteration"] == 2
    assert "agent_error" not in chat.events()

    # the lock is free and the same conversation carries on with a well-formed history
    assert routes_chat.conversations.begin(_user_id(chat, "owner"))
    routes_chat.conversations.end(_user_id(chat, "owner"))
    conversation_id = events[0][1]["conversation_id"]
    again = chat.chat(owner, "Try again", conversation_id=conversation_id)
    assert again[-1][0] == "done"
    assert _well_formed(chat.model.requests[-1]["messages"])


def test_no_model_call_starts_after_the_deadline(chat: ChatHarness, fake_time: FakeTime) -> None:
    chat.model = ScriptedModel(_slow(fake_time, 125, [("get_cash_position", {})]))
    events = chat.chat(chat.login("owner"), "Why will I be short on cash?")
    assert events[-1][1]["message"] == TIMED_OUT
    assert len(chat.model.requests) == 1  # the tool ran, then the deadline stopped the next call


def test_an_api_timeout_is_reported_as_a_turn_timeout(chat: ChatHarness, fake_time: FakeTime) -> None:
    chat.model = ScriptedModel(ModelTimeout("APITimeoutError"))
    events = chat.chat(chat.login("viewer"), "Hi")
    assert events[-1] == ("error", {"message": TIMED_OUT, "action_ids": []})
    assert "agent_turn_timeout" in chat.events() and "agent_error" not in chat.events()


# --- the Anthropic client --------------------------------------------------------------------


class FakeStream:
    def __init__(self, events: list[Any], on_event: Any = None) -> None:
        self.events, self.on_event = events, on_event

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def __iter__(self):  # noqa: ANN204
        for e in self.events:
            if self.on_event:
                self.on_event()
            yield e

    def get_final_message(self) -> Any:
        usage = SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(content=[], stop_reason="end_turn", usage=usage)


def _model(stream: Any) -> tuple[AnthropicChatModel, list[dict]]:
    calls: list[dict] = []

    def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        if isinstance(stream, Exception):
            raise stream
        return stream

    client = SimpleNamespace(messages=SimpleNamespace(stream=create))
    return AnthropicChatModel(client, "claude-sonnet-5-5"), calls  # type: ignore[arg-type]


def _run(model: AnthropicChatModel, timeout: float) -> list[Any]:
    return list(model.stream(system="s", tools=[{"name": "t"}], messages=[], tool_choice={"type": "auto"}, timeout=timeout))


def test_client_has_a_request_timeout_and_one_retry() -> None:
    model = AnthropicChatModel.connect("sk-test", "claude-sonnet-5-5")
    assert model.client.max_retries == 1
    assert model.client.timeout == 60.0


@pytest.mark.parametrize(("budget", "per_attempt"), [(120.0, 60.0), (50.0, 25.0), (8.0, 4.0)])
def test_each_attempt_fits_the_call_budget_with_its_retry(budget: float, per_attempt: float) -> None:
    model, calls = _model(FakeStream([]))
    _run(model, budget)
    assert calls[0]["timeout"] == per_attempt


def test_api_timeout_becomes_model_timeout() -> None:
    error = anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    model, _ = _model(error)
    with pytest.raises(ModelTimeout):
        _run(model, 120.0)


def test_other_api_errors_stay_unavailable_not_timeout() -> None:
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    model, _ = _model(error)
    with pytest.raises(ModelUnavailable) as raised:
        _run(model, 120.0)
    assert not isinstance(raised.value, ModelTimeout)


def test_a_slow_trickle_of_events_cannot_outlast_the_call(fake_time: FakeTime) -> None:
    text = SimpleNamespace(type="text", text="…")
    model, _ = _model(FakeStream([text] * 10, on_event=lambda: fake_time.advance(20)))
    with pytest.raises(ModelTimeout):
        _run(model, 50.0)
