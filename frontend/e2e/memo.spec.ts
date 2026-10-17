import { expect, test } from "@playwright/test";

import { noSideScroll, signIn, watchConsole } from "./helpers";

// Writing a memo calls the assistant, so POST /memo is recorded here (no AI budget spent). GET /memo
// is real in the first test: this week's demo state has no memo yet.

const MEMO = {
  message:
    "## Cash today\nCash in the bank is $8,650.00 [[account:1]].\n\n## The cash gap\nWeek 9 (Nov 26) closes at −$2,181.99 [[forecast_week:9]].",
  citations: [
    { ref: "account:1", valid: true, label: "Operating checking", reason: null },
    { ref: "forecast_week:9", valid: true, label: "Week 9 (Nov 26)", reason: null },
  ],
  warnings: [],
  as_of: "2026-10-01",
  generated_at: "2026-10-18T09:00:00Z",
  generated_by: "Demo Owner",
};

test("owner writes the memo once; it renders with evidence chips", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  let posts = 0;
  await page.route("**/api/backend/memo", (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    posts += 1;
    return route.fulfill({ json: { memo: MEMO, stale: false } });
  });
  await page.goto("/memo");
  await expect(page.getByText("No memo for this week yet.")).toBeVisible();
  await page.getByRole("button", { name: "Write this week's memo" }).click();
  const memo = page.getByRole("article", { name: "CFO memo" });
  await expect(memo.getByRole("heading", { name: "Cash today" })).toBeVisible();
  await expect(memo.getByRole("button", { name: "Operating checking" })).toBeVisible();
  await expect(memo).toContainText("Saved, so reading it again costs nothing");
  await expect(page.getByRole("button", { name: "Write it again" })).toBeVisible();
  expect(posts).toBe(1);
  await page.screenshot({ path: `e2e/.results/memo-${info.project.name}.png`, fullPage: true });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("viewers read a stale memo with a notice and cannot rewrite it", async ({ page }) => {
  await signIn(page, "viewer");
  await page.route("**/api/backend/memo", (route) => route.fulfill({ json: { memo: MEMO, stale: true } }));
  await page.goto("/memo");
  await expect(page.getByRole("alert").filter({ hasText: "Your numbers have changed since this memo was written." })).toBeVisible();
  await expect(page.getByRole("article", { name: "CFO memo" })).toContainText("Cash in the bank is $8,650.00");
  await expect(page.getByRole("button", { name: /Write/ })).toHaveCount(0);
});

test("an unverified memo is shown once with a warning and not presented as saved", async ({ page }) => {
  await signIn(page, "owner");
  await page.route("**/api/backend/memo", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          json: {
            memo: { ...MEMO, generated_at: null, generated_by: null, warnings: ["Some figures in this answer could not be verified against your records."], citations: [{ ...MEMO.citations[0], valid: false }] },
            stale: false,
          },
        })
      : route.fulfill({ json: { memo: null, stale: false } }),
  );
  await page.goto("/memo");
  await page.getByRole("button", { name: "Write this week's memo" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "so it wasn't saved" })).toBeVisible();
  await expect(page.getByRole("article", { name: "CFO memo" })).not.toContainText("Saved, so reading it again");
});
