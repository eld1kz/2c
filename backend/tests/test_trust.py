"""Phase 9: the Trust page shows the AI's boundaries, the gate's limits and what the guardrails did."""

from sqlalchemy import text

from app.audit import log as audit
from app.db.models import Policy, Tier
from app.policy.tiers import TOOL_TIERS
from app.services.trust import trust
from tests.conftest import ChatHarness, Demo


def _pay_verde(demo: Demo, key: str, amount: int):
    verde = demo.counterparties["Verde Green Coffee Imports"]
    invoice = next(i for i in demo.invoices.values() if i.counterparty_id == verde.id and i.status != "paid")
    return demo.service.propose(demo.actor("owner"), "schedule_payment",
                                {"payee_counterparty_id": verde.id, "invoice_id": invoice.id, "amount": amount,
                                 "date": "2026-10-02"}, idempotency_key=key)


def test_every_tool_is_listed_with_its_tier_and_the_agent_never_approves(demo: Demo) -> None:
    t = trust(demo.session, demo.business.id)
    assert [b["tool"] for b in t.boundaries] == list(TOOL_TIERS)
    by_tool = {b["tool"]: b for b in t.boundaries}
    assert "approve_action" not in TOOL_TIERS and not any("approve" in tool for tool in TOOL_TIERS)
    assert by_tool["schedule_payment"]["approve"] == ["owner"]
    assert by_tool["send_reminder"]["approve"] == ["owner", "accountant"]
    assert by_tool["get_forecast"]["propose"] == ["owner", "accountant", "viewer"]
    assert all(b["approve"] == [] for b in t.boundaries if b["tier"] != Tier.EXECUTE.value)


def test_a2_denial_is_counted_and_shown(demo: Demo) -> None:
    before = trust(demo.session, demo.business.id).activity["action_denied"]
    action = _pay_verde(demo, "trust-a2", 900_000)
    assert action.status == "denied"
    t = trust(demo.session, demo.business.id)
    assert t.activity["action_denied"] == before + 1
    assert t.recent_denials[0]["tool"] == "schedule_payment"
    assert "max_single_payment" in t.recent_denials[0]["reason"]


def test_viewer_refusal_is_counted(demo: Demo) -> None:
    action = _pay_verde(demo, "trust-a3", 10_000)
    before = trust(demo.session, demo.business.id).activity["role_refused"]
    try:
        demo.service.approve(demo.users["viewer"], action.id)
    except Exception:
        pass
    assert trust(demo.session, demo.business.id).activity["role_refused"] == before + 1


def test_other_businesses_events_are_not_counted(demo: Demo) -> None:
    before = trust(demo.session, demo.business.id).activity["action_denied"]
    audit.append(demo.session, "user:999", "action_denied", {"business_id": demo.business.id + 1, "tool": "x"},
                 now=demo.clock.now)
    assert trust(demo.session, demo.business.id).activity["action_denied"] == before


def test_chain_status_reports_tampering(demo: Demo) -> None:
    _pay_verde(demo, "trust-a5", 10_000)
    assert trust(demo.session, demo.business.id).chain.ok
    demo.session.execute(text("UPDATE audit_events SET actor = 'user:2' WHERE seq = 1"))
    demo.session.expire_all()
    chain = trust(demo.session, demo.business.id).chain
    assert not chain.ok and chain.broken_at_seq == 1


def test_every_role_reads_it_with_the_policy_limits_and_no_model_call(chat: ChatHarness) -> None:
    for role in ("owner", "accountant", "viewer"):
        r = chat.client.get("/trust", headers=chat.login(role))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["agent_can_approve"] is False and body["chain"]["ok"]
        with chat.factory() as s:
            policy = s.get(Policy, 1)
            assert body["limits"]["max_single_payment"] == policy.max_single_payment == 500_000
            assert body["limits"]["max_daily_payments"] == policy.max_daily_payments
        assert body["limits"]["max_proposals_per_turn"] == 3
    assert chat.model.requests == []


def test_unauthenticated_is_refused(chat: ChatHarness) -> None:
    assert chat.client.get("/trust").status_code == 401
