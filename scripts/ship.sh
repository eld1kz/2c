#!/usr/bin/env bash
# The only way to commit (CLAUDE.md, Git): runs every check, and commits + pushes only if all pass.
# Usage: scripts/ship.sh "phase N: <summary>"
# Needs the dev stack running for the browser tests: backend on :8000 (seeded DB), `npm run dev` on :3000.
set -euo pipefail

E2E_ARGS=()

msg=${1:?usage: scripts/ship.sh "phase N: <summary>"}
ROOT=$(git rev-parse --show-toplevel)
LOG=$(mktemp -t ship.XXXXXX)
trap 'rm -f "$LOG"' EXIT
fail() { echo "SHIP STOPPED: $1" >&2; exit 1; }
run() { # run <label> <cmd...>: quiet on success, prints the log tail on failure
  local label=$1; shift
  if "$@" >"$LOG" 2>&1; then echo "ok  $label: $(tail -n 1 "$LOG")"; else tail -n 30 "$LOG" >&2; fail "$label failed"; fi
}

# Windows (Git Bash): winget's gitleaks may not be on this shell's PATH yet; the venv has Scripts/, not bin/;
# without Google Chrome the browser tests use Playwright's bundled Chromium; browser tests run on one worker.
if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]]; then
  export PYTHONUTF8=1
  for d in "${LOCALAPPDATA:-}"/Microsoft/WinGet/Packages/Gitleaks.Gitleaks_*; do
    if [[ -x "$d/gitleaks.exe" ]]; then PATH="$PATH:$d"; fi
  done
  if [[ ! -x "/c/Program Files/Google/Chrome/Application/chrome.exe" ]]; then export E2E_CHANNEL=chromium; fi
  E2E_ARGS=(--workers=1)  # parallel specs share one demo database and race on slower Windows machines
fi
command -v gitleaks >/dev/null || fail "gitleaks not installed (brew install gitleaks / winget install Gitleaks.Gitleaks): it scans every commit for secrets"
branch=$(git rev-parse --abbrev-ref HEAD)
[[ "$branch" != HEAD ]] || fail "detached HEAD: check out a branch first"
curl -sf -o /dev/null http://localhost:8000/health || fail "backend not running on :8000"
curl -sf -o /dev/null http://localhost:3000/login || fail "frontend not running on :3000 (npm run dev)"

cd "$ROOT/backend"
# shellcheck disable=SC1091
if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; else source .venv/Scripts/activate; fi
run "backend tests" pytest -q
cd "$ROOT/frontend"
run "typecheck" npx tsc --noEmit
run "lint" npm run lint --silent
run "unit tests" npm test --silent
run "browser tests" npx playwright test ${E2E_ARGS[@]+"${E2E_ARGS[@]}"}

cd "$ROOT"
git add -A
if git diff --cached --name-only | grep -E '(^|/)\.env($|\.local)|\.venv/|node_modules/|e2e/\.results'; then fail "secret or artifact staged"; fi
git diff --cached --quiet && fail "nothing to commit"
gitleaks git --pre-commit --staged --redact --no-banner "$ROOT" >"$LOG" 2>&1 || { cat "$LOG" >&2; fail "gitleaks: secret in staged changes"; }
git commit -q -m "$msg"
if git ls-files | grep -E '(^|/)\.env$|\.env\.local|\.venv/'; then fail "secret tracked (commit made, not pushed)"; fi
# The project's owners: the first commit's author plus the second team machine's identity.
owners=$(printf '%s
' "$(git log --reverse --format='%an <%ae>' | head -n 1)" "hacksutates <hacksutates@gmail.com>")
unexpected=$(git log --format='%an <%ae>' | sort -u | grep -vxF "$owners" || true)
[[ -z "$unexpected" ]] || fail "unexpected author(s) (commit made, not pushed): $unexpected"
if git log --format=%B | grep -qi "co-authored-by"; then fail "Co-Authored-By in history (commit made, not pushed)"; fi
gitleaks git --redact --no-banner "$ROOT" >"$LOG" 2>&1 || { cat "$LOG" >&2; fail "gitleaks: secret in git history (commit made, not pushed)"; }
git push -q -u origin "$branch"
git log --oneline -1
