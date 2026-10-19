# Ledgerwise frontend

Next.js (App Router, TypeScript), Tailwind, shadcn/ui and Recharts. Setup, configuration and the
full test commands are in the [root README](../README.md#run-it-locally).

```bash
printf 'BACKEND_URL=http://127.0.0.1:8000\nDEMO_PASSWORD=emberoak-demo\n' > .env.local
npm install
npm run dev            # http://localhost:3000, needs the backend on :8000
```

## Layout

```
app/(app)/       signed-in screens: today, chat (Ask), approvals, dashboard (Overview), insights,
                 what-if, memo, paperwork, team, transactions, upload (Import), audit, trust
app/login/       sign-in, with one-click demo accounts when DEMO_PASSWORD is set
app/api/auth/    login/logout route handlers: set and clear the httpOnly session cookie
app/api/backend/ same-origin gateway: attaches the token server-side, allows only the method + path
                 pairs in lib/backend-routes.ts, refuses cross-origin writes
components/      one folder per screen, plus shell/ (navigation) and ui/ (shadcn)
lib/             API client (lib/api, generated types: npm run gen:api), money, labels, chat stream
tests/           Vitest unit tests (gateway allowlist, chat reducer, glossary, ...)
e2e/             Playwright browser tests against the running stack (phone + desktop)
```

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | Dev server on :3000 |
| `npx tsc --noEmit && npm run lint && npm test` | Types, lint, unit tests (run `npx next typegen` once first) |
| `npx playwright test` | Browser tests; needs the stack running in the golden state (`python -m seed.reset`) |
| `npm run gen:api` | Regenerate `lib/api/schema.d.ts` from the backend's OpenAPI |

`AGENTS.md` is written by `next dev` for coding agents; leave it as is.
