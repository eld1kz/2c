"""Phase 6c-2: "Can I afford it?" — the verdict comes from the engine; the agent only maps and phrases."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.agent.citations import validate
from app.config import get_settings
from app.db.models import Cadence, ForecastLineKind
from app.engine.afford import affordability
from app.engine.forecast import CERTAIN_BP, Line, build
from app.engine.snapshot import load_snapshot
from app.engine.whatif import OneOff, ScenarioError
from app.services import ledger
from app.services.llm_budget import LlmBudget
from app.services.scenarios import AddRecurringIn, OneOffIn, RaisePayrollIn, assess, payroll_raise
from tests.conftest import ChatHarness, Demo
from tests.fakes import ScriptedModel, tool_result
from tests.test_agent_tools import _call, _ctx

TODAY = date(2026, 10, 1)
BARISTA = {"type": "add_recurring", "amount_cents": -250_000, "cadence": "monthly", "start": "2026-11-01"}


def _forecast(*flows: tuple[int, int]):  # noqa: ANN202 - (day offset, cents) flows on top of $10,000 opening
    lines = [Line(TODAY, ForecastLineKind.opening, 1_000_000, CERTAIN_BP, ("account:1",))]
    lines += [Line(TODAY + timedelta(days=d), ForecastLineKind.baseline_in, c, CERTAIN_BP, ("transaction:1",)) for d, c in flows]
    return build(TODAY, "USD", 500_000, lines, {})


def _one_off(amount: int):  # noqa: ANN202
    return lambda day: [OneOff(amount, day)]


def test_yes_when_no_week_dips_below_the_cushion() -> None:
    a = affordability(_forecast(), _one_off(-400_000), TODAY)
    assert (a.verdict, a.earliest_safe_start, a.weeks_below_with_it) == ("yes", TODAY, ())


def test_not_yet_gives_the_first_safe_start() -> None:
    a = affordability(_forecast((28, 300_000)), _one_off(-600_000), TODAY)  # money comes in in week 5
    assert (a.verdict, a.earliest_safe_start) == ("not_yet", TODAY + timedelta(days=28))
    assert a.weeks_below_with_it == (1, 2, 3, 4)


def test_no_when_nothing_in_13_weeks_works() -> None:
    a = affordability(_forecast(), _one_off(-600_000), TODAY)
    assert (a.verdict, a.earliest_safe_start) == ("no", None)


def test_golden_barista_is_no_because_cash_is_already_short(demo: Demo) -> None:
    snap = load_snapshot(demo.session, demo.business.id, TODAY)
    a = assess(demo.session, snap, TODAY, AddRecurringIn(type="add_recurring", amount_cents=-250_000,
                                                          cadence=Cadence.monthly, start=date(2026, 11, 1)))
    assert a.verdict == "no" and a.base_weeks_below[0] == 6
    assert set(a.base_weeks_below) < set(a.weeks_below_with_it)  # it adds week 11


def test_a_raise_is_computed_by_the_engine(demo: Demo) -> None:
    snap = load_snapshot(demo.session, demo.business.id, TODAY)
    (payroll,) = [s for s in snap.series if s.category.value == "payroll"]
    (extra,) = payroll_raise(snap.series, 5, TODAY)
    assert (extra.amount, extra.cadence, extra.start) == (-(434_355 * 5 // 100), payroll.cadence, TODAY) == (-21_717, payroll.cadence, TODAY)
    with pytest.raises(ScenarioError):
        payroll_raise(tuple(s for s in snap.series if s.category.value != "payroll"), 5, TODAY)
    a = assess(demo.session, snap, TODAY, RaisePayrollIn(type="raise_payroll", percent=5, start=TODAY))
    assert a.verdict == "no"


def test_plans_outside_the_horizon_are_refused(demo: Demo) -> None:
    snap = load_snapshot(demo.session, demo.business.id, TODAY)
    with pytest.raises(ScenarioError):
        assess(demo.session, snap, TODAY, OneOffIn(type="one_off", amount_cents=-300_000, on=date(2027, 3, 1)))


def test_the_tool_never_counts_the_supplied_amount_as_evidence(demo: Demo) -> None:
    ctx = _ctx(demo)
    result, out = _call(ctx, "check_affordability", scenario=BARISTA)
    data = result["data"]
    assert data["verdict"] == "no" and data["earliest_safe_start"] is None
    assert data["already_below_cushion_without_it"]["ref"] == "forecast_week:6"
    assert out.scenarios == [BARISTA]
    exists = lambda ref: ledger.record_exists(demo.session, demo.business.id, ref)  # noqa: E731
    supplied = validate("No: a barista at $2,500.00 a month does not fit [[whatif:1]].", ctx.memory.index, exists)
    assert any(p.kind == "unsupported_figure" for p in supplied.problems)
    cushion = data["already_below_cushion_without_it"]["cushion_display"]
    ok = validate(f"No: your cash already falls below your {cushion} cushion in Week 6 [[forecast_week:6]].",
                  ctx.memory.index, exists)
    assert ok.ok, ok.warnings


# --- API ----------------------------------------------------------------------------------


def _answer(opening: str):  # noqa: ANN202
    def reply(messages: list[dict]) -> list:
        week = tool_result(messages, "check_affordability")["data"]["already_below_cushion_without_it"]
        return [f"{opening} your cash already falls below your {week['cushion_display']} cushion in "
                f"{week['label']} [[{week['ref']}]], before any new cost."]
    return reply


def test_a_cited_answer_with_the_engine_verdict(chat: ChatHarness) -> None:
    chat.model = ScriptedModel([("check_affordability", {"scenario": BARISTA})], _answer("No:"))
    r = chat.client.post("/afford", headers=chat.login("owner"),
                         json={"question": "Hire a barista at $2,500/month from November?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["verdict"], body["earliest_safe_start"], body["warnings"]) == ("no", None, [])
    assert body["message"].startswith("No:") and all(c["valid"] for c in body["citations"])
    assert body["scenarios"] == [BARISTA]
    assert all(req["tools"] == ["check_affordability"] for req in chat.model.requests)
    assert "Hire a barista at $2,500/month from November?" in chat.model.sent


def test_the_badge_keeps_the_engine_verdict_when_the_text_disagrees(chat: ChatHarness) -> None:
    chat.model = ScriptedModel([("check_affordability", {"scenario": BARISTA})], _answer("Yes, go ahead:"))
    body = chat.client.post("/afford", headers=chat.login("owner"), json={"question": "Can I hire a barista?"}).json()
    assert body["verdict"] == "no"
    assert any("doesn't open with the verdict" in w for w in body["warnings"])


def test_an_uncited_answer_is_flagged(chat: ChatHarness) -> None:
    chat.model = ScriptedModel([("check_affordability", {"scenario": BARISTA})], ["No, you are $7,271.99 short."],
                               ["No, you are $7,271.99 short."])
    body = chat.client.post("/afford", headers=chat.login("owner"), json={"question": "Can I hire a barista?"}).json()
    assert body["verdict"] == "no" and body["warnings"]


def test_no_plan_no_verdict(chat: ChatHarness) -> None:
    chat.model = ScriptedModel(["I can only check new costs."])
    body = chat.client.post("/afford", headers=chat.login("accountant"), json={"question": "What is the weather?"}).json()
    assert body["verdict"] is None and body["scenarios"] == [] and body["warnings"]


def test_viewer_cannot_ask_and_the_model_is_not_called(chat: ChatHarness) -> None:
    r = chat.client.post("/afford", headers=chat.login("viewer"), json={"question": "Can I hire a barista?"})
    assert r.status_code == 403 and chat.model.requests == []
    assert chat.events()[-1] == "simulation_forbidden"


def test_afford_respects_the_daily_ai_budget(chat: ChatHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "daily_llm_budget_usd", Decimal("0.05"))
    with chat.factory() as s:
        LlmBudget(s, 0, lambda: datetime.now(timezone.utc)).record("agent", "claude-sonnet-5-5", 25_000, 0)
        s.commit()
    r = chat.client.post("/afford", headers=chat.login("owner"), json={"question": "Can I hire a barista?"})
    assert r.status_code == 503 and "budget" in r.json()["detail"]
    assert chat.model.requests == []


def test_the_chart_accepts_a_raise(chat: ChatHarness) -> None:
    r = chat.client.post("/whatif", headers=chat.login("owner"),
                         json={"scenarios": [{"type": "raise_payroll", "percent": 5, "start": "2026-10-01"}]})
    assert r.status_code == 200, r.text
    assert r.json()["assumptions"][0]["amount_cents"] == -21_717
    bad = chat.client.post("/whatif", headers=chat.login("owner"),
                           json={"scenarios": [{"type": "raise_payroll", "percent": 80, "start": "2026-10-01"}]})
    assert bad.status_code == 422
