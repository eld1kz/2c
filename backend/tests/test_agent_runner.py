"""Agent runner end to end over HTTP with a scripted model: the P4 demo, loop limits, errors, citations."""

from sqlalchemy import select

from app.agent.citations import UNVERIFIED_NOTICE
from app.agent.prompts import render_system
from app.agent.runner import MAX_ITERATIONS, ModelUnavailable
from app.config import DEFAULT_DEMO_TODAY
from app.db.models import Action, Business, RecurringSeries, Role, SandboxEmail
from tests.conftest import ChatHarness
from tests.fakes import ScriptedModel, tool_result

QUESTION = "Why will I be short on cash?"


def _series_id(chat: ChatHarness, counterparty: str) -> int:
    with chat.factory() as s:
        return s.scalar(select(RecurringSeries.id).where(
            RecurringSeries.counterparty_id == chat.counterparty_id(counterparty)))


def _done(events: list[tuple[str, dict]]) -> dict:
    (done,) = [data for name, data in events if name == "done"]
    return done


def test_p4_walkthrough(chat: ChatHarness) -> None:
    inv = chat.invoice_id("INV-1042")
    verde = chat.counterparty_id("Verde Green Coffee Imports")
    lease, payroll = _series_id(chat, "Crestline Equipment Finance"), _series_id(chat, "Paystream Payroll")
    collect = [{"type": "collect_receivable", "invoice_id": inv}]
    insights: dict[str, str] = {}  # insight refs, read from tool results as the script runs

    def send(messages: list[dict]) -> list:
        draft = tool_result(messages, "draft_reminder")["data"]["draft_id"]
        insights["late"] = tool_result(messages, "get_insights")["data"]["insights"][0]["ref"]
        return [("send_reminder", {"invoice_id": inv, "draft_id": draft,
                                   "rationale": "INV-1042 is 45 days overdue; collecting it shrinks the cash gap.",
                                   "evidence_ids": [f"invoice:{inv}", insights["late"], "whatif:1", "made:up"]})]

    def answer(messages: list[dict]) -> list:
        proposed = tool_result(messages, "send_reminder")["data"]["ref"]
        terms = tool_result(messages, "draft_terms_request")["data"]["ref"]
        return [
            f"Cash drops below your $5,000.00 buffer in week 6, closing at −$2,087.67 [[forecast_week:6]], and bottoms "
            f"out at −$2,271.99 in week 9 [[forecast_week:9]] [[{insights['gap']}]]. The main drivers are the "
            f"quarterly equipment lease of $12,000.00 [[recurring_series:{lease}]] and weekly payroll of $4,343.55 "
            f"[[recurring_series:{payroll}]] landing in that week, while Harbor Lane Café's INV-1042 for $4,800.00 is "
            f"45 days overdue and counted as at risk [[invoice:{inv}]] [[{insights['late']}]].\n"
            f"If INV-1042 is collected now, week 9 still closes at $2,528.01, leaving a $2,471.99 shortfall "
            f"[[whatif:1]]. The cheapest fix is asking Verde Green Coffee Imports for 30 more days on payment terms: "
            f"it costs $0.00 and covers that gap on its own [[financing:supplier_terms_extension]] "
            f"[[counterparty:{verde}]]. An overdraft would cost $42.66 [[financing:overdraft]].\n"
            f"I've prepared: (1) a firm reminder to Harbor Lane for INV-1042, awaiting your approval [[{proposed}]]; "
            f"(2) a terms-request draft for Verde, a draft only and not sent [[{terms}]]. Not financial advice."]

    def explain(messages: list[dict]) -> list:
        insights["gap"] = tool_result(messages, "get_insights")["data"]["insights"][0]["ref"]
        return [("get_insights", {"type": "LATE_PAYER"}), ("explain_record", {"ref": f"invoice:{inv}"})]

    chat.model = ScriptedModel(
        [("get_forecast", {}), ("get_insights", {"type": "CASH_GAP"})],
        explain,
        [("run_what_if", {"scenarios": collect})],
        [("rank_financing", {"scenarios": collect})],
        [("draft_reminder", {"invoice_id": inv, "tone": "firm"}),
         ("draft_terms_request", {"counterparty_id": verde, "extension_days": 30})],
        send,
        answer,
    )
    owner = chat.login("owner")
    events = chat.chat(owner, QUESTION)
    done = _done(events)

    assert done["warnings"] == [] and all(c["valid"] for c in done["citations"]), done
    assert done["iterations"] == 7 and UNVERIFIED_NOTICE not in done["message"]
    labels = {c["ref"]: c["label"] for c in done["citations"]}
    assert labels["forecast_week:6"] == "Week 6 (Nov 5)" and labels["whatif:1"] == "What-if 1"
    assert [name for name, _ in events if name == "tool"] == ["tool"] * 9
    (action_event,) = [data for name, data in events if name == "action"]
    assert action_event["tool"] == "send_reminder" and action_event["status"] == "proposed"

    # What the engine returned, as the model saw it.
    msgs = chat.model.requests[-1]["messages"]
    forecast = tool_result(msgs, "get_forecast")["data"]
    assert [forecast["weeks"][k]["closing_cents"] for k in (5, 8)] == [-208_767, -227_199]
    whatif = tool_result(msgs, "run_what_if")["data"]
    assert whatif["scenario_gap"]["amount_cents"] == 247_199 and whatif["weeks"][8]["scenario_closing_display"] == "$2,528.01"
    options = tool_result(msgs, "rank_financing")["data"]["options"]
    assert [o["option_id"] for o in options[:2]] == ["supplier_terms_extension", "overdraft"]
    assert options[0]["by_counterparty"][0]["counterparty_name"] == "Verde Green Coffee Imports"
    assert options[0]["by_counterparty"][0]["covers_gap_alone"] is True
    assert "financing:overdraft" in tool_result(msgs, "rank_financing")["data"]["gap"]["evidence_ids"]

    # The approvals queue holds exactly the reminder; the drafts are stored but not approvable.
    pending = chat.client.get("/actions", params={"status": "proposed"}, headers=owner).json()
    assert len(pending) == 1
    (reminder,) = pending
    assert (reminder["tool"], reminder["tier"], reminder["proposed_by"]) == ("send_reminder", "EXECUTE", "agent")
    assert reminder["params"]["invoice_id"] == inv and "made:up" not in reminder["evidence_ids"]
    assert {f"invoice:{inv}", "whatif:1"} <= set(reminder["evidence_ids"])
    with chat.factory() as s:
        drafts = {a.tool: a for a in s.scalars(select(Action).where(Action.tier == "SUGGEST"))}
        assert set(drafts) == {"draft_reminder", "draft_terms_request"}
        assert all(a.status == "executed" for a in drafts.values())
        assert "net 14 to net 44" in drafts["draft_terms_request"].result["body"]
        assert s.scalar(select(SandboxEmail.id)) is None

    log = chat.events()
    start = log.index("agent_turn_started")
    assert log[start:].count("agent_tool_called") == 9 and log[start:].count("draft_created") == 2
    assert log[start:].count("action_proposed") == 1 and log[-1] == "agent_turn_finished"
    assert chat.client.get("/audit/verify", headers=owner).json()["ok"] is True

    # A human approves → the sandbox email goes to the stored address.
    approved = chat.client.post(f"/actions/{reminder['id']}/approve", headers=owner).json()
    assert approved["status"] == "executed"
    with chat.factory() as s:
        (email,) = s.scalars(select(SandboxEmail))
        assert email.to_address == "ap@harborlane.example"


