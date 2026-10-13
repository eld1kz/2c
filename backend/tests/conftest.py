import os
import socket
from collections.abc import Iterator

# Test-only signing key so app.main passes its startup JWT_SECRET check.
os.environ["JWT_SECRET"] = "test-only-jwt-secret-0123456789abcdef"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, Business
from app.engine.categorize import NullClassifier
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
