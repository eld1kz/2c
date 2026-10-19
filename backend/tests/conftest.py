import json
import os
import socket
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Test-only signing key so app.main passes its startup JWT_SECRET check.
os.environ["JWT_SECRET"] = "test-only-jwt-secret-0123456789abcdef"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import DEFAULT_DEMO_TODAY
from app.db.models import AuditEvent, Base, Business, Counterparty, Invoice, User
from app.engine.categorize import NullClassifier
from app.policy.gate import Actor
from app.services.action_service import ActionService, actor_for
from seed.load import DEMO_PASSWORD, load
from tests.fakes import FakeClassifier, ScriptedModel


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may reach the network (LLM calls must be mocked)."""

    def blocked(*args: object, **kwargs: object) -> None:
        raise RuntimeError("network access is disabled in tests")

    real_connect, real_socketpair = socket.socket.connect, socket.socketpair

    def loopback_pair(*args: object, **kwargs: object) -> tuple[socket.socket, socket.socket]:
        """On Windows socketpair() connects over loopback (asyncio's self-pipe); that is not network."""
        socket.socket.connect = real_connect  # type: ignore[method-assign]
        try:
            return real_socketpair(*args, **kwargs)  # type: ignore[arg-type]
        finally:
            socket.socket.connect = blocked  # type: ignore[method-assign,assignment]

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "socketpair", loopback_pair)


@pytest.fixture
def golden_db() -> Iterator[tuple[Session, Business, FakeClassifier]]:
    """Golden data loaded through the real pipeline into in-memory SQLite, LLM mocked."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    classifier = FakeClassifier()
    with Session(engine) as session:
        business = load(session, classifier=classifier)
        yield session, business, classifier


@pytest.fixture(params=["null", "llm"])
def golden_path(request: pytest.FixtureRequest) -> Iterator[tuple[str, Session, Business]]:
    """Golden data on both classifier paths: no LLM (Quillbook → review) and mocked LLM (Quillbook → series)."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    classifier = NullClassifier() if request.param == "null" else FakeClassifier()
    with Session(engine) as session:
        yield request.param, session, load(session, classifier=classifier)


class FakeClock:
    """Injectable wall clock for ActionService (cooldowns, audit timestamps)."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@dataclass
class Demo:
    session: Session
    business: Business
    service: ActionService
    clock: FakeClock
    users: dict[str, User]
    invoices: dict[str, Invoice]
    counterparties: dict[str, Counterparty]

    def actor(self, role: str) -> Actor:
        return actor_for(self.users[role])


@pytest.fixture
def demo(golden_db: tuple[Session, Business, FakeClassifier]) -> Demo:
    """Golden data + ActionService with a fake clock and lookups by role / invoice number / name."""
    session, business, _ = golden_db
    clock = FakeClock(datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc))
    return Demo(
        session=session,
        business=business,
        service=ActionService(session, DEFAULT_DEMO_TODAY, clock),
        clock=clock,
        users={u.role.value: u for u in session.scalars(select(User))},
        invoices={i.number: i for i in session.scalars(select(Invoice))},
        counterparties={c.name: c for c in session.scalars(select(Counterparty))},
    )


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for chunk in body.split("\n\n"):
        if chunk.strip():
            name_line, data_line = chunk.split("\n", 1)
            events.append((name_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))))
    return events


@dataclass
class ChatHarness:
    """The HTTP app over golden data in SQLite, with the chat model replaced by a ScriptedModel."""

    client: TestClient
    factory: sessionmaker
    model: ScriptedModel

    def login(self, role: str) -> dict[str, str]:
        r = self.client.post("/auth/login", json={"email": f"{role}@emberoak.demo", "password": DEMO_PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def chat(self, headers: dict[str, str], message: str, conversation_id: str | None = None,
             expect: int = 200) -> list[tuple[str, dict]]:
        body = {"message": message} | ({"conversation_id": conversation_id} if conversation_id else {})
        r = self.client.post("/chat", headers=headers, json=body)
        assert r.status_code == expect, r.text
        return parse_sse(r.text) if expect == 200 else [("http_error", r.json())]

    def invoice_id(self, number: str) -> int:
        with self.factory() as s:
            return s.scalar(select(Invoice.id).where(Invoice.number == number))

    def counterparty_id(self, name: str) -> int:
        with self.factory() as s:
            return s.scalar(select(Counterparty.id).where(Counterparty.name == name))

    def events(self) -> list[str]:
        with self.factory() as s:
            return list(s.scalars(select(AuditEvent.event_type).order_by(AuditEvent.seq)))


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch) -> Iterator[ChatHarness]:
    from app.agent.runner import ConversationStore
    from app.api import routes_chat
    from app.api.deps import get_chat_model, get_classifier, get_session, get_session_factory
    from app.main import app

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as s:
        load(s, classifier=FakeClassifier())
        s.commit()

    def session_override() -> Iterator[Session]:
        with factory() as s:
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise

    harness = ChatHarness(TestClient(app), factory, ScriptedModel())
    monkeypatch.setattr(routes_chat, "conversations", ConversationStore())
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_chat_model] = lambda: harness.model
    app.dependency_overrides[get_classifier] = FakeClassifier
    yield harness
    app.dependency_overrides.clear()
