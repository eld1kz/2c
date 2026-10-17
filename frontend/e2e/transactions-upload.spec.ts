import { expect, test } from "@playwright/test";

import { noSideScroll, signIn, watchConsole } from "./helpers";

// Writes are answered by recorded responses so the local demo data never changes; the backend rules
// for recategorizing and importing are covered by backend/tests/test_api_transactions.py and test_api.py.

test("transactions list real bank rows with chips and page on demand", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "viewer");
  await page.goto("/transactions");
  const rows = page.getByRole("list").last().getByRole("listitem");
  await expect(rows).toHaveCount(50);
  await page.getByRole("button", { name: "Show older transactions" }).click();
  await expect(rows).toHaveCount(100);
  await page.screenshot({ path: `e2e/.results/transactions-${info.project.name}.png` });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("accountant fixes a category from the review queue", async ({ page }) => {
  await signIn(page, "accountant");
  const queue = {
    rows: [{
      ref: "transaction:9001", id: 9001, date: "2026-09-09", amount_cents: -4_500, currency: "USD", category: null,
      category_source: null, needs_review: true, counterparty: null, invoice: null,
      description: { untrusted_text: "QUILLBOOK ACCOUNTING 0909", source: "bank statement description" },
    }],
    has_more: false,
  };
  let saved: unknown = null;
  await page.route("**/api/backend/transactions?needs_review=true**", (route) => route.fulfill({ json: queue }));
  await page.route("**/api/backend/transactions/9001/category", async (route) => {
    saved = route.request().postDataJSON();
    await route.fulfill({ json: { ...queue.rows[0], category: "software", category_source: "human", needs_review: false } });
  });
  await page.goto("/transactions?tab=review");
  await expect(page.getByRole("tab", { name: /Needs review \(1\)/ })).toHaveAttribute("aria-selected", "true");
  await page.getByLabel("Category for QUILLBOOK ACCOUNTING 0909").selectOption("software");
  await expect(page.getByText("Saved as Software.")).toBeVisible();
  expect(saved).toEqual({ category: "software" });
});

test("viewers see the review queue but can't change categories", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/transactions?tab=review");
  await expect(page.getByText("viewers can only look")).toBeVisible();
  await expect(page.getByRole("combobox")).toHaveCount(0);
});

test("import shows a preview first, then the result", async ({ page }, info) => {
  await signIn(page, "owner");
  await page.route("**/api/backend/upload", (route) =>
    route.fulfill({ json: { rows: 3, inserted: 2, skipped_duplicates: 1, linked: 1, by_rule: 1, by_llm: 0, needs_review: 1 } }),
  );
  await page.goto("/upload");
  await page.locator('input[type="file"]').setInputFiles({
    name: "october.csv",
    mimeType: "text/csv",
    buffer: Buffer.from('Date,Description,Amount\n2026-10-02,"POS SETTLEMENT 1002 CLOUDPOS",512.40\n2026-10-03,QUILLBOOK ACCOUNTING,-45.00\n2026-10-03,RENT OCT,-3200.00\n'),
  });
  await expect(page.getByText("Preview: first 3 of 3 rows")).toBeVisible();
  await expect(page.getByRole("cell", { name: "POS SETTLEMENT 1002 CLOUDPOS" })).toBeVisible();
  await page.screenshot({ path: `e2e/.results/upload-${info.project.name}.png` });
  await page.getByRole("button", { name: "Import 3 rows" }).click();
  await expect(page.getByRole("status")).toContainText("Imported 2 of 3 rows");
  await page.getByRole("link", { name: "Open the review queue" }).click();
  await expect(page.getByRole("tab", { name: /Needs review/ })).toHaveAttribute("aria-selected", "true");
});

test("the server's rejection of a bad file is shown and nothing is imported", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto("/upload");
  await page.locator('input[type="file"]').setInputFiles({ name: "notes.csv", mimeType: "text/csv", buffer: Buffer.from("hello,world\nnot,a statement\n") });
  await page.getByRole("button", { name: "Import 1 row", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Nothing was imported" })).toBeVisible();
});

test("viewers can't import", async ({ page }) => {
  const errors = watchConsole(page);
  await signIn(page, "viewer");
  await page.goto("/upload");
  await expect(page.getByText("can't import statements")).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  expect(errors).toEqual([]);
});