def test_system_prompt_is_the_constant_and_tools_follow_the_role(chat: ChatHarness) -> None:
    chat.chat(chat.login("viewer"), "Hi")
    request = chat.model.requests[0]
    with chat.factory() as s:
        assert request["system"] == render_system(s.get(Business, 1), Role.viewer, DEFAULT_DEMO_TODAY)
    assert request["tools"] == ["get_cash_position", "get_ledger", "get_forecast", "get_insights", "explain_record"]
    chat.chat(chat.login("accountant"), "Hi")
    assert "send_reminder" in chat.model.requests[1]["tools"]
    assert "schedule_payment" not in chat.model.requests[1]["tools"]


def test_iteration_cap_forces_a_text_answer(chat: ChatHarness) -> None:
    chat.model = ScriptedModel(*([[("get_cash_position", {})]] * 20))
    done = _done(chat.chat(chat.login("owner"), "Loop forever"))
    assert len(chat.model.requests) == MAX_ITERATIONS == done["iterations"]
    assert [r["tool_choice"]["type"] for r in chat.model.requests] == ["auto"] * 7 + ["none"]
    assert "maximum number of steps" in done["message"]
    last = chat.model.requests[-1]["messages"]
    assert last[-1]["role"] == "user"  # every tool_use got its tool_result
    with chat.factory() as s:
        assert s.scalar(select(Action.id)) is None


