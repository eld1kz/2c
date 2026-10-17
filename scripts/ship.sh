#!/usr/bin/env bash
# The only way to commit (CLAUDE.md, Git): runs every check, and commits + pushes only if all pass.
# Usage: scripts/ship.sh "phase N: <summary>"
# Needs the dev stack running for the browser tests: backend on :8000 (seeded DB), `npm run dev` on :3000.
set -euo pipefail

msg=${1:?usage: scripts/ship.sh "phase N: <summary>"}
ROOT=$(git rev-parse --show-toplevel)
LOG=$(mktemp -t ship.XXXXXX)
trap 'rm -f "$LOG"' EXIT
fail() { echo "SHIP STOPPED: $1" >&2; exit 1; }
run() { # run <label> <cmd...>: quiet on success, prints the log tail on failure
  local label=$1; shift
  if "$@" >"$LOG" 2>&1; then echo "ok  $label: $(tail -n 1 "$LOG")"; else tail -n 30 "$LOG" >&2; fail "$label failed"; fi
}

command -v gitleaks >/dev/null || fail "gitleaks not installed (brew install gitleaks): it scans every commit for secrets"
curl -sf -o /dev/null http://localhost:8000/health || fail "backend not running on :8000"
curl -sf -o /dev/null http://localhost:3000/login || fail "frontend not running on :3000 (npm run dev)"

cd "$ROOT/backend"
# shellcheck disable=SC1091
source .venv/bin/activate
run "backend tests" pytest -q
cd "$ROOT/frontend"
run "typecheck" npx tsc --noEmit
run "lint" npm run lint --silent
run "unit tests" npm test --silent
run "browser tests" npx playwright test

cd "$ROOT"
git add -A
if git diff --cached --name-only | grep -E '(^|/)\.env($|\.local)|\.venv/|node_modules/|e2e/\.results'; then fail "secret or artifact staged"; fi
git diff --cached --quiet && fail "nothing to commit"
gitleaks git --pre-commit --staged --redact --no-banner "$ROOT" >"$LOG" 2>&1 || { cat "$LOG" >&2; fail "gitleaks: secret in staged changes"; }
git commit -q -m "$msg"
if git ls-files | grep -E '(^|/)\.env$|\.env\.local|\.venv/'; then fail "secret tracked (commit made, not pushed)"; fi
owner=$(git log --reverse --format='%an <%ae>' | head -n 1)
authors=$(git log --format='%an <%ae>' | sort -u)
[[ "$authors" == "$owner" ]] || fail "unexpected author(s) (commit made, not pushed): $authors"
if git log --format=%B | grep -qi "co-authored-by"; then fail "Co-Authored-By in history (commit made, not pushed)"; fi
gitleaks git --redact --no-banner "$ROOT" >"$LOG" 2>&1 || { cat "$LOG" >&2; fail "gitleaks: secret in git history (commit made, not pushed)"; }
git push -q origin main
git log --oneline -1
