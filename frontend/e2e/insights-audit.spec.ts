import { expect, test } from "@playwright/test";

import { noSideScroll, signIn, watchConsole } from "./helpers";

test("insights list every finding with its impact, filterable by priority", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "viewer");
  await page.goto("/insights");
  const cards = page.getByRole("article");
  await expect(cards).toHaveCount(4);
  await expect(page.getByText("$9,198.00")).toBeVisible();
  await page.getByRole("button", { name: /^Low priority/ }).click();
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText("Designly");
  await expect(cards.first().getByRole("link", { name: "Ask the CFO" })).toBeVisible();
  await page.screenshot({ path: `e2e/.results/insights-${info.project.name}.png`, fullPage: true });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("verify chain reports an intact chain from the real backend", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "accountant");
  await page.goto("/audit");
  await expect(page.getByText("Signed in").first()).toBeVisible();
  await page.getByRole("button", { name: "Verify chain" }).click();
  await expect(page.getByRole("region", { name: "Tamper check" }).getByRole("status")).toContainText("Chain intact.");
  await page.getByRole("button", { name: /Signed in/ }).first().click();
  await expect(page.getByText("Previous").first()).toBeVisible();
  await page.screenshot({ path: `e2e/.results/audit-${info.project.name}.png` });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("a broken chain is reported with the event where it breaks", async ({ page }) => {
  await signIn(page, "owner");
  await page.route("**/api/backend/audit/verify", (route) =>
    route.fulfill({ json: { ok: false, checked: 57, broken_at_seq: 42, reason: "hash mismatch" } }),
  );
  await page.goto("/audit");
  await page.getByRole("button", { name: "Verify chain" }).click();
  const panel = page.getByRole("region", { name: "Tamper check" });
  await expect(panel.getByRole("alert")).toContainText("Chain broken at event #42.");
  await expect(panel.getByRole("alert")).toContainText("hash mismatch");
});

test("phones reach the audit log through More", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the More menu is phone-only");
  await signIn(page, "owner");
  await page.getByRole("button", { name: "More" }).click();
  await page.getByRole("dialog").getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
});
