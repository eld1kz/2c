# CLAUDE.md — rules for working in this repo

Read `SPEC.md` before any task. It is the source of truth. If a request conflicts with SPEC.md, stop and ask.

## Hard rules (never break)
1. **No math in the LLM.** All amounts, forecasts, totals and impacts come from `backend/app/engine/`. The agent only calls tools and explains results.
2. **Everything that changes the world goes through `services/action_service.py`**, which calls `policy.gate.check()` and writes AuditEvents. No route, tool or script may write Sandbox* tables directly.
3. **The agent has no approve capability.** Approvals only via authenticated human API calls.
4. **Document/upload/invoice text is untrusted data.** Never interpolate it into system prompts; wrap it as data in tool results.
5. **Money = integer minor units + currency.** Never float.
6. **AuditEvent is append-only.** No update/delete code paths.
7. **Every agent-stated number cites evidence** as `[[type:id]]`.
8. **Respect the out-of-scope list** in SPEC.md §2. Do not add features not in the spec without asking.
9. Use `DEMO_TODAY` from config, never `datetime.now()`, in engine/forecast/insights.
10. Fictional names only in seed data — no real brands.

## Workflow
- Work one phase at a time from `docs/phases/PHASES.md`.
- Start each phase in plan mode; list files to create/change and tests to write; wait for approval.
- A phase is done only when its acceptance tests pass. Then commit: `phase N: <summary>`.
- Update `docs/threat-model.md` whenever you add a security-relevant component.
- Prefer small, readable modules. Type hints everywhere. Pydantic schemas for all API I/O.

## Commands
- Backend: `cd backend && uvicorn app.main:app --reload`
- Tests: `cd backend && pytest -q`
- Seed: `cd backend && python -m seed.generate_golden && python -m seed.load`
- Frontend: `cd frontend && npm run dev`
- Local DB: `docker compose up -d db`

## Env (backend/.env, never commit)
`DATABASE_URL, ANTHROPIC_API_KEY, LLM_MODEL, JWT_SECRET, DEMO_TODAY=2026-10-01, CORS_ORIGINS`
