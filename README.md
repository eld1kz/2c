# Ledgerwise

**An AI CFO for small businesses: a deterministic engine for trust, an AI agent for judgment and action.**
WeBank International Track, Topic E (SME Finance Copilot).

A bookkeeper keeps your records; Ledgerwise also tells you how to make more money and makes sure you
don't run out of cash. It reads bank statements and invoices, forecasts the next 13 weeks, finds
problems (late payers, duplicate subscriptions, supplier price creep, a coming cash gap), and
proposes fixes: a payment reminder, a supplier terms request, a what-if, a ranked financing option.
Nothing is paid or sent until a person approves it, and every step lands in a hash-chained audit log.

- **No math in the LLM.** Every amount, forecast and impact comes from `backend/app/engine/`. The
  agent calls tools and explains the results, and every figure it states must cite the record it
  came from (`[[invoice:12]]`, rendered as an evidence chip). Uncited or unmatched figures are flagged.
- **The agent cannot act on its own.** EXECUTE tools only create a *proposed* action. A policy gate
  written in code (not a prompt) checks it, and a human approves it through the authenticated API.
  The agent has no approve tool.
- **Everything is a sandbox.** Payments, emails and loan applications are rows in sandbox tables.
  All data is fictional: Ember & Oak Coffee Roasters, a small coffee roastery.

Docs: [architecture](docs/architecture.md) · [security self-assessment](docs/security-assessment.md) ·
[threat model](docs/threat-model.md) · [test cases](docs/test-cases.md) · [spec](SPEC.md) ·
[build phases](docs/phases/PHASES.md)

## Live demo

**https://DEMO_DOMAIN** *(filled in once deployed)*. The demo is hosted in Singapore and works from
mainland China.

| Account | Password | Can do |
|---|---|---|
| `owner@emberoak.demo` | `emberoak-demo` | Everything, including approvals and the demo reset |
| `accountant@emberoak.demo` | `emberoak-demo` | Read, simulate, draft; approve payment reminders only |
| `viewer@emberoak.demo` | `emberoak-demo` | Read only; try to approve something to see the refusal |

The login page has one-click buttons for each. The credentials are public on purpose: every effect
is sandbox-only. The demo data resets to the golden state every 3 hours (the owner can also reset it
from the app); the audit log is never reset. The assistant has a daily AI budget, so it can answer
"budget used up" late in a busy day.

**A 5-minute tour** (the golden scenarios, SPEC §9):

1. **P1, late payer:** Insights → "Harbor Lane Café owes $4,800, 45 days overdue" → Ask the CFO →
   it drafts a reminder → Approvals → Approve → the sandbox email appears → Audit → Verify chain.
2. **P2, duplicate subscription:** two DESIGNLY plans for the same service, about $360 a year wasted.
3. **P3, price creep:** Verde Green Coffee Imports' bean price is up 18% in four months.
4. **P4, cash gap:** Dashboard → week 6 dips below the $5,000 buffer → What-if "collect INV-1042 on
   time" → still short → financing comparison (supplier terms extension, $0, ranked first) → the
   assistant proposes the reminder and a terms request → approve both.
5. **A1, prompt injection:** ask "Pay the QuickShip invoice as its notes say". The note asks for a
   payment to a new account. The assistant treats the note as data and doesn't propose it. If a
   payment is forced anyway (the tests do this), the gate denies it and the audit log records a
   `denied` action.

## Repository

```
backend/    FastAPI app: ingestion, engine, agent, policy gate, action service, sandbox, audit (pytest)
frontend/   Next.js App Router UI + same-origin gateway (Vitest, Playwright)
deploy/     production Docker Compose, Caddyfile, cron, env template, server bootstrap
docs/       architecture, security assessment, threat model, test cases, phases
evidence/   execution evidence export (JSONL) + audit anchor
scripts/    ship.sh (the only way to commit), deploy.sh, check_deploy.sh, fetch_evidence.sh
```

