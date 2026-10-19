#!/usr/bin/env bash
# Record the demo video: reset demo data to the golden state, then play demo/storyboard.yml.
# Needs the local stack running (db, backend :8000, frontend :3000), shot-scraper >= 1.10 and ffmpeg.
# Writes demo/out/ledgerwise-demo.webm and .mp4. The chat scene makes one real model call, and the
# Import scene syncs the Plaid sandbox feed (needs PLAID_* keys).
# The data is reset to the golden state before and after recording.
set -euo pipefail
cd "$(dirname "$0")/.."

# winget's ffmpeg isn't on PATH in shells opened before it was installed.
if ! command -v ffmpeg >/dev/null; then
  ff=$(ls -d "$LOCALAPPDATA"/Microsoft/WinGet/Packages/Gyan.FFmpeg_*/ffmpeg-*/bin 2>/dev/null | head -1 || true)
  [ -n "$ff" ] && export PATH="$ff:$PATH"
fi

py="$PWD/backend/.venv/Scripts/python.exe"
[ -x "$py" ] || py="$PWD/backend/.venv/bin/python"
reset() { (cd backend && "$py" -m seed.reset); }
reset
trap reset EXIT   # leave the golden state behind: the browser tests in scripts/ship.sh expect it

mkdir -p demo/out
shot-scraper video demo/storyboard.yml --mp4 --timeout 180000 "$@"
