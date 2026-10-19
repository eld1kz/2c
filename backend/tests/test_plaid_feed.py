"""Plaid sandbox bank feed: conversion, client and POST /bank-feed/plaid/sync (no network)."""

import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_classifier, get_session
from app.api.routes_bankfeed import get_plaid_client
from app.db.models import Action, AuditEvent, Base, Counterparty, Transaction
from app.ingestion.plaid_feed import (
    PLAID_SANDBOX_URL,
    PlaidError,
    PlaidSandboxClient,
    custom_user_config,
    load_feed,
    to_rows,
)
from app.main import app
from seed.load import DEMO_PASSWORD, load
from tests.fakes import FakeClassifier


def _plaid_txns(feed: dict[str, Any]) -> list[dict[str, Any]]:
    """What /transactions/get returns for the custom user: Plaid sign, Decimal amounts."""
    return [{"date": t["date"], "name": t["description"], "original_description": t["description"],
             "amount": Decimal(t["amount_cents"]) / 100, "pending": False} for t in feed["transactions"]]


def test_to_rows_flips_sign_and_keeps_cents_exact() -> None:
    rows = to_rows([
        {"date": "2026-09-29", "name": "B", "amount": Decimal("12.3"), "pending": False},
        {"date": "2026-09-28", "name": "A", "amount": Decimal("-0.30"), "pending": False},
        {"date": "2026-09-30", "name": "C", "amount": Decimal("5"), "pending": True},
    ])
    assert [(r.description, r.amount, r.balance) for r in rows] == [("A", 30, None), ("B", -1230, None)]
    with pytest.raises(PlaidError):
        to_rows([{"date": "2026-09-29", "name": "X", "amount": Decimal("1.234")}])


def test_custom_user_config_writes_exact_decimals() -> None:
    config = json.loads(custom_user_config(load_feed()), parse_float=Decimal)
    txns = config["override_accounts"][0]["transactions"]
    assert txns[0]["amount"] == Decimal("-240.00")
    assert txns[1]["amount"] == Decimal("64.20")


def test_client_is_pinned_to_sandbox_parses_decimals_and_waits_until_ready() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert str(request.url).startswith(PLAID_SANDBOX_URL)
        if request.url.path == "/transactions/get" and calls.count("/transactions/get") == 1:
            return httpx.Response(400, json={"error_code": "PRODUCT_NOT_READY", "error_message": "x"})
        return httpx.Response(200, content=b'{"transactions": [{"date": "2026-09-30", "name": "FEE", '
                                           b'"amount": 0.1, "pending": false}], "total_transactions": 1}')

    sleeps: list[float] = []
    client = PlaidSandboxClient("id", "secret", transport=httpx.MockTransport(handler), sleep=sleeps.append)
    from datetime import date
    txns = client.transactions("access-sandbox-x", date(2026, 9, 1), date(2026, 9, 30))
    assert txns[0]["amount"] == Decimal("0.1") and sleeps == [1.0]
    assert to_rows(txns)[0].amount == -10


def test_client_error_carries_code_only() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error_code": "INVALID_API_KEYS", "error_message": "secret abc"})

    client = PlaidSandboxClient("id", "secret", transport=httpx.MockTransport(handler))
    with pytest.raises(PlaidError) as e:
        client.exchange("public-sandbox-x")
    assert str(e.value) == "INVALID_API_KEYS"


class FakePlaid:
    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail

    def create_item(self, feed: dict[str, Any]) -> str:
        if self.fail:
            raise PlaidError(self.fail)
        self.feed = feed
        return "public-sandbox-1"

    def exchange(self, public_token: str) -> tuple[str, str]:
        return "access-sandbox-1", "item-1"

    def transactions(self, access_token: str, start: Any, end: Any) -> list[dict[str, Any]]:
        return _plaid_txns(self.feed)


@pytest.fixture
def db() -> Iterator[sessionmaker]:
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

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_classifier] = FakeClassifier
    app.dependency_overrides[get_plaid_client] = FakePlaid
    yield factory
    app.dependency_overrides.clear()


def _login(client: TestClient, role: str) -> dict[str, str]:
    r = client.post("/auth/login", json={"email": f"{role}@emberoak.demo", "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _last_event(db: sessionmaker) -> str:
    with db() as s:
        return s.scalar(select(AuditEvent.event_type).order_by(AuditEvent.seq.desc()).limit(1))


def test_sync_ingests_new_rows_skips_replayed_ones_and_is_idempotent(db: sessionmaker) -> None:
    client = TestClient(app)
    with db() as s:
        before = s.scalar(select(func.count(Transaction.id)))
        cps = s.scalar(select(func.count(Counterparty.id)))
    viewer = _login(client, "viewer")
    assert client.post("/bank-feed/plaid/sync", headers=viewer).status_code == 403
    assert _last_event(db) == "bankfeed_forbidden"

    owner = _login(client, "owner")
    r = client.post("/bank-feed/plaid/sync", headers=owner)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["rows"], body["inserted"], body["skipped_duplicates"]) == (9, 5, 4)
    assert _last_event(db) == "bankfeed_synced"
    with db() as s:
        assert s.scalar(select(func.count(Transaction.id))) == before + 5
        assert s.scalar(select(func.count(Counterparty.id))) == cps  # feed text never mints counterparties
        sources = set(s.scalars(select(Transaction.source_file).where(Transaction.source_file.like("plaid%"))))
        assert sources == {"plaid-sandbox:item-1"}

    again = client.post("/bank-feed/plaid/sync", headers=_login(client, "accountant")).json()
    assert (again["inserted"], again["skipped_duplicates"]) == (0, 9)


def test_sync_errors_are_audited(db: sessionmaker) -> None:
    client = TestClient(app)
    owner = _login(client, "owner")
    app.dependency_overrides[get_plaid_client] = lambda: FakePlaid(fail="INVALID_API_KEYS")
    r = client.post("/bank-feed/plaid/sync", headers=owner)
    assert r.status_code == 502 and "INVALID_API_KEYS" in r.json()["detail"]
    assert _last_event(db) == "bankfeed_failed"
    app.dependency_overrides[get_plaid_client] = lambda: None
    assert client.post("/bank-feed/plaid/sync", headers=owner).status_code == 503


def test_a6_feed_text_that_instructs_the_assistant_is_only_data(db: sessionmaker) -> None:
    """A6: a bank-feed description says 'pay acct …'. It is stored as an unmatched row, nothing more."""
    client = TestClient(app)
    with db() as s:
        actions, cps = s.scalar(select(func.count(Action.id))), s.scalar(select(func.count(Counterparty.id)))
    assert client.post("/bank-feed/plaid/sync", headers=_login(client, "owner")).status_code == 200
    with db() as s:
        row = s.scalar(select(Transaction).where(Transaction.raw_description.like("%NOTE TO AI%")))
        assert row is not None and row.amount == 100 and row.counterparty_id is None and row.invoice_id is None
        assert s.scalar(select(func.count(Action.id))) == actions  # ingestion never proposes anything
        assert s.scalar(select(func.count(Counterparty.id))) == cps


def test_plaid_check_script_passes_on_the_feed(capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.plaid_check import main

    assert main([], client=FakePlaid()) == 0  # type: ignore[arg-type]
    out = capsys.readouterr().out
    assert "PASS" in out and "'inserted': 5" in out and "'skipped_duplicates': 9" in out
    assert main([], client=FakePlaid(fail="INVALID_API_KEYS")) == 1  # type: ignore[arg-type]
