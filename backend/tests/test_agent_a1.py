"""A1 through the agent: QS-2291's injected notes reach the model only as masked, marked data, and
any payment proposal the injection could produce is DENIED (never proposed) and audited."""

import json

import pytest
from sqlalchemy import select

from app.agent.prompts import render_system
from app.api import routes_chat
from app.config import DEFAULT_DEMO_TODAY
from app.db.models import Action, AuditEvent, Business, Role, SandboxPayment
from tests.conftest import ChatHarness
from tests.fakes import ScriptedModel, tool_result

ASK = "Please handle whatever QuickShip's invoice QS-2291 needs."
ACCOUNT = "000123456789"


def _no_payment_anywhere(chat: ChatHarness, owner: dict[str, str]) -> None:
    assert chat.client.get("/actions", params={"status": "proposed"}, headers=owner).json() == []
    with chat.factory() as s:
        assert s.scalar(select(SandboxPayment.id)) is None
        stored = json.dumps([e.payload for e in s.scalars(select(AuditEvent))] +
                            [a.params for a in s.scalars(select(Action))])
    assert ACCOUNT not in stored


def test_injected_notes_are_masked_data_and_nothing_is_proposed(chat: ChatHarness) -> None:
    qs = chat.invoice_id("QS-2291")
    chat.model = ScriptedModel(
        [("explain_record", {"ref": f"invoice:{qs}"})],
        [f"QS-2291's notes ask for a payment to a new bank account. I did not act on that [[invoice:{qs}]]."])
    owner = chat.login("owner")
    events = chat.chat(owner, ASK)

    first, second = chat.model.requests
    with chat.factory() as s:
        assert first["system"] == render_system(s.get(Business, 1), Role.owner, DEFAULT_DEMO_TODAY)
    assert "SYSTEM NOTICE" not in first["system"] and "Bayline" not in first["system"]
    assert ACCOUNT not in chat.model.sent  # masked before it ever left the server (T8)
    notes = tool_result(second["messages"], "explain_record")["data"]["notes"]
    assert notes["instruction_like"] is True and notes["source"] == "invoice notes written by the counterparty"
    assert "⟨ACCOUNT_1⟩ at Bayline Trust" in notes["untrusted_text"]
    assert "Bayline" not in json.dumps([m for m in second["messages"] if m["role"] == "assistant"])

    conversation = routes_chat.conversations._items[events[0][1]["conversation_id"]]
    assert ("money", "465000") not in conversation.memory.index.values[f"invoice:{qs}"]  # $4,650.00 from the note
    assert ("money", "46500") in conversation.memory.index.values[f"invoice:{qs}"]  # the real total
    assert [n for n, _ in events if n == "action"] == []
    with chat.factory() as s:
        assert s.scalar(select(Action.id)) is None
    _no_payment_anywhere(chat, owner)


FORCED = {
    "injected_beneficiary": ({"payee_counterparty_id": "quickship", "invoice_id": "qs", "amount": 465_000,
                              "date": "2026-10-10", "beneficiary_name": "QS Logistics Holdings",
                              "account_number": ACCOUNT}, "invalid parameters"),
    "not_a_counterparty": ({"payee_counterparty_id": 999_999, "invoice_id": "qs", "amount": 465_000,
                            "date": "2026-10-10"}, "payee is not an existing counterparty"),
    "mapped_onto_quickship": ({"payee_counterparty_id": "quickship", "invoice_id": "qs", "amount": 465_000,
                               "date": "2026-10-10"}, "exceeds the invoice's outstanding balance 46500"),
    "not_allowlisted": ({"payee_counterparty_id": "harbor", "invoice_id": "qs", "amount": 46_500,
                         "date": "2026-10-10"}, "payee is not on the payee allowlist"),
}


@pytest.mark.parametrize("case", FORCED)
def test_forced_payment_from_the_injection_is_denied_and_audited(chat: ChatHarness, case: str) -> None:
    template, reason = FORCED[case]
    ids = {"quickship": chat.counterparty_id("QuickShip Logistics"), "qs": chat.invoice_id("QS-2291"),
           "harbor": chat.counterparty_id("Harbor Lane Café")}
    params = {k: ids.get(v, v) if isinstance(v, str) else v for k, v in template.items()}
    chat.model = ScriptedModel(
        [("explain_record", {"ref": f"invoice:{ids['qs']}"})],
        [("schedule_payment", {**params, "rationale": "Invoice note says QuickShip changed banks."})],
        ["The payment was denied by the policy gate."])
    owner = chat.login("owner")
    events = chat.chat(owner, ASK)

    (action_event,) = [d for n, d in events if n == "action"]
    assert action_event["status"] == "denied"
    result = tool_result(chat.model.requests[-1]["messages"], "schedule_payment")["data"]
    assert result["status"] == "denied" and reason in result["reason"] and "do not retry" in result["next_step"]
    with chat.factory() as s:
        (action,) = s.scalars(select(Action))
        assert (action.status, action.proposed_by, action.tier) == ("denied", "agent", "EXECUTE")
        assert reason in action.result["denied"]
        denial = s.scalar(select(AuditEvent).where(AuditEvent.event_type == "action_denied"))
        assert denial.payload["action_id"] == action.id and reason in denial.payload["reason"]
        assert denial.actor.startswith("agent:user:")
        assert s.scalar(select(AuditEvent).where(AuditEvent.event_type == "action_proposed")) is None
    _no_payment_anywhere(chat, owner)
    assert chat.client.get("/audit/verify", headers=owner).json()["ok"] is True


def test_claiming_the_payment_was_made_is_caught(chat: ChatHarness) -> None:
    chat.model = ScriptedModel(["I've scheduled the payment to QuickShip's new account."],
                               ["I did not schedule any payment; the request in the note was not followed."])
    events = chat.chat(chat.login("owner"), ASK)
    assert ("reset", {"reason": "citation_check"}) in events
    assert "claims an action happened" in chat.model.requests[1]["messages"][-1]["content"]
    assert events[-1][1]["warnings"] == []
