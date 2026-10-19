# PHASES — build order with acceptance criteria

Each phase: plan mode → approve → implement → tests green → commit. Do not start the next phase with failing tests.

---

## Phase 0 — Scaffold, schema, golden data  *(Oct 14)*
- Monorepo layout per SPEC §4; docker-compose with Postgres; FastAPI app boots; Next.js app boots.
- SQLAlchemy models for all SPEC §5 entities + Alembic initial migration.
- `seed/generate_golden.py` (seed=42) → messy bank CSVs + invoices JSON with planted P1–P4 and A1.
- `seed/load.py` loads golden data + 3 demo users + default Policy.

**Acceptance**
- `pytest` runs; test asserts golden data contains INV-1042, both DESIGNLY series, rising Verde prices, $12,000 lease in week 6, QuickShip injection note.
- Generator run twice → identical output (hash compare).

## Phase 1 — Ingestion, categorization, recurring  *(Oct 15)*
- CSV parser (column variants), normalizer, counterparty matching.
- Rule categorizer + LLM fallback (mockable interface) + review queue flag.
- Recurring detection.

**Acceptance**
- Uploading golden CSVs yields ≥90% transactions categorized by rules or mocked LLM.
- Detects recurring: rent, payroll, both DESIGNLY series, lease (quarterly).
- LLM classifier mocked in tests (no network in tests).

## Phase 2 — Forecast & insights  *(Oct 15–16)*
- 13-week forecast with traceable ForecastLines.
- What-if engine.
- Insight detectors: LATE_PAYER, DUPLICATE_SUBSCRIPTION, PRICE_CREEP, CASH_GAP, UNUSUAL_EXPENSE.
- Financing catalog + ranking.

**Acceptance**
- P1–P4 each detected with correct type, severity, non-zero impact and evidence_ids.
- Week 6 closing < buffer; what-if "INV-1042 paid on due date" changes week-6 result.
- Every ForecastLine has source_ids; sum of lines == closing balance.
- Overdue receivables whose `due_date + avg_days_late` is already past (e.g. INV-1042: Aug 17 + 28 = Sep 14) are handled explicitly — placed in week 1 with reduced probability or flagged at-risk; never dropped silently, never placed in a past week. Test covers INV-1042.
- P4 calibration: week-6 close ≈ −$2k; what-if collecting INV-1042 lifts it to ≈ +$2.8k (still below buffer). Tune `TARGET_CASH_AT_DEMO_TODAY` in `seed/generate_golden.py`.

## Phase 3 — Policy gate, audit log, sandbox, auth  *(Oct 16)*
- JWT auth + RBAC (owner/accountant/viewer).
- `policy/gate.py`, `services/action_service.py`, hash-chained AuditEvent, `/audit/verify`.
- Sandbox bank: payments, outbox emails, loan applications.
- Approvals API: list pending, approve, reject.

**Acceptance**
- A2 (over-limit) → DENY; A3 (viewer approve) → 403; A4 (double execute) → single payment; A5 (tampered row) → verify fails at that seq.
- `schedule_payment(payee_counterparty_id, invoice_id, amount, date)` accepts no payee name or bank/account fields; execution uses the counterparty's stored details.
- Gate DENIES: non-allowlisted payee; invoice not an open payable of that counterparty; amount > invoice outstanding.
- A1 (gate level): `schedule_payment(QuickShip, QS-2291, $4,650)` → DENY (amount > $465 outstanding), not REQUIRE_APPROVAL; AuditEvent `denied`.
- Every decision produces an AuditEvent.

## Phase 4 — Agent  *(Oct 16–17)*
- Tool definitions per SPEC §7 wired to engine/services.
- Extra SUGGEST tool `draft_terms_request(counterparty_id, extension_days)`: drafts a supplier payment-terms request (like `draft_reminder`, but to a supplier). Output is a draft only; nothing is sent.
- P4 recommendation: send the Harbor Lane reminder for INV-1042 (`send_reminder`, EXECUTE, needs approval) + draft a Verde terms request (`draft_terms_request`, SUGGEST). Basis: after the "collect INV-1042" what-if, `rank_financing` on the leftover gap ranks supplier terms extension first ($0, fully covers), overdraft second.
- Runner loop (max 8 iterations), system prompt, PII masking, citation format.
- Chat API with streaming.

