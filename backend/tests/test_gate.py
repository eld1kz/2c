"""Policy gate rules (SPEC §8) on golden data: A1, A2 and every schedule_payment DENY rule."""

import pytest
from sqlalchemy.orm import Session

from app.db.models import Policy, Role, Transaction
from app.policy.gate import ActionRequest, Actor, Decision, GateContext, check
from app.policy.tiers import EXECUTE_PARAMS, TOOL_TIERS
from tests.conftest import Demo


def _ctx(demo: Demo) -> GateContext:
    return GateContext(demo.session, demo.session.get(Policy, demo.business.id), demo.clock(), demo.service.today)


def _check(demo: Demo, tool: str, params: dict, role: str = "owner") -> tuple[Decision, str]:
    result = check(ActionRequest(demo.business.id, tool, params), demo.actor(role), _ctx(demo))
    return result.decision, result.reason


def _pay(demo: Demo, payee: str, invoice: str, amount: int, **extra: object) -> dict:
    return {"payee_counterparty_id": demo.counterparties[payee].id, "invoice_id": demo.invoices[invoice].id,
            "amount": amount, "date": "2026-10-08", **extra}


def test_valid_payment_requires_approval(demo: Demo) -> None:
    assert _check(demo, "schedule_payment", _pay(demo, "Verde Green Coffee Imports", "VGC-5513", 219_600)) == (
        Decision.REQUIRE_APPROVAL, "")


def test_a1_injection_mapped_onto_quickship_is_denied_on_outstanding(demo: Demo) -> None:
    decision, reason = _check(demo, "schedule_payment", _pay(demo, "QuickShip Logistics", "QS-2291", 465_000))
    assert decision == Decision.DENY and "outstanding balance 46500" in reason


@pytest.mark.parametrize("extra", [
    {"payee_name": "QS Logistics Holdings"},
    {"account_number": "000123456789"},
    {"beneficiary": {"bank": "Bayline Trust", "account": "000123456789"}},
])
def test_a1_payee_or_bank_fields_are_not_accepted(demo: Demo, extra: dict) -> None:
    decision, reason = _check(demo, "schedule_payment", _pay(demo, "QuickShip Logistics", "QS-2291", 46_500, **extra))
    assert decision == Decision.DENY and "Extra inputs are not permitted" in reason


def test_a2_over_limit_is_denied(demo: Demo) -> None:
    decision, reason = _check(demo, "schedule_payment", _pay(demo, "Verde Green Coffee Imports", "VGC-5513", 900_000))
    assert decision == Decision.DENY and "exceeds max_single_payment 500000" in reason


@pytest.mark.parametrize("payee,invoice,amount,reason", [
    ("Harbor Lane Café", "INV-1042", 100, "payee is not on the payee allowlist"),
    ("Verde Green Coffee Imports", "QS-2291", 100, "invoice is not an open payable of this payee"),  # other payee's
    ("Verde Green Coffee Imports", "VGC-5512", 100, "invoice is not an open payable of this payee"),  # paid
    ("QuickShip Logistics", "QS-2291", 46_501, "exceeds the invoice's outstanding balance 46500"),
])
def test_payment_deny_rules(demo: Demo, payee: str, invoice: str, amount: int, reason: str) -> None:
    decision, got = _check(demo, "schedule_payment", _pay(demo, payee, invoice, amount))
    assert decision == Decision.DENY and reason in got


def test_unknown_payee_and_receivable_invoice_denied(demo: Demo) -> None:
    params = _pay(demo, "Verde Green Coffee Imports", "VGC-5513", 100) | {"payee_counterparty_id": 99_999}
    assert _check(demo, "schedule_payment", params) == (Decision.DENY, "payee is not an existing counterparty")
    demo.counterparties["Harbor Lane Café"].is_allowed_payee = True  # even if a customer were allowlisted
    decision, reason = _check(demo, "schedule_payment", _pay(demo, "Harbor Lane Café", "INV-1042", 100))
    assert (decision, reason) == (Decision.DENY, "invoice is not an open payable of this payee")


@pytest.mark.parametrize("bad", [{"amount": "465.00"}, {"amount": 46_500.0}, {"amount": 0}, {"amount": -5}])
def test_amount_must_be_positive_integer_cents(demo: Demo, bad: dict) -> None:
    params = _pay(demo, "QuickShip Logistics", "QS-2291", 1) | bad
    assert _check(demo, "schedule_payment", params)[0] == Decision.DENY


def test_outstanding_counts_bank_payments(demo: Demo) -> None:
    qs = demo.invoices["QS-2291"]
    demo.session.add(Transaction(account_id=1, date=demo.service.today, amount=-40_000, currency="USD",
                                 raw_description="ACH DEBIT QUICKSHIP LOGISTICS QS-2291", source_file="t.csv",
                                 invoice_id=qs.id))
    demo.session.flush()
    decision, reason = _check(demo, "schedule_payment", _pay(demo, "QuickShip Logistics", "QS-2291", 6_501))
    assert decision == Decision.DENY and "outstanding balance 6500" in reason


def test_roles_viewer_read_only_accountant_reminders_only(demo: Demo) -> None:
    pay = _pay(demo, "Verde Green Coffee Imports", "VGC-5513", 100)
    assert _check(demo, "schedule_payment", pay, "viewer") == (Decision.DENY, "role viewer may not use schedule_payment")
    assert _check(demo, "schedule_payment", pay, "accountant")[0] == Decision.DENY
    assert _check(demo, "draft_reminder", {}, "viewer")[0] == Decision.DENY
    assert _check(demo, "get_forecast", {}, "viewer") == (Decision.ALLOW, "")
    assert _check(demo, "rank_financing", {}, "accountant") == (Decision.ALLOW, "")


