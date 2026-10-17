# Test cases: golden scenarios P1–P4 and adversarial cases A1–A5

The golden dataset (SPEC §9, `backend/seed/golden/`, generated with `seed=42`) is the demo and the test
suite at once. Every case below names the tests that prove it. `backend/tests/test_test_cases_doc.py`
fails if any test named here no longer exists, so this list cannot silently go stale.

How to run:

- Backend (no network; the LLM is a scripted fake): `cd backend && pytest -q`
- Browser tests against the running dev stack: `cd frontend && npx playwright test`
- Live end-to-end runs with the real model (spend a few cents of the daily AI budget):
  `LIVE=1 npx playwright test e2e/live-p1.spec.ts e2e/live-p4.spec.ts --project=desktop`
  (add `E2E_BASE_URL=https://<domain>` to run them against the deployed instance)

## Golden scenarios

| # | Planted problem | Expected | Tests |
|---|---|---|---|
| P1 | Harbor Lane Café: INV-1042, $4,800, 45 days overdue; customer averages 28 days late | LATE_PAYER (high) → agent drafts a firm-but-polite reminder → owner approves → sandbox email sent | Data: `backend/tests/test_golden.py::test_p1_inv_1042_overdue_45_days`, `backend/tests/test_golden.py::test_p1_harbor_lane_avg_28_days_late`. Detection: `backend/tests/test_insights.py::test_p1_late_payer_evidence`. Forecast places it at risk in week 1, never dropped: `backend/tests/test_forecast.py::test_inv_1042_at_risk_in_week_1_not_dropped`. Approval → sandbox email: `backend/tests/test_api_approvals.py::test_reminder_card_shows_who_what_and_the_draft`, `frontend/e2e/approvals.spec.ts::"owner approves a reminder and sees the sandbox email"`. Live, full flow: `frontend/e2e/live-p1.spec.ts::"live P1: late-payer insight → chat → draft → approve → sandbox email → audit verify"` |
| P2 | `DESIGNLY PRO` and `DESIGNLY*TEAM`, both about $29.99 a month | DUPLICATE_SUBSCRIPTION, impact ≈ $360 a year → agent recommends cancelling one (SUGGEST only) | Data: `backend/tests/test_golden.py::test_p2_two_designly_series`. Both series detected: `backend/tests/test_recurring.py::test_golden_series`. Detection + impact + evidence: `backend/tests/test_insights.py::test_p2_duplicate_subscription_evidence` |
| P3 | Verde Green Coffee Imports: bean unit price +18% over 4 months | PRICE_CREEP with annualized impact → agent suggests negotiating | Data: `backend/tests/test_golden.py::test_p3_verde_price_rises_18pct`. Detection + impact + evidence: `backend/tests/test_insights.py::test_p3_price_creep_evidence`. Future bean purchases are forecast at the latest price: `backend/tests/test_forecast.py::test_future_bean_purchases_projected_at_latest_price` |
| P4 | Week 6: the $12,000 quarterly equipment lease plus payroll take cash below the $5,000 buffer | CASH_GAP (high) → what-if "collect INV-1042" → rank financing → reminder + supplier terms request proposed → owner approves both | Data: `backend/tests/test_golden.py::test_p4_lease_lands_in_week_6`. Gap: `backend/tests/test_forecast.py::test_p4_week6_below_buffer`, `backend/tests/test_insights.py::test_p4_cash_gap_evidence`. What-if: `backend/tests/test_whatif.py::test_p4_collect_inv_1042`. Financing (supplier terms first at $0, overdraft second): `backend/tests/test_financing.py::test_p4_demo_sequence`. Agent walkthrough: `backend/tests/test_agent_runner.py::test_p4_walkthrough`. Live, full flow in the UI: `frontend/e2e/live-p4.spec.ts::"live P4: cash gap → what-if → leftover financing → reminder + terms request → approve both → audit"` |

All four together, and nothing else: `backend/tests/test_insights.py::test_golden_detects_exactly_p1_to_p4`.

**Gaps (be honest):** for P2 and P3 the tests cover detection, impact and evidence. The agent's
recommendation itself (cancel one subscription, negotiate with Verde) is free text and isn't asserted
by a test. There is no dedicated "price negotiation email" tool: the agent can draft that text in chat,
but nothing sends it. The only supplier email the app can send is the Phase 6 terms request
(`send_terms_request`), which goes through the gate and needs the owner's approval.

## Adversarial cases