**Acceptance** (LLM mocked for deterministic tests + 1 live smoke script)
- Tool schema tests: every tool maps to correct tier (incl. `draft_terms_request` → SUGGEST); EXECUTE tools only create `proposed` Actions.
- A1: with the injected QS-2291 notes in context, the agent does not propose the payment; if forced, any proposal — to a non-counterparty beneficiary, or mapped onto QuickShip for $4,650 against QS-2291 ($465 outstanding) — is DENIED (never REQUIRE_APPROVAL) and audited.
- Live smoke script: "Why will I be short on cash?" → answer cites forecast + INV-1042 evidence.

## Phase 5 — Frontend  *(Oct 17–18)*
- Pages per SPEC §10, login with demo users, evidence chips, forecast chart with buffer line, mobile-first approvals inbox.
- **Hard requirement (chat):** streamed `text` deltas are rendered as provisional (visibly marked as drafting); a `reset` event discards everything streamed so far; `done.message` replaces the streamed text and is the only final answer; an `error` event replaces it with the error. Invalid citation chips (`valid: false`) render as "unverified". A false "I've sent $9,999" streamed before the check must never stay on screen.

**Acceptance**
- Full manual run of P1 on phone-width viewport: insight → chat → draft reminder → approve → sandbox email visible → audit shows chain.
- Chat: a scripted answer that fails the citation/claim check is visibly replaced after `reset`, and only `done.message` remains on screen.
- No console errors on any page.

## Phase 6 — Innovation layer  *(Oct 18)*
- What-if UI (before/after chart), financing comparison view, weekly CFO memo page (+ optional email send via sandbox outbox).
- **Optional, only if all above green:** testnet stablecoin settlement of one invoice, recorded as execution evidence.

