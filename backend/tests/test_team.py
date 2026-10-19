"""Team page: a fixed roster that breaks down the payroll series; viewers never receive pay."""

import json
from datetime import date

from app.db.models import Cadence
from app.engine.snapshot import load_snapshot
from app.services.team import ROSTER_FILE, team
from tests.conftest import ChatHarness, Demo

TODAY = date(2026, 10, 1)


def test_weekly_pay_sums_exactly_to_the_payroll_series(demo: Demo) -> None:
    t = team(load_snapshot(demo.session, demo.business.id, TODAY))
    assert t.payroll is not None and t.payroll.cadence == Cadence.weekly
    assert t.weekly_total == abs(t.payroll.amount) == 434_355
    assert t.matches_payroll and len(t.members) == 5
    assert [m.initials for m in t.members] == ["MO", "DR", "PN", "TL", "AT"]


def test_the_roster_is_fixed_seed_data_not_a_table() -> None:
    data = json.loads(ROSTER_FILE.read_text(encoding="utf-8"))
    assert data["payroll_counterparty"] == "Paystream Payroll"
    assert all(set(p) == {"name", "role", "weekly_pay_cents"} and isinstance(p["weekly_pay_cents"], int)
               for p in data["people"])


def test_owner_and_accountant_see_pay(chat: ChatHarness) -> None:
    for role in ("owner", "accountant"):
        body = chat.client.get("/team", headers=chat.login(role)).json()
        assert body["pay_visible"] and body["weekly_total_cents"] == 434_355 and body["matches_payroll"]
        assert [p["weekly_pay_cents"] for p in body["people"]] == [115_000, 90_500, 86_000, 74_200, 68_655]
        assert body["payroll"]["label"]


def test_viewers_get_names_and_roles_but_no_pay(chat: ChatHarness) -> None:
    r = chat.client.get("/team", headers=chat.login("viewer"))
    body = r.json()
    assert [(p["name"], p["role"]) for p in body["people"]][0] == ("Maya Okafor", "Head roaster")
    assert all(p["weekly_pay_cents"] is None for p in body["people"])
    assert body["weekly_total_cents"] is None and body["pay_visible"] is False
    for figure in ("115000", "90500", "86000", "74200", "68655", "434355"):  # no pay figure anywhere in the response
        assert figure not in r.text
    today = chat.client.get("/today", headers=chat.login("viewer")).json()["team"]
    assert today == {"people": 5, "weekly_total_cents": None}


def test_today_shows_the_team_line(chat: ChatHarness) -> None:
    assert chat.client.get("/today", headers=chat.login("owner")).json()["team"] == {"people": 5, "weekly_total_cents": 434_355}