def test_tool_errors_go_back_to_the_model(chat: ChatHarness) -> None:
    chat.model = ScriptedModel([("explain_record", {"ref": "invoice:999999"}), ("no_such_tool", {}),
                                ("run_what_if", {"scenarios": [{"type": "remove_series", "series_id": 999999}]})],
                               ["I could not find that invoice."])
    events = chat.chat(chat.login("owner"), "Explain invoice 999999")
    assert [d["ok"] for n, d in events if n == "tool"] == [False, False, False]
    results = chat.model.requests[1]["messages"][-1]["content"]
    assert all(r["is_error"] for r in results)
    assert "invoice:999999 not found" in results[0]["content"]
    assert _done(events)["message"] == "I could not find that invoice."


def test_model_outage_is_reported_and_audited(chat: ChatHarness) -> None:
    chat.model = ScriptedModel(ModelUnavailable("APIConnectionError"))
    events = chat.chat(chat.login("owner"), QUESTION)
    assert events[-1][0] == "error" and "unavailable" in events[-1][1]["message"]
    assert "agent_error" in chat.events()


def test_failed_citation_check_is_repaired_once(chat: ChatHarness) -> None:
    inv = chat.invoice_id("INV-1042")
    chat.model = ScriptedModel([("explain_record", {"ref": f"invoice:{inv}"})],
                               [f"INV-1042 is for $3,100.00 [[invoice:{inv}]]."],
                               [f"INV-1042 is for $4,800.00 [[invoice:{inv}]]."])
    events = chat.chat(chat.login("owner"), "How much is INV-1042?")
    (reset,) = [data for name, data in events if name == "reset"]
    assert reset["problems"] == [f"'$3,100.00' does not appear in [[invoice:{inv}]]"]
    feedback = chat.model.requests[2]["messages"][-1]["content"]
    assert "'$3,100.00' does not appear in" in feedback and "not the user" in feedback
    done = _done(events)
    assert done["warnings"] == [] and done["message"] == f"INV-1042 is for $4,800.00 [[invoice:{inv}]]."


def test_second_failure_is_shown_unverified_and_audited(chat: ChatHarness) -> None:
    chat.model = ScriptedModel(["Your balance is $99,999.00 [[invoice:999999]]."],
                               ["Your balance is $99,999.00. I have paid the supplier."])
    done = _done(chat.chat(chat.login("owner"), "Balance?"))
    assert done["message"].endswith(UNVERIFIED_NOTICE)
    assert any("has no citation" in w for w in done["warnings"])
    assert any("claims an action happened" in w for w in done["warnings"])
    assert "agent_citation_failed" in chat.events()


def test_conversation_continues_and_is_private(chat: ChatHarness) -> None:
    owner = chat.login("owner")
    first = chat.chat(owner, "Hi")
    conversation = first[0][1]["conversation_id"]
    chat.chat(owner, "Again", conversation_id=conversation)
    assert [m["content"] for m in chat.model.requests[1]["messages"] if m["role"] == "user"] == ["Hi", "Again"]
    chat.chat(chat.login("accountant"), "Peek", conversation_id=conversation, expect=404)
