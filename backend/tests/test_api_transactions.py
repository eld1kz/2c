"""Transactions API (Phase 5): ledger table, review queue, and human recategorization.

Recategorizing is owner/accountant only, audited, and may change only the transaction's
categorization and add a rule: never counterparties, invoices or anything the payment gate reads.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Action,
    AuditEvent,
    Business,
    CategoryRule,
    CategorySource,
    Counterparty,
    Invoice,
    InvoiceLine,
    Policy,
    Role,
    RuleSource,
    SandboxEmail,
    SandboxLoanApplication,
    SandboxPayment,
    Transaction,
    User,
)
from app.policy.limits import invoice_outstanding
from seed.load import DEMO_PASSWORD
from tests.test_api import _login, client, db  # noqa: F401 - fixtures

CATEGORIZATION = {"category", "category_source", "needs_review", "confidence"}
GATE_INPUTS = (Counterparty, Invoice, InvoiceLine, Policy, Action, SandboxPayment, SandboxEmail, SandboxLoanApplication)


def _dump(rows: list[Any], skip: set[str] = frozenset()) -> list[dict[str, Any]]:
    return [{c.key: getattr(r, c.key) for c in inspect(r).mapper.column_attrs if c.key not in skip} for r in rows]


def _gate_state(db: sessionmaker) -> dict[str, Any]:
    with db() as s:
        state = {m.__name__: _dump(list(s.scalars(select(m).order_by(*inspect(m).primary_key)))) for m in GATE_INPUTS}
        state["Transaction"] = _dump(list(s.scalars(select(Transaction).order_by(Transaction.id))), CATEGORIZATION)
        state["outstanding"] = {i.number: invoice_outstanding(s, i) for i in s.scalars(select(Invoice))}
    return state


def _linked_transaction(db: sessionmaker) -> Transaction:
    """A customer payment that settles an invoice: the riskiest row to recategorize."""
    with db() as s:
        return s.scalar(select(Transaction).where(Transaction.invoice_id.is_not(None), Transaction.counterparty_id.is_not(None))
                        .order_by(Transaction.id))


def _a1_payment(client: TestClient, db: sessionmaker, key: str) -> str:  # noqa: F811
    with db() as s:
        qs = s.scalar(select(Counterparty.id).where(Counterparty.name == "QuickShip Logistics"))
        inv = s.scalar(select(Invoice.id).where(Invoice.number == "QS-2291"))
    r = client.post("/actions", headers=_login(client, "owner"), json={
        "tool": "schedule_payment", "idempotency_key": key,
        "params": {"payee_counterparty_id": qs, "invoice_id": inv, "amount": 465_000, "date": "2026-10-08"}})
    return r.json()["status"]


def test_list_and_page_transactions(client: TestClient) -> None:  # noqa: F811
    assert client.get("/transactions").status_code == 401
    headers = _login(client, "viewer")
    first = client.get("/transactions", headers=headers).json()
    assert len(first["rows"]) == 50 and first["has_more"]
    row = first["rows"][0]
    assert set(row["description"]) == {"untrusted_text", "source"}
    second = client.get("/transactions", params={"offset": 50}, headers=headers).json()
    assert {r["id"] for r in first["rows"]}.isdisjoint({r["id"] for r in second["rows"]})


def test_review_queue_lists_only_flagged_rows(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    t = _linked_transaction(db)
    with db() as s:
        s.get(Transaction, t.id).needs_review = True
        s.commit()
    queue = client.get("/transactions", params={"needs_review": True}, headers=_login(client, "viewer")).json()
    assert [r["id"] for r in queue["rows"]] == [t.id] and not queue["has_more"]


def test_recategorize_changes_only_categorization_and_a_rule(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    t = _linked_transaction(db)
    assert _a1_payment(client, db, "a1-before") == "denied"
    before = _gate_state(db)
    with db() as s:
        rules_before = s.query(CategoryRule).count()

    r = client.post(f"/transactions/{t.id}/category", json={"category": "other"}, headers=_login(client, "accountant"))
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "other" and r.json()["category_source"] == "human" and not r.json()["needs_review"]

    after = _gate_state(db)
    assert after == before, "recategorize changed something the payment gate reads"
    with db() as s:
        row = s.get(Transaction, t.id)
        assert (row.category.value, row.category_source, row.needs_review) == ("other", CategorySource.human, False)
        assert s.query(CategoryRule).count() == rules_before + 1
        rule = s.scalar(select(CategoryRule).where(CategoryRule.source == RuleSource.human))
        cp = s.get(Counterparty, t.counterparty_id)
        assert (rule.kind.value, rule.pattern, rule.category.value) == ("name", cp.normalized_name, "other")
        event = s.scalar(select(AuditEvent).where(AuditEvent.event_type == "transaction_recategorized"))
        assert event.payload["transaction_id"] == t.id and event.payload["to"] == "other"
    assert _a1_payment(client, db, "a1-after") == "denied"  # the gate still refuses the injected payment


def test_recategorizing_twice_reuses_the_rule(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    t = _linked_transaction(db)
    headers = _login(client, "owner")
    for category in ("other", "revenue_retail"):
        assert client.post(f"/transactions/{t.id}/category", json={"category": category}, headers=headers).status_code == 200
    with db() as s:
        rules = list(s.scalars(select(CategoryRule).where(CategoryRule.source == RuleSource.human)))
    assert [r.category.value for r in rules] == ["revenue_retail"]


def test_viewer_cannot_recategorize_and_the_attempt_is_audited(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    t = _linked_transaction(db)
    before = _gate_state(db)
    r = client.post(f"/transactions/{t.id}/category", json={"category": "other"}, headers=_login(client, "viewer"))
    assert r.status_code == 403
    assert _gate_state(db) == before
    with db() as s:
        assert s.get(Transaction, t.id).category_source != CategorySource.human
        assert s.scalar(select(AuditEvent.event_type).order_by(AuditEvent.seq.desc())) == "recategorize_forbidden"


@pytest.mark.parametrize("body", [{"category": "bribes"}, {"category": "other", "counterparty_id": 1}, {}])
def test_invalid_bodies_are_rejected(client: TestClient, db: sessionmaker, body: dict) -> None:  # noqa: F811
    t = _linked_transaction(db)
    r = client.post(f"/transactions/{t.id}/category", json=body, headers=_login(client, "owner"))
    assert r.status_code == 422


def test_another_business_transaction_is_not_found(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    t = _linked_transaction(db)
    with db() as s:
        other = Business(name="Other Co", base_currency="USD", industry="x", min_cash_buffer=0, settings={})
        s.add(other)
        s.flush()
        s.add(User(business_id=other.id, email="owner@other.example", name="O", role=Role.owner,
                   password_hash=s.scalar(select(User.password_hash))))
        s.commit()
    token = client.post("/auth/login", json={"email": "owner@other.example", "password": DEMO_PASSWORD}).json()
    r = client.post(f"/transactions/{t.id}/category", json={"category": "other"},
                    headers={"Authorization": f"Bearer {token['access_token']}"})
    assert r.status_code == 404
    with db() as s:
        assert s.get(Transaction, t.id).category_source != CategorySource.human