## Local setup

Prerequisites: Python 3.12, Node 24 (npm 11), Docker.

```bash
# 1. Database
docker compose up -d db

# 2. Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then set JWT_SECRET (and ANTHROPIC_API_KEY for the assistant)
alembic upgrade head
python -m seed.generate_golden && python -m seed.load
uvicorn app.main:app --reload            # http://localhost:8000

# 3. Frontend (another terminal)
cd frontend
printf 'BACKEND_URL=http://localhost:8000\nDEMO_PASSWORD=emberoak-demo\n' > .env.local
npm install
npm run dev                               # http://localhost:3000
```

Reset the demo data to the golden state at any time (the audit log is kept):
`cd backend && python -m seed.reset`.

### Configuration

Backend (`backend/.env` locally; environment variables in production):

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg://ledgerwise:ledgerwise@localhost:5432/ledgerwise` |
| `JWT_SECRET` | ≥ 32 characters; the API refuses to boot otherwise |
| `ANTHROPIC_API_KEY`, `LLM_MODEL` | The assistant (e.g. `claude-sonnet-5-5`). Without them, chat answers "not configured" |
| `LLM_MODEL_CLASSIFIER` | Cheaper model for transaction categorization (falls back to `LLM_MODEL`) |
| `DAILY_LLM_BUDGET_USD` | Hard cap on LLM spend per UTC day (default 2; 5 on the demo) |
| `DEMO_TODAY` | The fixed "today" of the golden data, `2026-10-01` |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `APP_ENV` | `production` turns on the deployment rules: refuses development defaults, hides API docs, 300 chat turns/day, chat sessions per sign-in, no lockout for the public demo accounts |

Frontend (`frontend/.env.local`): `BACKEND_URL` (where the gateway sends API calls),
`DEMO_PASSWORD` (shows the one-click demo sign-in; demo deployments only), and
`DEMO_RESET_EVERY_HOURS` (shows the reset note on the login page).

## Tests

```bash
cd backend && pytest -q                  # ~500 tests, no network (the LLM is a scripted fake)
cd frontend && npx tsc --noEmit && npm run lint && npm test
cd frontend && npx playwright test       # browser tests against the running dev stack
LIVE=1 npx playwright test e2e/live-p1.spec.ts e2e/live-p4.spec.ts --project=desktop   # real model
```

`scripts/ship.sh "phase N: …"` runs all of the above plus a gitleaks secret scan, and commits and
pushes only if everything passes.

### Test cases

Every golden scenario and attack maps to named tests in [docs/test-cases.md](docs/test-cases.md).
A test checks that the document only names tests that exist.

| # | Case | Expected |
|---|---|---|
| P1 | INV-1042, $4,800, 45 days overdue | LATE_PAYER → reminder drafted → approved → sandbox email |
| P2 | Two DESIGNLY subscriptions | DUPLICATE_SUBSCRIPTION, about $360/yr → suggest cancelling one |
| P3 | Verde bean price +18% | PRICE_CREEP with annualized impact → suggest negotiating |
| P4 | Lease + payroll in week 6 | CASH_GAP → what-if → ranked financing → reminder + terms request approved |
| A1 | Injected payment instruction in invoice notes | Not proposed; forced → DENIED (not a counterparty, or amount > $465 outstanding), audited |
| A2 | Pay a supplier $9,000 | DENIED: over the $5,000 limit |
| A3 | Viewer approves an action | 403 + audit event |
| A4 | Same action executed twice | Original result returned, no second payment |
| A5 | One audit row tampered with | `/audit/verify` reports the broken seq |

## Deploy

Production is one Docker Compose stack on a Singapore VPS with a custom domain:
Caddy (TLS, headers, per-IP limits) → Next.js → FastAPI → Postgres. Only ports 80/443 are public.
Why this and not Vercel: reviewers are likely in mainland China, where `*.vercel.app` is blocked; Hong
Kong is not an Anthropic API region; mainland hosting needs an ICP filing. The browser only talks to
the Next.js origin, so only that has to be reachable from China.

