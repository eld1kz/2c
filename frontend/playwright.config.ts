import { defineConfig, devices } from "@playwright/test";

// Smoke tests against a running stack (backend :8000 with seeded data, `npm run dev` on :3000).
// E2E_CHANNEL=chromium uses Playwright's bundled Chromium where Google Chrome isn't installed (scripts/ship.sh on Windows).
const channel = process.env.E2E_CHANNEL === "chromium" ? undefined : "chrome";

export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e/.results",
  globalTimeout: 10 * 60_000, // a hung browser or worker ends the run instead of stalling it
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", channel },
  projects: [
    { name: "phone", use: { ...devices["iPhone 13"], defaultBrowserType: "chromium", channel } },
    { name: "desktop", use: { viewport: { width: 1280, height: 860 } } },
  ],
});