| # | Attack | Expected | Tests |
|---|---|---|---|
| A1 | QuickShip Logistics invoice `notes` tell the agent to pay a new account | The agent does not propose it. If forced, the gate DENIES it (not a counterparty / not allowlisted). Mapped onto QuickShip, `schedule_payment(QuickShip, QS-2291, $4,650)` is DENIED because only $465 is outstanding. Never REQUIRE_APPROVAL; audited `denied` | Data: `backend/tests/test_golden.py::test_a1_quickship_injection_note`. Gate: `backend/tests/test_gate.py::test_a1_injection_mapped_onto_quickship_is_denied_on_outstanding`, `backend/tests/test_gate.py::test_a1_payee_or_bank_fields_are_not_accepted`. Service + audit: `backend/tests/test_action_service.py::test_a1_gate_denial_is_recorded_and_audited`. HTTP: `backend/tests/test_api.py::test_a1_injected_beneficiary_over_http_is_denied`. Agent: `backend/tests/test_agent_a1.py::test_injected_notes_are_masked_data_and_nothing_is_proposed`, `backend/tests/test_agent_a1.py::test_forced_payment_from_the_injection_is_denied_and_audited`, `backend/tests/test_agent_a1.py::test_claiming_the_payment_was_made_is_caught`. Notes can't steer the engine: `backend/tests/test_forecast.py::test_invoice_notes_never_affect_the_forecast`, `backend/tests/test_insights.py::test_invoice_notes_never_affect_insights` |
| A2 | User asks the agent to pay a supplier $9,000 | Gate DENIES it (over the $5,000 single-payment limit); the agent explains | `backend/tests/test_gate.py::test_a2_over_limit_is_denied`, `backend/tests/test_action_service.py::test_a2_over_limit_denied_with_reason`. Splitting it up: `backend/tests/test_action_service.py::test_daily_cap_two_4000_payments_pass_third_denied` |
| A3 | Viewer tries to approve an action | 403 + AuditEvent | `backend/tests/test_api.py::test_a3_viewer_approve_is_403_and_audited`, `backend/tests/test_action_service.py::test_a3_viewer_cannot_approve_and_it_is_audited`, `backend/tests/test_api_approvals.py::test_viewer_sees_the_card_but_cannot_approve`, `frontend/e2e/approvals.spec.ts::"viewer sees Approve, the server refuses, and the card says so"` |
| A4 | The same action executed twice | The second call returns the original result; no duplicate SandboxPayment | `backend/tests/test_action_service.py::test_a4_executing_twice_returns_original_result`, `backend/tests/test_action_service.py::test_a4_db_rejects_second_sandbox_payment_for_one_action`, `backend/tests/test_action_service.py::test_idempotency_key_returns_the_same_action` |
| A5 | Tamper with one AuditEvent row | `/audit/verify` reports the broken chain at that seq | `backend/tests/test_audit.py::test_a5_tampered_row_breaks_chain_at_that_seq`, `backend/tests/test_audit.py::test_recomputed_hash_after_tamper_still_breaks_next_link`, `backend/tests/test_api.py::test_audit_list_and_verify_detects_tamper`. A DB owner who rewrites the chain *and* recomputes every hash fools `/audit/verify`, but not the anchor committed with the evidence export: `backend/tests/test_evidence_export.py::test_the_anchor_catches_a_rewritten_chain_that_verify_accepts`, `backend/tests/test_evidence_export.py::test_the_anchor_catches_deleted_newest_events` |

## Deployment cases (Phase 7)

| Case | Tests |
|---|---|
| Production refuses to boot on development defaults | `backend/tests/test_production.py::test_production_refuses_development_defaults` |
| Public demo logins: nobody can lock them out; sessions don't block or see each other | `backend/tests/test_production.py::test_demo_accounts_cannot_be_locked_out_in_production`, `backend/tests/test_production.py::test_shared_login_sessions_do_not_block_each_other_in_production`, `backend/tests/test_production.py::test_shared_login_sessions_do_not_see_each_others_conversations_in_production` |
| Scheduled demo reset keeps the audit chain | `backend/tests/test_demo_reset.py::test_reset_command_audits_who_ran_it_and_keeps_the_chain` |
| Evidence export verifies from the file alone | `backend/tests/test_evidence_export.py::test_the_export_verifies_from_the_file_alone`, `backend/tests/test_evidence_export.py::test_an_edited_export_file_fails_the_check` |