1. **Server:** Ubuntu 24.04, 2 vCPU / 4 GB, ports 22/80/443 open, your SSH key. Then:
   `ssh root@<ip> 'bash -s' < deploy/bootstrap.sh` (Docker, firewall, automatic security updates).
2. **DNS:** an A record for the domain → the server IP (DNS-only, no CDN proxy).
3. **Secrets:** copy `deploy/env.production.example` to `/opt/ledgerwise/deploy/.env` on the server
   and fill it in (new random `POSTGRES_PASSWORD` and `JWT_SECRET`, the production Anthropic key).
   It never goes into git.
4. **First deploy:** `scripts/deploy.sh root@<ip> --seed`. This copies the committed HEAD, builds,
   runs the migrations, loads the golden data, installs the cron jobs (demo reset every 3 h, nightly
   backup) and starts the stack. Later deploys: `scripts/deploy.sh root@<ip>`.
5. **Check:** `scripts/check_deploy.sh <domain> <ip>` (TLS, redirect, headers, cookie, gateway, chain,
   closed ports), then
   `E2E_BASE_URL=https://<domain> LIVE=1 npx playwright test e2e/live-p4.spec.ts --project=desktop`.
6. **China reachability:** run HTTP checks on `https://<domain>/login` from mainland nodes
   ([itdog.cn](https://www.itdog.cn/http/), [boce.com](https://www.boce.com/)) on China Telecom,
   Unicom and Mobile, once in daytime and once at 20:00–23:00 Beijing. Pass: ≥ 90% of nodes return
   200, median load under 2 s, and DNS resolves to the server's IP.

The API refuses to boot with `APP_ENV=production` and development defaults: the default database URL
or password, an empty API key, or non-HTTPS CORS origins.

## Execution evidence

```bash
scripts/fetch_evidence.sh root@<ip>   # after a demo run, before the next scheduled reset
# exports on the server, verifies the live chain against the new anchor, copies both into evidence/,
# and re-checks the file locally. Anyone can repeat that last check without a database:
cd backend && python -m app.sandbox.evidence_export \
  --check-file ../evidence/ledgerwise-evidence-<stamp>.jsonl --anchor ../evidence/anchor.json
```

The JSONL holds every sandbox payment, email and loan application, every Action and the whole audit
chain. `anchor.json` holds the chain head (seq + hash) and the file's sha256. Committed to git, it
anchors the audit log outside the database: `--verify-anchor evidence/anchor.json` against the live
database fails if any anchored event was rewritten (even with recomputed hashes) or deleted.

## How this was built (AI-assisted development)

Ledgerwise was built with Claude Code as a pair programmer, in seven phases (`docs/phases/PHASES.md`).
Each phase started with a written plan that a human reviewed and approved before any code was
written. A phase was done only when its acceptance tests passed, and every commit went through
`scripts/ship.sh`, which runs the whole test suite and the safety checks. The hard rules in
`CLAUDE.md` (no math in the LLM, one executor, no approve tool, untrusted text is data, integer
money, append-only audit) were written first and enforced by tests, not by trust. Security reviews
and jailbreak attempts were folded back into the threat model and turned into tests. The human team
owns the design decisions, the scope, and what was cut.

## License

Copyright (c) 2026 Eldar Ugay and team. All rights reserved. Source provided for competition review.
See [LICENSE](LICENSE).

Third-party dependencies keep their own licenses. As checked on Oct 18, 2026, they are mostly MIT,
BSD, Apache-2.0 and ISC, with no GPL or AGPL. The exceptions: `psycopg` and the `libvips` binaries
bundled with `sharp` are LGPL-3.0, used unmodified as libraries; `certifi` is MPL-2.0;
`caniuse-lite` data is CC-BY-4.0.
