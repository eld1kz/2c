"""POST /chat: auth, input limits, rate limit (T10), configuration."""

from sqlalchemy import select

from app.api.deps import get_chat_model
from app.config import get_settings
from app.db.models import AuditEvent, User
from app.main import app
from tests.conftest import ChatHarness


def test_token_required(chat: ChatHarness) -> None:
    assert chat.client.post("/chat", json={"message": "hi"}).status_code == 401


def test_message_is_validated(chat: ChatHarness) -> None:
    owner = chat.login("owner")
    for body in ({"message": ""}, {"message": "x" * 4001}, {"message": "hi", "extra": 1},
                 {"message": "hi", "conversation_id": "not-a-uuid"}):
        assert chat.client.post("/chat", headers=owner, json=body).status_code == 422


def test_stream_shape(chat: ChatHarness) -> None:
    events = chat.chat(chat.login("viewer"), "Hello")
    assert [name for name, _ in events] == ["turn", "text", "done"]
    assert events[-1][1]["message"] == "Done." and events[-1][1]["iterations"] == 1


def test_rate_limit_per_minute(chat: ChatHarness) -> None:
    owner = chat.login("owner")
    for _ in range(10):
        chat.chat(owner, "Hi")
    r = chat.client.post("/chat", headers=owner, json={"message": "Hi"})
    assert r.status_code == 429 and r.headers["Retry-After"] == "60"
    with chat.factory() as s:
        event = s.scalar(select(AuditEvent).where(AuditEvent.event_type == "chat_rate_limited"))
        assert event is not None and event.payload["business_id"] == 1
    chat.chat(chat.login("viewer"), "Hi")  # other users are not affected


def test_one_turn_in_flight_per_user(chat: ChatHarness) -> None:
    from app.api import routes_chat

    owner = chat.login("owner")
    with chat.factory() as s:
        user_id = s.scalar(select(User.id).where(User.email == "owner@emberoak.demo"))
    assert routes_chat.conversations.begin(user_id)
    r = chat.client.post("/chat", headers=owner, json={"message": "Hi"})
    assert r.status_code == 429 and "still streaming" in r.json()["detail"]
    routes_chat.conversations.end(user_id)
    chat.chat(owner, "Hi")


def test_unconfigured_model_is_503(chat: ChatHarness, monkeypatch) -> None:  # noqa: ANN001
    del app.dependency_overrides[get_chat_model]
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    r = chat.client.post("/chat", headers=chat.login("owner"), json={"message": "Hi"})
    assert r.status_code == 503


def test_unknown_conversation_is_404(chat: ChatHarness) -> None:
    chat.chat(chat.login("owner"), "Hi", conversation_id="00000000-0000-4000-8000-000000000000", expect=404)
