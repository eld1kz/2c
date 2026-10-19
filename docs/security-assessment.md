# Security self-assessment

What Ledgerwise protects, how, how we tested it, and what is still open. This document condenses
the living [threat model](threat-model.md), where every row names its mitigations and tests in full
detail. The design is described in [architecture.md](architecture.md#security-design).

**Scope and assumptions.** This is a competition demo. All data is fictional (Ember & Oak Coffee
Roasters). Every "world-changing" effect is a row in a sandbox table: no real bank, inbox or lender
is ever touched. The three demo accounts are public by design. The main things to protect are
**(1) that no payment, email or application happens without an authorized human's approval and
within policy**, **(2) the integrity of the audit trail**, and **(3) that every number the AI states
is real**. Secondary concerns are PII going to the LLM, cost abuse, and a shared demo staying usable. For the submission the app runs locally; the production stack in
`deploy/` is ready but not deployed, so the deployment controls below (Caddy, cron reset, `APP_ENV=production`)
describe that stack.

## Permission tiers

Every agent tool has a fixed tier (`backend/app/policy/tiers.py`). The gate enforces it in code, so
a prompt cannot change it.

| Tier | Tools | What happens when called |
|---|---|---|
| READ | `get_cash_position`, `get_ledger`, `get_forecast`, `get_insights`, `explain_record` | Returns engine results. Audited |
| SUGGEST | `run_what_if`, `rank_financing`, `draft_reminder`, `draft_terms_request`, `draft_cfo_memo` | Returns a simulation or a draft. Writes nothing to the outside world. Audited |
| EXECUTE | `send_reminder`, `send_terms_request`, `schedule_payment`, `submit_loan_application` | Creates a `proposed` Action (or a `denied` one) through the policy gate. It runs only after a human approves it through the authenticated API, and the gate is checked again at execution |

The agent has **no approve capability**. Approvals exist only as authenticated HTTP calls made by a person.

### Roles × capabilities

| Capability | Viewer | Accountant | Owner |
|---|---|---|---|
| Read dashboard, ledger, forecast, insights, audit, memo | ✓ | ✓ | ✓ |
| Chat with the assistant | READ tools only | READ + SUGGEST + reminders | all tools |
| What-if, financing comparison, write the CFO memo | — | ✓ | ✓ |
| Recategorize transactions, upload CSVs | — | ✓ | ✓ |
| Propose / approve payment reminders | — | ✓ | ✓ |
| Propose / approve payments, loan applications, supplier terms requests | — | — | ✓ |
| Reset the demo data | — | — | ✓ |

Every refused attempt (wrong role, other business, bad input) returns 403/404/422 and is written to
the audit log.

## Policy limits enforced by the gate

- **Payments**: the payee must be an existing counterparty with `is_allowed_payee`. The invoice must
  be one of that payee's open payables. The amount must be ≤ its outstanding balance, ≤ $5,000 per
  payment, and ≤ $10,000 per payment date (counting executed and approved payments). The date must be
  between today and +90 days. There is no field for a payee name, beneficiary or bank account: money
  can only go to stored counterparty details.
- **Emails**: reminders go out at most once per invoice per 7 days, and terms requests at most once
  per supplier per 7 days. They go only to the stored `contact_email`, with text from fixed templates
  over structured records. A draft older than the cooldown, or whose amount no longer matches the
  invoice, is refused.
- **Loans**: per-product caps, counted cumulatively.
- **Every denial** is an audited `denied` Action, never "pending approval".

## Threats, controls and evidence

| # | Threat | Main controls | Tested by | Status |
|---|---|---|---|---|
| T1 | Prompt injection through documents (invoice notes, descriptions) | Untrusted text reaches the model only as wrapped, cleaned data; closed EXECUTE schemas; the gate pays only stored details within outstanding; the engine never reads notes | A1: `test_gate.py`, `test_action_service.py`, `test_api.py`, `test_agent_a1.py` | Mitigated |
| T2 | Agent acts without consent | EXECUTE only proposes; no approve tool; claim check on "sent/paid/done" | `test_agent_tools.py`, `test_action_service.py`, `test_citations.py` | Mitigated |
| T16 | Bank-feed abuse (leaked keys, real bank, injected feed text) | Sandbox host hard-coded; keys in env only; access token never stored; feed rows take the CSV path (never mint counterparties); owner/accountant only, audited | A6: `test_plaid_feed.py` | Mitigated |
| T3 | Excessive or split payments | Single and daily caps, amount ≤ outstanding, integer cents only | A2: `test_gate.py`, `test_action_service.py` | Mitigated |
| T4 | Privilege escalation | RBAC on every route plus role checks in the gate; role re-read on every request | A3: `test_api.py`, `test_action_service.py`, `test_security_review.py` | Mitigated |
| T5 | Duplicate execution | Idempotency keys, row locks, UNIQUE `action_id` on sandbox rows, replay returns the original | A4: `test_action_service.py` | Mitigated |
| T6 | Audit log tampering | SHA-256 hash chain, ORM guard and DB trigger against UPDATE/DELETE, `/audit/verify`, head hash anchored in git by the evidence export | A5: `test_audit.py`, `test_evidence_export.py` | Mitigated (see residual risks) |
| T7 | Hallucinated numbers | Engine-only numbers; citation check on every money/percent figure; supplied inputs never count as evidence | `test_citations.py`, `test_agent_runner.py`, `test_forecast.py` | Mitigated for money and percentages |
| T8 | PII sent to the LLM | Regex masking of accounts, cards, IBANs, emails and phones in everything sent; contact emails never in tool results | `test_pii.py`, `test_agent_a1.py`, `test_llm_classifier.py` | Mitigated (regex-based) |
| T9 | Secret leakage | Env-only config; `.env` files gitignored; deploy copies only tracked files; production refuses dev defaults; full-history secret scan before publishing | `test_production.py`; gitleaks run by `scripts/ship.sh` | Mitigated |
| T10 | Chat abuse and cost | Per-user limits; one turn in flight per sign-in; caps on model calls and tokens per turn; time limits; daily AI budget; per-IP limits at the edge | `test_chat_api.py`, `test_llm_budget.py`, `test_agent_timeouts.py`, `test_production.py` | Mitigated |
| T11 | Malicious upload | ≤ 2 MB, CSV only, UTF-8, ≤ 20k rows, all-or-nothing, nothing evaluated | `test_csv_parser.py`, `test_api.py` | Mitigated |
| T12 | Stolen or forged session | bcrypt; pinned HS256 with a ≥ 32-char secret; 8 h tokens; login lockout (not for the public demo accounts in production) plus per-IP edge limits | `test_api.py`, `test_security_review.py`, `test_production.py` | Mitigated (demo-grade) |
| T13 | XSS, CSRF, UI injection | httpOnly + SameSite=Strict + Secure cookie; same-origin gateway with route allowlist and Origin check; no raw HTML or links in answers; drafts dropped on `reset` | `frontend/tests/security.test.ts`, `chat-reducer.test.ts`, `e2e/chat.spec.ts` | Mitigated |
| T14 | Exposed or misconfigured deployment | Only Caddy publishes 80/443; backend and DB on the internal network only; TLS + HSTS + `frame-ancestors 'none'`; API docs off; boot refuses default DB password, empty API key and non-HTTPS CORS; firewall; automatic security updates | `test_production.py`, `scripts/check_deploy.sh` | Mitigated |

## Known residual risks

We are stating these openly rather than hiding them.

1. **Demo-grade identity.** Seeded users with one published password; no MFA; no token revocation
   before the 8 h expiry. The login lockout is per email. On the public demo the three demo accounts
   are exempt from it (their password is public, so a lockout protects nothing and would let anyone
   lock out every visitor); per-IP rate limits at Caddy remain.
2. **Shared public accounts.** Anyone can approve or reject the planted actions. Every effect is
   sandbox-only and fictional, the daily AI budget caps spend, and the data resets every 3 hours on a deployed instance (locally: the owner's reset button or `seed.reset`; the
   audit log is kept and gains a `demo_reset` event). On the deployed demo, chat conversations and the
   one-turn lock are per sign-in, so visitors don't see or block each other's chats. They do share
   the per-user turn quota (10/min, 300/day for the owner account).
3. **Audit hash is unkeyed.** A DB owner able to drop the trigger can rewrite events and recompute
   every later hash, and `/audit/verify` still passes. The evidence anchor committed to git detects any
   rewrite or truncation *up to the anchored event*; events after the last export are protected only
   by the in-database chain.
4. **PII masking is regex-based** and misses some formats (dashed account numbers, lowercase or
   dashed IBANs, obfuscated emails, some phone layouts). It is a backstop: the agent never needs
   account details, and payments use stored counterparty details only.
5. **The citation check covers money and percentages only.** Bare numbers (days, weeks, quantities)
   are not verified, and the check matches figures, not the meaning of the sentence around them.
6. **The agent's free-text rationale** on a proposal is LLM output and may echo injected text. The
   approvals UI labels it as the assistant's own words and shows amount, payee and invoice from the
   stored records next to it.
7. **Counterparty names, invoice numbers and SKUs** reach the model and the email templates unwrapped.
   Today they come only from seed data. If invoice or counterparty upload is ever added, they become
   an injection path and must be wrapped and validated.
8. **Streamed chat text** is shown before the final checks finish. Our UI renders it only as a
   marked draft and replaces it with the checked answer; another client reading the raw stream would
   not get that protection.
9. **Budget overshoot.** The in-flight lock and conversations are per process (the API runs one
   worker on purpose). A model call already running when the daily budget is reached can overshoot it
   by that one call's cost.
10. **Heuristic outputs.** Categorization can mislabel (confidence threshold + human review), the
    forecast is based on historical behavior and is not a guarantee, and the financing catalog is
    simulated and labeled "not financial advice".
11. **`Policy.payee_allowlist_mode`** is stored but not read. The gate always behaves as `strict`,
    which is the safe setting.
12. **Single server.** No high availability. A nightly `pg_dump` is the only backup, and losing the
    server loses the unexported tail of the audit chain.

**Never reuse this setup with real data, real money or real integrations.**

## How to check it yourself

- `cd backend && pytest -q`: the whole suite, including A1–A6 (no network needed).
- `cd backend && python -m scripts.plaid_check`: the live Plaid sandbox feed, as a dry run.
- `GET /audit/verify` or the "Verify chain" button on `/audit`.
- `python -m app.sandbox.evidence_export --check-file evidence/<file>.jsonl --anchor evidence/anchor.json`
  recomputes the committed chain without a database (the committed export is from the local stack).
- `scripts/check_deploy.sh <domain> <ip>` checks TLS, headers, the cookie, the gateway and closed ports
  on a deployed instance (not used for the submission).
