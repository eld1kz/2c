import os
import socket
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Test-only signing key so app.main passes its startup JWT_SECRET check.
os.environ["JWT_SECRET"] = "test-only-jwt-secret-0123456789abcdef"

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import DEFAULT_DEMO_TODAY
from app.db.models import Base, Business, Counterparty, Invoice, User
from app.engine.categorize import NullClassifier
from app.policy.gate import Actor
from app.services.action_service import ActionService, actor_for
from seed.load import load
from tests.fakes import FakeClassifier


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may reach the network (LLM calls must be mocked)."""

    def blocked(*args: object, **kwargs: object) -> None:
        raise RuntimeError("network access is disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


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
