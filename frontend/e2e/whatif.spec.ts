import { expect, test } from "@playwright/test";

import { noSideScroll, refFor, signIn, sse, watchConsole } from "./helpers";

// What-if against the real engine (POST /whatif writes nothing, so the demo data is never changed).
// Figures are the golden demo state (seed.reset, no-LLM categorization).

test("cash-gap card → what-if: before/after, with the scenario shown as an assumption", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  await page.goto("/dashboard");
  const card = page.getByRole("article").filter({ hasText: "Cash falls below" });
  await card.getByRole("link", { name: "What if Harbor Lane Café pays INV-1042?" }).click();

  await expect(page).toHaveURL(/\/what-if\?s=/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("What if Harbor Lane Café pays INV-1042?");
  const assumption = page.getByRole("region", { name: "Assumption, not a recorded fact" });
  await expect(assumption).toContainText("Harbor Lane Café pays INV-1042 in full: $4,800.00");
  await expect(assumption).toContainText("Nothing in your books was changed");
  const summary = page.getByTestId("whatif-summary");
  await expect(summary).toContainText("Today's forecast$7,181.99 short of your cushion"); // today's gap
  await expect(summary).toContainText("If the assumption holds$2,381.99 short of your cushion"); // the gap left if it is paid
  await expect(page.getByRole("region", { name: "Closing cash by week, before and after" }).locator(".recharts-bar-rectangle").first()).toBeVisible();
  await page.screenshot({ path: `e2e/.results/whatif-${info.project.name}.png`, fullPage: true });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);

  await page.getByRole("button", { name: "Table" }).click();
  const week6 = page.getByRole("row").filter({ hasText: "W6" });
  await expect(week6).toContainText("−$1,997.67");
  await expect(week6).toContainText("$2,802.33");
  await expect(week6).toContainText("+$4,800.00");

  // One click from the result to the financing ranking for the gap that is left.
  await page.getByRole("button", { name: "Compare financing for the $2,381.99 left" }).click();
  const financing = page.getByRole("region", { name: "Ways to cover the gap left after this scenario" });
  const options = financing.getByRole("listitem").filter({ has: page.getByRole("heading") });
  await expect(options.first()).toHaveAccessibleName("Option 1: Ask suppliers for +30 days on payment terms");
  await expect(options.first()).toContainText("$0.00");
  await expect(options.first()).toContainText("Covers the whole $2,381.99");
  await expect(options.first()).toContainText("Verde Green Coffee Imports");
  await expect(options.first()).toContainText("covers it alone");
  await expect(options.nth(1)).toHaveAccessibleName("Option 2: Sandbox bank overdraft (18% APR)");
  await expect(options.nth(1)).toContainText("$41.11");
  await expect(financing).toContainText("Not financial advice.");
  await financing.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `e2e/.results/financing-${info.project.name}.png`, fullPage: true });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);

  await page.getByRole("button", { name: "Today's gap" }).click();
  const base = page.getByRole("region", { name: "Ways to cover today's gap" });
  await expect(base.getByRole("listitem").filter({ has: page.getByRole("heading") }).first()).toHaveAccessibleName(
    "Option 1: Sandbox bank overdraft (18% APR)",
  );
  await expect(base).toContainText("Not enough alone");
  expect(errors).toEqual([]);
});

test("the overview opens the financing comparison for today's gap", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto("/dashboard");
  await page.getByRole("link", { name: "Compare financing" }).click();
  const base = page.getByRole("region", { name: "Ways to cover today's gap" });
  await expect(base).toContainText("$7,181.99");
  await expect(base.getByRole("link", { name: "Ask the CFO to prepare this" })).toHaveAttribute("href", /cheapest/);
});

test("viewers see no what-if shortcut and the page explains why", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/dashboard");
  const inv = await refFor(page, "invoice", "INV-1042");
  await expect(page.getByRole("article").filter({ hasText: "Cash falls below" })).toBeVisible();
  await expect(page.getByRole("link", { name: /^What if/ })).toHaveCount(0);
  await page.goto(`/what-if?s=${encodeURIComponent(JSON.stringify([{ type: "collect_receivable", invoice_id: Number(inv.split(":")[1]) }]))}`);
  await expect(page.getByRole("alert").filter({ hasText: "Simulations need an owner or accountant" })).toBeVisible();
});

test("a what-if in the chat renders as a before/after chart from the engine", async ({ page }) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  const inv = await refFor(page, "invoice", "INV-1042");
  const scenarios = [{ type: "collect_receivable", invoice_id: Number(inv.split(":")[1]) }];
  await page.route("**/api/backend/chat", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: sse([
        ["turn", { conversation_id: "00000000-0000-4000-8000-000000000002", turn: 1 }],
        ["tool", { name: "run_what_if", tier: "SUGGEST", ok: true, scenarios }],
        ["done", { message: "If INV-1042 is paid now, week 6 stays positive [[whatif:1]].", citations: [{ ref: "whatif:1", valid: true, label: "What-if 1", reason: null }], warnings: [], action_ids: [], iterations: 2 }],
      ]),
    }),
  );
  await page.goto("/chat");
  await page.getByLabel("Ask the CFO").fill("What if Harbor Lane pays?");
  await page.getByRole("button", { name: "Send" }).click();
  const panel = page.getByRole("region", { name: "What-if result" });
  await expect(panel).toContainText("What if Harbor Lane Café pays INV-1042?");
  await expect(panel).toContainText("$2,381.99");
  await panel.getByRole("link", { name: "Open the what-if" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("What if Harbor Lane Café pays INV-1042?");
  expect(errors).toEqual([]);
});
