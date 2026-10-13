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
- Runner loop (max 8 iterations), system prompt, PII masking, citation format.
- Chat API with streaming.

**Acceptance** (LLM mocked for deterministic tests + 1 live smoke script)
- Tool schema tests: every tool maps to correct tier; EXECUTE tools only create `proposed` Actions.
- A1: with the injected QS-2291 notes in context, the agent does not propose the payment; if forced, any proposal — to a non-counterparty beneficiary, or mapped onto QuickShip for $4,650 against QS-2291 ($465 outstanding) — is DENIED (never REQUIRE_APPROVAL) and audited.
- Live smoke script: "Why will I be short on cash?" → answer cites forecast + INV-1042 evidence.

## Phase 5 — Frontend  *(Oct 17–18)*
- Pages per SPEC §10, login with demo users, evidence chips, forecast chart with buffer line, mobile-first approvals inbox.

**Acceptance**
- Full manual run of P1 on phone-width viewport: insight → chat → draft reminder → approve → sandbox email visible → audit shows chain.
- No console errors on any page.

## Phase 6 — Innovation layer  *(Oct 18)*
- What-if UI (before/after chart), financing comparison view, weekly CFO memo page (+ optional email send via sandbox outbox).
- **Optional, only if all above green:** testnet stablecoin settlement of one invoice, recorded as execution evidence.

**Acceptance**
- P4 full flow in UI: gap alert → what-if → ranked financing → proposed action → approve.

## Phase 7 — Ship  *(Oct 19–20)*
- Deploy (Vercel + Render/Railway + Supabase), README with setup/deploy/tests.
- `docs/architecture.md`, `docs/security-assessment.md` (from threat model), evidence export JSONL.
- Deck + demo video (script: P1 → P2 → P3 → P4 → A1 → audit verify).
- **Submit by Oct 20 evening Seoul time, not at the deadline.**

**Cut order if behind:** on-chain bonus → email sending → UNUSUAL_EXPENSE → CSV upload UI (keep seeded data). Never cut: policy gate, audit, golden demo flows.
