# Test cases: golden scenarios P1–P4 and adversarial cases A1–A5

The golden dataset (SPEC §9, `backend/seed/golden/`, generated with `seed=42`) is the demo and the test
suite at once. Every case below names the tests that prove it. `backend/tests/test_test_cases_doc.py`
fails if any test named here no longer exists, so this list cannot silently go stale.

How to run:

- Backend (no network; the LLM is a scripted fake): `cd backend && pytest -q`
- Browser tests against the running dev stack: `cd frontend && npx playwright test`
- Live end-to-end runs with the real model (spend a few cents of the daily AI budget):
  `LIVE=1 npx playwright test e2e/live-p1.spec.ts e2e/live-p4.spec.ts --project=desktop`
  (add `KEEP_STATE=1` to stop P4 before its reset, as for the committed evidence export; add
  `E2E_BASE_URL=https://<domain>` to run them against a deployed instance)

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

## Today (Phase 6c)

| Case | Tests |
|---|---|
| Today ranks the decisions and opens without writing or calling the model | `backend/tests/test_today.py::test_top_three_decisions_by_impact`, `backend/tests/test_today.py::test_today_reads_without_writing_or_calling_the_model` |
| Safe to spend = cash − cushion − this week's bills | `backend/tests/test_today.py::test_safe_to_spend_is_cash_minus_cushion_minus_this_weeks_bills`, `backend/tests/test_today.py::test_supplier_bills_due_this_week_count` |
| One tap prepares the action once; roles decide who may | `backend/tests/test_today.py::test_preparing_a_reminder_proposes_it_once`, `backend/tests/test_today.py::test_roles_for_preparing`, `frontend/e2e/today.spec.ts::"one tap prepares the reminder and opens it for approval"` |
| P3 price-review email: fixed template, stored contact, gated | `backend/tests/test_today.py::test_price_email_is_drafted_from_records_and_sent_to_the_stored_contact`, `backend/tests/test_today.py::test_price_request_gate` |
| Can I afford it: the verdict is the engine's (yes / not yet / no) | `backend/tests/test_afford.py::test_yes_when_no_week_dips_below_the_cushion`, `backend/tests/test_afford.py::test_not_yet_gives_the_first_safe_start`, `backend/tests/test_afford.py::test_no_when_nothing_in_13_weeks_works`, `backend/tests/test_afford.py::test_golden_barista_is_no_because_cash_is_already_short` |
| Today's chart shows the forecast with every approved fix; the ghost line shows the pending ones; a reset restores it | `backend/tests/test_today.py::test_the_chart_starts_on_the_base_forecast`, `backend/tests/test_today.py::test_each_approved_fix_lifts_the_curve_and_a_reset_restores_it`, `backend/tests/test_today.py::test_outlook_wording`, `backend/tests/test_today.py::test_today_sends_the_chart_to_every_role`, `frontend/e2e/today.spec.ts::"watch your future fix itself: the chart, the ghost line, and the curve lifting after an approval"`, `frontend/e2e/today.spec.ts::"the chart doesn't animate with reduced motion"` |
| Credentials never appear in a URL, even before the JavaScript loads | `frontend/e2e/login.spec.ts::"signing in never puts the email or password in a URL"`, `frontend/e2e/login.spec.ts::"before the app's JavaScript loads, the form can't submit and would only ever POST"` |
| Team roster sums exactly to the payroll series; viewers never receive pay | `backend/tests/test_team.py::test_weekly_pay_sums_exactly_to_the_payroll_series`, `backend/tests/test_team.py::test_viewers_get_names_and_roles_but_no_pay`, `backend/tests/test_team.py::test_owner_and_accountant_see_pay`, `frontend/e2e/team.spec.ts::"viewers see names and roles but no pay and no buttons"` |
| Hire and Raise open Can I afford it with both verdicts | `frontend/e2e/team.spec.ts::"the team, the Today line, and a raise opening Can I afford it with both verdicts"`, `frontend/e2e/team.spec.ts::"+ Hire someone asks with the role and weekly pay"` |
| Every "What is this?" term used in the UI exists in the glossary | `frontend/tests/glossary.test.ts`, `frontend/e2e/glossary.spec.ts::"financial terms explain themselves in plain English"` |
| Team lineup: labelled characters, tap for the card and a raise, hire preview, small on Today, reduced motion | `frontend/e2e/team.spec.ts::"the lineup: five labelled characters, tap one for their card, and a hire preview"`, `frontend/e2e/team.spec.ts::"Today shows the lineup small, and it opens the Team page"`, `frontend/e2e/team.spec.ts::"the characters bob on hover, but not with reduced motion"` |
| Can I afford it advises (Safe / Tight / Risky, go-ahead lowest point, ways to make it work); any role gets a character | `frontend/e2e/today.spec.ts::"can I afford it: a chip asks, both engine verdicts (today, with Today's fixes), a cited sentence and the chart"`, `frontend/e2e/team.spec.ts::"any role gets a character, and the list cards use the same illustrations"` |
| Can I afford it if Today's fixes succeed: a second engine verdict (Harbor Lane pays, Verde agrees); one chip says Yes | `backend/tests/test_afford.py::test_golden_fixes_are_harbor_lane_paying_and_verde_agreeing`, `backend/tests/test_afford.py::test_golden_chips_today_and_with_fixes`, `backend/tests/test_afford.py::test_longer_terms_move_only_the_suppliers_upcoming_invoices`, `frontend/e2e/today.spec.ts` |
| A raise is computed by the engine; the owner's amount is never evidence | `backend/tests/test_afford.py::test_a_raise_is_computed_by_the_engine`, `backend/tests/test_afford.py::test_the_tool_never_counts_the_supplied_amount_as_evidence` |
| The badge keeps the engine verdict; viewers and the budget are refused before the model | `backend/tests/test_afford.py::test_the_badge_keeps_the_engine_verdict_when_the_text_disagrees`, `backend/tests/test_afford.py::test_viewer_cannot_ask_and_the_model_is_not_called`, `backend/tests/test_afford.py::test_afford_respects_the_daily_ai_budget`, `frontend/e2e/today.spec.ts::"can I afford it: a chip asks, both engine verdicts (today, with Today's fixes), a cited sentence and the chart"` |

