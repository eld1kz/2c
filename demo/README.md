# Demo video

A 2-minute walkthrough of every screen, recorded from `storyboard.yml` with
[shot-scraper video](https://shot-scraper.datasette.io/en/stable/video.html).

## Record

Needs the local stack (db, backend :8000, frontend :3000), `shot-scraper` >= 1.10 and `ffmpeg`:

```bash
uv tool install shot-scraper && shot-scraper install
winget install --id Gyan.FFmpeg -e
demo/record.sh
```

`record.sh` resets the demo data to the golden state (`seed.reset`, audit log kept), records, and
resets again at the end, so the browser tests still find the golden state. It writes
`demo/out/ledgerwise-demo.webm` and `.mp4` (git-ignored, about 2 minutes). The chat scene makes one
real model call (needs `ANTHROPIC_API_KEY`); the Import scene syncs the Plaid sandbox feed (needs
`PLAID_CLIENT_ID` and `PLAID_SECRET`). A missing key fails that scene.
**Plaid sync changes the demo data — run Reset demo data afterwards.** `record.sh` already resets at the end; after a manual sync, press "Reset demo data"
(or `cd backend && python -m seed.reset`) before recording or running the browser tests.
Extra arguments go to `shot-scraper video`, e.g. `demo/record.sh --timeout 180000`.

## Edit

Each scene is a list of `click` / `wait_for` / `scroll` / `pause` steps with Playwright locators
(the same ones `frontend/e2e` uses). Change pacing with `pause` and scroll `duration`.

## Exploring with Playwright MCP

`.mcp.json` is git-ignored (the launcher differs per OS). To use Playwright MCP, create it locally
with `npx -y @playwright/mcp@0.0.83 --browser chromium --caps devtools --output-dir demo/out/mcp`
(on Windows wrap the command in `cmd /c`). `--caps devtools` adds `browser_start_video`,
`browser_video_chapter` (title cards) and `browser_video_show_actions` (cursor and action callouts).
Use it to find selectors or record a one-off clip interactively; videos land in `demo/out/mcp/`.
