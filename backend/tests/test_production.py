"""APP_ENV=production: boot refuses development defaults; the shared public demo logins neither lock
each other out nor share chat state (one turn in flight and conversations per sign-in session)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import select

from app.api import routes_chat
from app.auth.jwt import read_token
from app.config import Settings, check_production, get_settings
from app.db.models import AuditEvent
from app.main import app
from seed.load import DEMO_PASSWORD
from tests.conftest import ChatHarness

SECRET = "test-only-jwt-secret-0123456789abcdef"
GOOD = {"app_env": "production", "jwt_secret": SECRET, "anthropic_api_key": "sk-test", "llm_model": "claude-test",
        "database_url": "postgresql+psycopg://ledgerwise:s3cret-random@db:5432/ledgerwise",
        "cors_origins": "https://demo.example.com"}


def _settings(**overrides: str) -> Settings:
    return Settings(_env_file=None, **(GOOD | overrides))  # type: ignore[call-arg]


@pytest.fixture
def production(chat: ChatHarness) -> Iterator[ChatHarness]:
    app.dependency_overrides[get_settings] = lambda: _settings()
    yield chat
    app.dependency_overrides.pop(get_settings, None)


def test_production_config_is_accepted() -> None:
    check_production(_settings())


@pytest.mark.parametrize("overrides", [
    {"database_url": Settings.model_fields["database_url"].default},
    {"database_url": "postgresql+psycopg://ledgerwise:ledgerwise@db:5432/ledgerwise"},
    {"anthropic_api_key": ""},
    {"llm_model": ""},
    {"cors_origins": "http://localhost:3000"},
    {"cors_origins": "https://demo.example.com,http://demo.example.com"},
    {"cors_origins": ""},
])
def test_production_refuses_development_defaults(overrides: dict[str, str]) -> None:
    with pytest.raises(RuntimeError, match="APP_ENV=production refuses to boot"):
        check_production(_settings(**overrides))


def test_development_skips_the_production_checks() -> None:
    check_production(Settings(_env_file=None, jwt_secret=SECRET))  # type: ignore[call-arg]


def test_daily_chat_limit_is_higher_in_production() -> None:
    assert routes_chat.limits(_settings())[1][1] == routes_chat.TURNS_PER_DAY_PRODUCTION == 300
    assert routes_chat.limits(Settings(_env_file=None, jwt_secret=SECRET))[1][1] == 100  # type: ignore[call-arg]


def _fail(chat: ChatHarness, email: str, times: int) -> None:
    for _ in range(times):
        assert chat.client.post("/auth/login", json={"email": email, "password": "wrong"}).status_code == 401


def test_demo_accounts_cannot_be_locked_out_in_production(production: ChatHarness) -> None:
    _fail(production, "owner@emberoak.demo", 8)
    production.login("owner")
    with production.factory() as s:
        types = list(s.scalars(select(AuditEvent.event_type).order_by(AuditEvent.seq)))
    assert types.count("login_failed") == 8 and "login_locked" not in types


def test_other_emails_still_lock_out_in_production(production: ChatHarness) -> None:
    _fail(production, "someone@example.com", 5)
    r = production.client.post("/auth/login", json={"email": "someone@example.com", "password": DEMO_PASSWORD})
    assert r.status_code == 429


def _owner_of(headers: dict[str, str]) -> tuple[int, str]:
    claims = read_token(headers["Authorization"].removeprefix("Bearer "), SECRET)
    return claims.user_id, claims.session_id


def test_each_sign_in_gets_its_own_session_id(chat: ChatHarness) -> None:
    a, b = _owner_of(chat.login("owner")), _owner_of(chat.login("owner"))
    assert a[0] == b[0] and a[1] != b[1]


def test_shared_login_sessions_do_not_block_each_other_in_production(production: ChatHarness) -> None:
    first, second = production.login("owner"), production.login("owner")
    assert routes_chat.conversations.begin(_owner_of(first))  # a reply is streaming in the first session
    r = production.client.post("/chat", headers=first, json={"message": "Hi"})
    assert r.status_code == 429 and "still streaming" in r.json()["detail"]
    production.chat(second, "Hi")  # the other sign-in is not blocked
    routes_chat.conversations.end(_owner_of(first))
    production.chat(first, "Hi")


def test_shared_login_sessions_do_not_see_each_others_conversations_in_production(production: ChatHarness) -> None:
    first, second = production.login("owner"), production.login("owner")
    conversation_id = production.chat(first, "Hi")[0][1]["conversation_id"]
    production.chat(second, "Hi", conversation_id, expect=404)
    production.chat(first, "Again", conversation_id)


def test_outside_production_the_lock_and_conversations_stay_per_user(chat: ChatHarness) -> None:
    first, second = chat.login("owner"), chat.login("owner")
    conversation_id = chat.chat(first, "Hi")[0][1]["conversation_id"]
    chat.chat(second, "Again", conversation_id)
    assert routes_chat.conversations.begin(_owner_of(first)[0])
    r = chat.client.post("/chat", headers=second, json={"message": "Hi"})
    assert r.status_code == 429
    routes_chat.conversations.end(_owner_of(first)[0])


def test_memo_uses_the_session_lock_in_production(production: ChatHarness) -> None:
    first, second = production.login("owner"), production.login("owner")
    assert routes_chat.conversations.begin(_owner_of(first))
    assert production.client.post("/memo", headers=first).status_code == 429
    assert production.client.post("/memo", headers=second).status_code != 429
    routes_chat.conversations.end(_owner_of(first))