def test_actor_from_other_business_and_unknown_tool_denied(demo: Demo) -> None:
    outsider = Actor(business_id=demo.business.id + 1, user_id=1, role=Role.owner)
    result = check(ActionRequest(demo.business.id, "get_forecast", {}), outsider, _ctx(demo))
    assert (result.decision, result.reason) == (Decision.DENY, "actor belongs to another business")
    assert _check(demo, "transfer_funds", {}) == (Decision.DENY, "unknown tool 'transfer_funds'")


def test_reminder_rules(demo: Demo) -> None:
    draft = demo.service.record_draft(demo.actor("owner"), demo.invoices["INV-1042"].id, "polite")
    ok = {"invoice_id": demo.invoices["INV-1042"].id, "draft_id": draft.id}
    assert _check(demo, "send_reminder", ok, "accountant") == (Decision.REQUIRE_APPROVAL, "")
    assert _check(demo, "send_reminder", ok | {"invoice_id": demo.invoices["VGC-5513"].id})[1] == (
        "invoice is not an open receivable")
    assert _check(demo, "send_reminder", ok | {"invoice_id": demo.invoices["INV-1047"].id})[1] == (
        "draft is not a reminder draft for this invoice")
    demo.counterparties["Harbor Lane Café"].contact_email = None
    assert _check(demo, "send_reminder", ok)[1] == "customer has no stored contact email"


def test_terms_request_rules(demo: Demo) -> None:
    verde, harbor = demo.counterparties["Verde Green Coffee Imports"], demo.counterparties["Harbor Lane Café"]
    draft = demo.service.record_terms_draft(demo.actor("owner"), verde.id, 30)
    ok = {"counterparty_id": verde.id, "draft_id": draft.id}
    assert _check(demo, "send_terms_request", ok) == (Decision.REQUIRE_APPROVAL, "")
    assert _check(demo, "send_terms_request", ok, "accountant") == (
        Decision.DENY, "role accountant may not use send_terms_request")  # owner only
    assert _check(demo, "send_terms_request", ok | {"counterparty_id": harbor.id})[1] == (
        "counterparty is not a supplier of this business")
    quickship = demo.counterparties["QuickShip Logistics"].id
    assert _check(demo, "send_terms_request", ok | {"counterparty_id": quickship})[1] == (
        "draft is not a terms-request draft for this supplier")
    reminder = demo.service.record_draft(demo.actor("owner"), demo.invoices["INV-1042"].id, "polite")
    assert _check(demo, "send_terms_request", ok | {"draft_id": reminder.id})[1] == (
        "draft is not a terms-request draft for this supplier")
    assert _check(demo, "send_terms_request", ok | {"to": "x@evil.example"})[1].startswith("invalid parameters")
    demo.clock.advance(days=8)
    assert _check(demo, "send_terms_request", ok)[1] == "draft is older than 7 days; draft a new terms request"
    fresh = demo.service.record_terms_draft(demo.actor("owner"), verde.id, 30)
    verde.contact_email = None
    assert _check(demo, "send_terms_request", ok | {"draft_id": fresh.id})[1] == "supplier has no stored contact email"


@pytest.mark.parametrize("option,amount,decision", [
    ("overdraft", 1_500_000, Decision.REQUIRE_APPROVAL),
    ("overdraft", 1_500_001, Decision.DENY),
    ("short_term_loan", 5_000_000, Decision.REQUIRE_APPROVAL),
    ("invoice_factoring", 1_392_300, Decision.REQUIRE_APPROVAL),  # 85% of $16,380 open AR ≤ 30 days past due
    ("invoice_factoring", 1_392_301, Decision.DENY),
    ("supplier_terms_extension", 100, Decision.DENY),  # not a loan product
])
def test_loan_application_limits(demo: Demo, option: str, amount: int, decision: Decision) -> None:
    assert _check(demo, "submit_loan_application", {"option_id": option, "amount": amount})[0] == decision


def test_every_execute_tool_has_a_closed_schema() -> None:
    execute = {tool for tool, tier in TOOL_TIERS.items() if tier == "EXECUTE"}
    assert execute == set(EXECUTE_PARAMS) == {"send_reminder", "send_terms_request", "schedule_payment",
                                              "submit_loan_application"}
    assert set(EXECUTE_PARAMS["send_terms_request"].model_fields) == {"counterparty_id", "draft_id"}
    assert all(model.model_config["extra"] == "forbid" for model in EXECUTE_PARAMS.values())
    assert set(EXECUTE_PARAMS["schedule_payment"].model_fields) == {"payee_counterparty_id", "invoice_id", "amount", "date"}
    assert TOOL_TIERS["draft_terms_request"] == "SUGGEST"


def test_cooldown_window(demo: Demo) -> None:
    svc, inv = demo.service, demo.invoices["INV-1042"]
    draft = svc.record_draft(demo.actor("owner"), inv.id, "firm")
    sent = svc.propose(demo.actor("owner"), "send_reminder", {"invoice_id": inv.id, "draft_id": draft.id},
                       idempotency_key="reminder-1")
    svc.approve(demo.users["owner"], sent.id)
    params = {"invoice_id": inv.id, "draft_id": draft.id}
    demo.clock.advance(days=6, hours=23)
    assert _check(demo, "send_reminder", params)[0] == Decision.DENY
    demo.clock.advance(hours=2)
    assert _check(demo, "send_reminder", params) == (Decision.DENY, "draft is older than 7 days; draft a new reminder")
    fresh = svc.record_draft(demo.actor("owner"), inv.id, "firm")
    assert _check(demo, "send_reminder", {"invoice_id": inv.id, "draft_id": fresh.id})[0] == Decision.REQUIRE_APPROVAL
