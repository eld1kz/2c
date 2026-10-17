"""What-if API (Phase 6): POST /whatif before/after forecast, scenario inputs shown as assumptions."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Action, AuditEvent, ForecastRun, Invoice, SandboxEmail
from tests.test_api import _events, _login, client, db  # noqa: F401 - fixtures
from tests.test_forecast import expected_closings


def _invoice_id(db: sessionmaker, number: str) -> int:  # noqa: F811
    with db() as s:
        return s.scalar(select(Invoice.id).where(Invoice.number == number))


def _collect(invoice_id: int) -> dict:
    return {"scenarios": [{"type": "collect_receivable", "invoice_id": invoice_id}]}


def test_forecast_offers_the_at_risk_receivable(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    fc = client.get("/forecast", headers=_login(client, "viewer")).json()
    inv = _invoice_id(db, "INV-1042")
    assert fc["at_risk_receivables"] == [{
        "invoice": {"ref": f"invoice:{inv}", "label": "INV-1042"}, "number": "INV-1042",
        "counterparty_name": "Harbor Lane Café", "outstanding_cents": 480_000}]


def test_collecting_inv_1042_changes_week_6_and_leaves_a_smaller_gap(client: TestClient,  # noqa: F811
                                                                     db: sessionmaker) -> None:  # noqa: F811
    inv = _invoice_id(db, "INV-1042")
    out = client.post("/whatif", json=_collect(inv), headers=_login(client, "owner"))
    assert out.status_code == 200, out.text
    body = out.json()
    weeks = {w["week"]: w for w in body["weeks"]}
    assert [w["base_closing_cents"] for w in body["weeks"]] == expected_closings("llm")
    assert all(w["change_cents"] == 480_000 for w in body["weeks"])  # collected now, in full
    assert weeks[6]["base_closing_cents"] < 0 < weeks[6]["scenario_closing_cents"] < 500_000
    assert weeks[6]["scenario_below_buffer"]
    assert body["base_gap"]["amount_cents"] == 727_199
    assert body["scenario_gap"] == {**body["scenario_gap"], "first_week": 6, "low_week": 9, "amount_cents": 247_199}
    assert body["assumptions"] == [{
        "type": "collect_receivable", "invoice": {"ref": f"invoice:{inv}", "label": "INV-1042"}, "series": None,
        "counterparty_name": "Harbor Lane Café", "on": "2026-10-01", "days": None, "cadence": None,
        "amount_cents": 480_000, "amount_source": "records"}]


def test_typed_in_amounts_are_marked_supplied(client: TestClient) -> None:  # noqa: F811
    body = {"scenarios": [{"type": "one_off", "amount_cents": -250_000, "on": "2026-10-20"}]}
    out = client.post("/whatif", json=body, headers=_login(client, "accountant")).json()
    first = out["assumptions"][0]
    assert (first["type"], first["amount_cents"], first["amount_source"]) == ("one_off", -250_000, "supplied")
    assert out["weeks"][2]["change_cents"] == -250_000


@pytest.mark.parametrize("scenario", [
    {"type": "one_off", "amount_cents": -100_000_001, "on": "2026-10-20"},  # over $1,000,000
    {"type": "one_off", "amount_cents": -1_000, "on": "2027-06-01"},  # outside the horizon
    {"type": "collect_receivable", "invoice_id": 99_999},  # not a record
    {"type": "remove_series", "series_id": 99_999},
    {"type": "one_off", "amount_cents": -1_000, "on": "2026-10-20", "payee": "ACME"},  # unknown field
])
def test_bad_scenarios_are_refused(client: TestClient, scenario: dict) -> None:  # noqa: F811
    r = client.post("/whatif", json={"scenarios": [scenario]}, headers=_login(client, "owner"))
    assert r.status_code == 422
    assert "ACME" not in r.text


def test_a_paid_invoice_cannot_be_collected_again(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    with db() as s:
        paid = s.scalar(select(Invoice.id).where(Invoice.status == "paid").limit(1))
    r = client.post("/whatif", json=_collect(paid), headers=_login(client, "owner"))
    assert r.status_code == 422
    assert "not an open receivable" in r.json()["detail"]


def test_viewer_cannot_simulate_and_is_audited(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    r = client.post("/whatif", json=_collect(_invoice_id(db, "INV-1042")), headers=_login(client, "viewer"))
    assert r.status_code == 403
    assert _events(db)[-1] == "simulation_forbidden"


def test_simulation_writes_nothing(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    headers = _login(client, "owner")

    def counts() -> tuple[int, ...]:
        with db() as s:
            return tuple(s.scalar(select(func.count()).select_from(m)) for m in (Action, ForecastRun, SandboxEmail,
                                                                                  AuditEvent))

    before = counts()
    assert client.post("/whatif", json=_collect(_invoice_id(db, "INV-1042")), headers=headers).status_code == 200
    assert counts() == before


def test_needs_a_signed_in_user(client: TestClient) -> None:  # noqa: F811
    assert client.post("/whatif", json={"scenarios": []}).status_code == 401