## Paperwork Center (Phase 6b)

| Case | Tests |
|---|---|
| September statements reconcile to the ledger to the cent | `backend/tests/test_statements.py::test_every_transaction_lands_in_exactly_one_line`, `backend/tests/test_statements.py::test_cash_flow_reconciles_with_pnl_snapshot_and_bank`, `backend/tests/test_statements.py::test_bank_statement_balance_matches_the_books` |
| A bank statement that disagrees, or has no running balance, is reported, not hidden | `backend/tests/test_statements.py::test_a_statement_that_disagrees_is_reported`, `backend/tests/test_statements.py::test_a_statement_without_running_balance_cannot_reconcile` |
| Figures agree across reports (month close, bank pack, forecast, dashboard) | `backend/tests/test_statements.py::test_bank_pack_agrees_with_month_close_and_forecast`, `backend/tests/test_statements.py::test_aging_matches_the_open_invoices`, `backend/tests/test_statements.py::test_obligations_are_the_forecasts_rent_and_lease_lines`, `backend/tests/test_statements.py::test_api_figures_agree_with_the_dashboard` |
| Pages, label, Not included and the PDF | `frontend/e2e/paperwork.spec.ts::"close my month: September reconciles and every report renders"`, `frontend/e2e/paperwork.spec.ts::"bank-ready pack: all sections, Not included, and a one-file PDF"` |

## Deployment cases (Phase 7)

| Case | Tests |
|---|---|
| Production refuses to boot on development defaults | `backend/tests/test_production.py::test_production_refuses_development_defaults` |
| Public demo logins: nobody can lock them out; sessions don't block or see each other | `backend/tests/test_production.py::test_demo_accounts_cannot_be_locked_out_in_production`, `backend/tests/test_production.py::test_shared_login_sessions_do_not_block_each_other_in_production`, `backend/tests/test_production.py::test_shared_login_sessions_do_not_see_each_others_conversations_in_production` |
| Scheduled demo reset keeps the audit chain | `backend/tests/test_demo_reset.py::test_reset_command_audits_who_ran_it_and_keeps_the_chain` |
| Evidence export verifies from the file alone | `backend/tests/test_evidence_export.py::test_the_export_verifies_from_the_file_alone`, `backend/tests/test_evidence_export.py::test_an_edited_export_file_fails_the_check` |