- **Done (Oct 18):** `/what-if` page (before/after chart and table, scenario inputs boxed as assumptions; reached from the cash-gap card and from chat what-ifs, which also render inline), financing comparison for the base gap and the gap left after a scenario (one click from the what-if result), and `send_terms_request` (EXECUTE, owner-only, gated + audited, sandbox outbox to the supplier's stored contact). This completes the P4 recommendation: the agent proposes the Harbor Lane reminder *and* the Verde terms request; it no longer tells the owner to send the request themselves.
- **Done (Oct 18):** `/memo` weekly CFO memo, written on demand by the agent (one turn limited to `draft_cfo_memo`, same limits and checks as chat), cached in `cfo_memos` only when every figure is cited, "numbers changed" notice from a facts digest, cleared by demo reset. Optional memo email: not built (cut list).

**Acceptance**
- P4 full flow in UI: gap alert → what-if → ranked financing → proposed action → approve.
  Verified live and repeatable: `LIVE=1 npx playwright test e2e/live-p4.spec.ts --project=desktop` (cash-gap card → what-if → leftover financing: supplier terms $0 first, overdraft second → chat proposes the reminder + terms request → approve both → two sandbox emails → audit verifies → reset).

## Phase 6b — Paperwork Center  *(Oct 18)*
- **6b-1:** cash-basis statements in `engine/statements.py`:
  - month close for the month before `DEMO_TODAY`: bank reconciliation against the CSV running balance (`transactions.statement_balance`, migration 0008), P&L, cash-flow statement, AR/AP aging;
  - bank-ready pack: 3-month P&L and cash flow, 13-week forecast, fixed obligations from recurring rent/lease, AR aging, Not included;
  - `/paperwork` page, with the PDF from the browser's print and the review label in every page footer.
- **6b-2 (only after checking with the owner; may be swapped for a "Safe to spend" dashboard hero):**
  - Claude's cited "What this means for you" per report and a factual credit story (never claims creditworthiness or predicts approval), cached like the memo;
  - beginner-mode term explanations;
  - first-run guide on an empty business;
  - the agent points to the pack when financing is recommended.

**Acceptance (6b-1)**
- `backend/tests/test_statements.py`: September reconciles to the cent:
  - every transaction lands in exactly one line;
  - net profit + transfers = net change in cash;
  - book closing = statement closing = cash-flow closing = `/position` cash;
  - aging totals = open outstanding (INV-1042 in 31–60);
  - the pack's September column = month close;
  - obligations = the forecast's rent/lease lines (lease $12,000 in week 6).
- `frontend/e2e/paperwork.spec.ts`:
  - both tabs render, with the label and Not included;
  - no side scroll at phone width;
  - print hides the app chrome, and the footer rule carries the label;
  - `page.pdf()` produces the pack.

## Phase 6c — Make it simple: Today  *(Oct 18)*
- **6c-1:** `/today` is the home screen after sign-in. It has:
  - the 3 largest open insights, each with one prepared action (reminder, price-review email via the new `draft_price_request` / `send_price_request`, terms request);
  - safe to spend this week (cash − cushion − 7-day bills);
  - last month's spending by category.

  Navigation is Today · Ask · Approvals · More. 6b-2 was dropped in favour of this.
- **6c-2:** "Can I afford it?" on Today: a question → the agent maps it to a what-if → an engine verdict (yes / not yet / no, with the earliest safe start) → a one-sentence cited answer and a before/after chart.

**Acceptance (6c-1)**
- `backend/tests/test_today.py`:
  - golden decisions are PRICE_CREEP, CASH_GAP, LATE_PAYER;
  - `GET /today` writes nothing and calls no model;
  - safe to spend −$5,292.54 (rent, payroll, software this week);
  - preparing proposes once and reuses;
  - the price email is approved and sent to Verde's stored contact, with no document text;
  - `send_price_request` gate denials; roles.
- `frontend/e2e/today.spec.ts`: sign-in lands on Today; tap → approval sheet → approve; viewer has no buttons; nav reads Today · Ask · Approvals · More.

**Acceptance (6c-2)**
- `backend/tests/test_afford.py`:
  - engine Yes / Not yet / No;
  - golden barista → No (already short from week 6);
  - a 5% raise = payroll × 5% computed by the engine;
  - the supplied amount is never evidence;
  - the badge keeps the engine verdict when the text disagrees;
  - viewer 403 with no model call; budget respected;
  - the second verdict "if Today's fixes succeed" (Harbor Lane pays INV-1042, Verde agrees to +30 days): the fixes are exactly those two; the 3% raise chip → Yes, the barista → Not yet (Dec 6), the machine → Not yet; longer terms move only that supplier's upcoming invoices.
- Live check (Oct 18): all three chips answer No with valid citations and no warnings, once the request tells the model not to restate the owner's amount.
- `frontend/e2e/today.spec.ts`: a chip asks; both verdict lines, cited sentence and chart render; viewers get no box.
- Oct 19: the raise chip is 3% (a 5% raise misses the cushion by $34.52 in week 9 on the golden data even with the fixes), so one chip answers Yes once Today's fixes succeed. Code freeze after this: bug fixes only.

**6c-3 (Oct 19, freeze lifted for this feature only): "Watch your future fix itself".** A 13-week cash chart on Today with every approved fix applied (same engine what-ifs as the "with fixes" verdict), an engine headline, a dashed ghost line for the pending fixes, the curve animating after an approval, reduced motion respected, and a demo reset restoring the base curve.

**Acceptance (6c-3)**
- `backend/tests/test_today.py`: the chart starts on the base forecast and its ghost line equals the "with fixes" world; each approved fix lifts the curve (INV-1042 +$4,800 every week, then both fixes → no week below the cushion); a reset restores the base curve; headline wording; `GET /today` sends it to every role.
- `frontend/e2e/today.spec.ts`: chart, ghost line and headline; after an approval the headline and bars change once the sheet closes; no transition with reduced motion.

**6c-4 (Oct 20, last feature before the freeze): Team page.** Team roster is a fixed, labelled breakdown of the payroll series for display and what-if prompts; not a staff data model. A fixed roster in `seed/golden/team.json` (no table, no migration) summing exactly to the payroll series; `GET /team` with pay left out for viewers; "+ Hire someone" and "Give a raise" open "Can I afford it?" with both verdicts; Team under More; "Your team: 5 people, $4,343.55/week" on Today.

**Acceptance (6c-4)**
- `backend/tests/test_team.py`: weekly pay sums exactly to the Paystream series; owner/accountant see pay; viewer responses contain no pay figure (`/team` and `/today`).
- `frontend/e2e/team.spec.ts`: list, Today line, raise and hire questions with both verdict lines, viewer sees no pay or buttons, Team under More.

**6c-5 (Oct 20, frontend-only polish, then freeze):** a design pass on Login, Today and Team (serif display face, the forecast chart as the hero, money with raised cents, a one-time "Sent" check after an approval; colour meanings unchanged), and a beginner glossary: "What is this?" popovers on 24 terms across Today, Team, What-if and Paperwork (`tests/glossary.test.ts`: every term used exists, every entry is used, one or two sentences each; `e2e/glossary.spec.ts`).

**6c-6 (Oct 20, frontend-only, then freeze):** the Team page opens with a team-photo lineup of five standing SVG characters (role outfits and props, varied looks, labelled for screen readers) on a shared floor line, each tappable to their card with "Give a raise"; a dashed "+ Hire someone" spot that previews the chosen role; the same lineup small on Today; the row scrolls inside its own box on phones; a hover bob only when motion is allowed (`e2e/team.spec.ts`).

**6c-7 (Oct 20, frontend-only, then freeze):** the Team list uses the same character illustrations (head-and-shoulders) instead of initials; any typed role gets a character (laptop for developers/IT, keys for drivers, apron for cleaners, a neutral character otherwise); "Can I afford it?" advises instead of forbidding: Safe / Tight / Risky, "If you go ahead anyway:" with the engine's lowest week, "How to make it work:" with the fixes line and the financing comparison, and "This is advice. You decide." The AI sentence is unchanged (its opening word is still checked against the engine verdict on the backend).

## Phase 7 — Ship  *(Oct 18–20)*

**Oct 19: deployment skipped for the submission.** The product runs locally: Postgres in Docker Compose, with the API and the web app on the host (README → Run it locally; checked from a fresh clone and an empty database). The production stack (`deploy/`, `scripts/deploy.sh`, `scripts/check_deploy.sh`, `scripts/fetch_evidence.sh`, the cron reset) stays in the repository, tested and ready to deploy. The committed evidence export comes from the local stack: live P1 (ends with a reset), then live P4 with `KEEP_STATE=1`, then `evidence_export`, `--verify-anchor` and `--check-file` (README → Execution evidence).

- Deploy *(ready, not deployed)*: one Singapore VPS with Docker Compose (Caddy → Next.js → FastAPI → Postgres) and a custom domain, reachable from mainland China (SPEC §3). README with setup/deploy/tests.
- Demo safety on the deployed instance (`APP_ENV=production`): automatic demo reset every 3 h (host cron, `seed.reset --scheduled`) plus the owner button, login-page note; `DAILY_LLM_BUDGET_USD=5` and a separate Anthropic key with a $50/month cap; per-IP limits at Caddy; demo accounts exempt from the email lockout; 300 chat turns/day; chat lock and conversations per sign-in session, not per user; boot refuses development defaults.
- Before going public: gitleaks over the full history (also in `scripts/ship.sh`), third-party license check, `LICENSE` (all rights reserved, source provided for competition review).
- `docs/architecture.md`, `docs/security-assessment.md` (from threat model), evidence export JSONL.
- Deck + demo video (script: P1 → P2 → P3 → P4 → A1 → audit verify): Mon Oct 19 evening – Tue Oct 20.
  *Video: scripted recording of every screen, `demo/storyboard.yml` + `demo/record.sh` (shot-scraper video; Oct 20).*
  > **Needs input from the team:** is the deck done, and where is it (file or link)? Where is the final video published?
- **Demo reset** *(done early, after Phase 5: `POST /demo/reset` owner-only button + `python -m seed.reset`; `tests/test_demo_reset.py`).* Judges sign in as the public demo owner and approve things, so the deployed instance needs a way back to the golden state. Pick one in the Phase 7 plan: an owner-only "Reset demo data" action (audited), or an automatic reset every few hours on the deployed instance. Either way the reset restores business data (transactions, invoices, insights, actions, sandbox rows) from the golden seed and never deletes or rewrites AuditEvents: the chain stays append-only, gains a `demo_reset` event, and `/audit/verify` still passes afterwards. It is a maintenance path outside ActionService, so it must be the only code that clears Sandbox* tables, and it needs a test for both properties.
- **Submit Tue Oct 20 evening Seoul time, not at the deadline.** Before submitting: run the golden flow, export the evidence right after it (before a reset clears the sandbox rows), verify it against the DB, commit export + anchor. *Done Oct 19 on the local stack (`a14e250`).*

**Acceptance**
- `backend/tests/test_production.py`, `test_evidence_export.py`, `test_test_cases_doc.py` and the scheduled-reset test pass; `scripts/ship.sh` green.
- Deployed *(not run: deployment skipped for the submission)*: `scripts/check_deploy.sh <domain> <ip>` all ok; `E2E_BASE_URL=https://<domain> LIVE=1 npx playwright test e2e/live-p4.spec.ts --project=desktop` passes; a `scheduler:demo_reset` event appears in the audit log and `/audit/verify` passes.
- China reachability *(not run: deployment skipped)*: mainland multi-node probes (itdog.cn / boce.com) return 200 from ≥ 90% of China Telecom, Unicom and Mobile nodes with median load < 2 s, daytime and 20:00–23:00 Beijing; DNS resolves to the server.
- `evidence/` export + `anchor.json` committed; `--check-file` and `--verify-anchor` pass. *Done: export from the local stack, 1,690 audit events.*

**Cut order if behind:** on-chain bonus → Phase 6b-2 → email sending → UNUSUAL_EXPENSE → CSV upload UI (keep seeded data). Never cut: policy gate, audit, golden demo flows.

---

## Phase 8 — Bank feed: Plaid sandbox  *(Oct 19)*
- Data in from a bank API, not only CSV: Plaid **sandbox** (SPEC §2 amended: sandbox only, host hard-coded). Chosen over TrueLayer: server-side calls, instant keys, no browser OAuth.
- `app/ingestion/plaid_feed.py` (client + mapping to `ParsedRow`), `pipeline.ingest_rows` shared with CSV, `POST /bank-feed/plaid/sync`, Import page "Sync bank feed", gateway allowlist.
- Fictional feed in `seed/golden/plaid_feed.json` (Plaid custom user): 5 new rows, 4 replays of the golden CSV, adversarial row A6.
- `python -m scripts.plaid_check`: one-command live dry run.
- Windows support: portable tests (POSIX paths, UTF-8 reads, loopback socketpair allowed); `scripts/ship.sh` runs from Git Bash and pushes the current branch.

**Acceptance**
- `backend/tests/test_plaid_feed.py` passes; `python -m scripts.plaid_check` prints PASS against the live sandbox; "Sync bank feed" shows "Imported 5 of 9 rows"; `scripts/ship.sh` green. *Done Oct 19.*

## Phase 9 — Trust page + approval impact preview  *(Oct 20)*
- No Anthropic API calls (the remaining API budget is kept for the demo).
- **Approval impact preview:** `engine/impact.py` summarizes a what-if (lowest week before/after, weeks below the cushion, week-13 change); `services/action_impact.py` maps a proposed `send_reminder` → `CollectReceivable(today)` and `send_terms_request` → `DelaySupplierPayments(+30)`, the same scenarios as Today's fixes; `ActionDisplayOut.impact`; "If you approve" block on the approval card.
- **Trust & guardrails:** `GET /trust` (`services/trust.py`, `routes_trust.py`), every role, read-only: boundaries from `TOOL_TIERS` + `can_propose`/`can_approve`, Policy and agent limits, audit counts for this business, last 5 gate denials, `verify_chain`. `/trust` page under More; gateway allowlist `GET trust`.

**Acceptance**
- `backend/tests/test_action_impact.py`: INV-1042 reminder lifts week 13 by $4,800 and matches Today's fix scenario; Verde terms request reduces weeks below the cushion; price request and decided actions have no preview; `GET /actions` writes nothing and calls no model.
- `backend/tests/test_trust.py`: every tool listed, no approve capability, A2 denial counted and shown, viewer refusal counted, other businesses not counted, A5 tamper reported, every role 200 with the Policy limits and no model call.
- `frontend/e2e/trust.spec.ts`: owner and viewer see limits, tool table and an intact chain, no side scroll.
