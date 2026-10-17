"""Read API for the web UI (Phase 5): /me, /position, /forecast, /insights, /llm-budget."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Business, Counterparty, CounterpartyKind, Role, User
from app.services import ledger
from seed.load import DEMO_PASSWORD
from tests.test_api import _login, client, db  # noqa: F401 - fixtures
from tests.test_forecast import expected_closings

READ_ROUTES = ["/me", "/position", "/forecast", "/forecast/weeks/6", "/insights", "/llm-budget"]


@pytest.mark.parametrize("path", READ_ROUTES)
def test_read_routes_need_a_signed_in_user(client: TestClient, path: str) -> None:  # noqa: F811
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("role", ["owner", "accountant", "viewer"])
def test_every_role_can_read(client: TestClient, role: str) -> None:  # noqa: F811
    headers = _login(client, role)
    for path in READ_ROUTES:
        assert client.get(path, headers=headers).status_code == 200, path
    assert client.get("/me", headers=headers).json()["user"]["role"] == role


def test_position_is_cash_at_demo_today(client: TestClient) -> None:  # noqa: F811
    pos = client.get("/position", headers=_login(client, "viewer")).json()
    assert pos["as_of"] == "2026-10-01"
    assert pos["cash_cents"] == 865_000
    assert pos["min_cash_buffer_cents"] == 500_000
    assert pos["headroom_cents"] == 365_000
    assert pos["evidence"] and all(e["ref"].startswith("account:") and e["label"] for e in pos["evidence"])


def test_forecast_shows_both_dips_below_the_buffer(client: TestClient) -> None:  # noqa: F811
    fc = client.get("/forecast", headers=_login(client, "viewer")).json()
    weeks = {w["week"]: w for w in fc["weeks"]}
    closings = expected_closings("llm")  # the API fixture loads with the mocked LLM classifier
    assert [w["closing_cents"] for w in fc["weeks"]] == closings
    assert weeks[6]["below_buffer"] and weeks[9]["below_buffer"]
    assert fc["lowest"] == {"week": 9, "closing_cents": closings[8]}
    assert {6, 9} <= set(fc["gap"]["weeks_below"])
    assert fc["gap"]["low_week"] == 9
    assert fc["gap"]["amount_cents"] == 500_000 - closings[8]


def test_week_lines_add_up_and_cite_records(client: TestClient) -> None:  # noqa: F811
    out = client.get("/forecast/weeks/6", headers=_login(client, "viewer")).json()
    week = out["week"]
    assert sum(ln["amount_cents"] for ln in out["lines"]) == week["closing_cents"] - week["opening_cents"]
    assert any(ln["face_cents"] == -1_200_000 for ln in out["lines"])  # the quarterly lease
    assert all(ln["sources"] and all(s["label"] for s in ln["sources"]) for ln in out["lines"])


@pytest.mark.parametrize("week", [0, 14])
def test_week_out_of_horizon_is_rejected(client: TestClient, week: int) -> None:  # noqa: F811
    assert client.get(f"/forecast/weeks/{week}", headers=_login(client, "viewer")).status_code == 422


def test_insights_carry_impact_and_labelled_evidence(client: TestClient) -> None:  # noqa: F811
    rows = client.get("/insights", headers=_login(client, "viewer")).json()
    types = {r["type"] for r in rows}
    assert {"LATE_PAYER", "DUPLICATE_SUBSCRIPTION", "PRICE_CREEP", "CASH_GAP"} <= types
    assert all(r["impact_cents"] > 0 and r["evidence"] for r in rows)
    late = next(r for r in rows if r["type"] == "LATE_PAYER" and r["severity"] == "high")
    assert "INV-1042" in {e["label"] for e in late["evidence"]}
    impacts = [r["impact_cents"] for r in rows]
    assert impacts == sorted(impacts, reverse=True)


def test_llm_budget_is_untouched_on_a_fresh_day(client: TestClient) -> None:  # noqa: F811
    b = client.get("/llm-budget", headers=_login(client, "viewer")).json()
    assert b["spent_microusd"] == 0
    assert b["remaining_microusd"] == b["limit_microusd"] == 2_000_000
    assert b["remaining_display"] == "$2.0000" and not b["exhausted"]


def test_labels_never_resolve_another_business_records(client: TestClient, db) -> None:  # noqa: F811, ANN001
    with db() as s:
        other = Business(name="Other Co", base_currency="USD", industry="x", min_cash_buffer=0, settings={})
        s.add(other)
        s.flush()
        s.add(User(business_id=other.id, email="owner@other.example", name="O", role=Role.owner,
                   password_hash=s.scalar(select(User.password_hash))))
        s.add(Counterparty(business_id=other.id, name="Secret Supplier", normalized_name="SECRET SUPPLIER",
                           kind=CounterpartyKind.supplier, is_allowed_payee=False, stats={}))
        s.commit()
    token = client.post("/auth/login", json={"email": "owner@other.example", "password": DEMO_PASSWORD}).json()
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    assert client.get("/insights", headers=headers).json() == []
    assert client.get("/me", headers=headers).json()["business"]["name"] == "Other Co"
    with db() as s:
        secret = s.scalar(select(Counterparty).where(Counterparty.name == "Secret Supplier"))
        mine = s.scalar(select(Counterparty).where(Counterparty.business_id == 1))
        refs = [f"counterparty:{secret.id}", f"counterparty:{mine.id}", "invoice:abc", "nope:1"]
        assert ledger.labels(s, 1, refs) == {f"counterparty:{mine.id}": mine.name}
