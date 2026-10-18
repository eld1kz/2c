import { expect, test, type Page } from "@playwright/test";

import { signIn, watchConsole } from "./helpers";

// P1 end to end with the real assistant (spends AI budget). Starts from the golden state (run
// `python -m seed.reset` first if needed) and ends by pressing "Reset demo data", so it can be repeated.
// Run with LIVE=1, desktop only.
test.skip(!process.env.LIVE, "set LIVE=1 to call the real assistant");

const shot = (page: Page, name: string) => page.screenshot({ path: `e2e/.results/p1-${name}.png`, fullPage: true });

async function ask(page: Page, question: string) {
  const turns = page.getByRole("article");
  const before = await turns.count();
  await page.getByLabel("Ask the CFO").fill(question);
  await page.getByRole("button", { name: "Send" }).click();
  const turn = turns.nth(before);
  await expect(turn.getByTestId("answer").or(turn.getByRole("alert"))).toBeVisible({ timeout: 150_000 });
  await expect(turn.getByTestId("answer")).toBeVisible();
  return turn;
}

test("live P1: late-payer insight → chat → draft → approve → sandbox email → audit verify", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one live run is enough");
  test.setTimeout(420_000);
  const errors = watchConsole(page);
  await signIn(page, "owner");
  await page.goto("/dashboard");

  // 1. the insight
  const insight = page.getByRole("article").filter({ hasText: "INV-1042 is 45 days overdue" });
  await expect(insight).toBeVisible();
  await shot(page, "1-dashboard");
  await insight.getByRole("link", { name: "Ask the CFO" }).click();

  // 2. chat: the assistant explains, drafts the reminder and proposes sending it
  await expect(page.getByLabel("Ask the CFO")).toHaveValue(/INV-1042/);
  let turn = await ask(page, await page.getByLabel("Ask the CFO").inputValue());
  const proposed = page.getByRole("link", { name: /Proposed a reminder: waiting for approval/ });
  if (!(await proposed.count())) {
    turn = await ask(page, "Please draft a firm but polite reminder for INV-1042 and propose sending it for my approval.");
  }
  await expect(proposed.first()).toBeVisible();
  await expect(turn.getByTestId("answer").getByRole("button").first()).toBeVisible(); // cites records
  await shot(page, "2-chat");

  // 3. approve in the inbox
  await proposed.first().click();
  const card = page.getByRole("article", { name: "Send a payment reminder to Harbor Lane Café" });
  await expect(card).toContainText("$4,800.00");
  await card.getByRole("button", { name: /INV-1042/ }).last().click(); // open the email draft
  await shot(page, "3-approval");
  await card.getByRole("button", { name: "Approve and send" }).click();
  await expect(card.getByTestId("sandbox-result")).toContainText(/Sandbox email #\d+ sent to Harbor Lane Café/);
  await shot(page, "4-sent");

  // 4. the audit log records it and the chain verifies
  await card.getByRole("link", { name: "See it in the audit log" }).click();
  await expect(page.getByText("Action carried out in the sandbox").first()).toBeVisible();
  await page.getByRole("button", { name: "Verify chain" }).click();
  await expect(page.getByRole("region", { name: "Tamper check" }).getByRole("status")).toContainText("Chain intact.");
  await shot(page, "5-audit");

  // 5. reset with the owner's button: back to the golden state, audit log kept and still verifying
  await page.getByRole("button", { name: "Reset demo data" }).first().click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reset demo data" }).click();
  await expect(page).toHaveURL(/\/today$/);
  await page.goto("/approvals");
  await expect(page.getByRole("tab", { name: "Waiting (0)" })).toBeVisible();
  await page.getByRole("tab", { name: "Decided" }).click();
  await expect(page.getByText("No decisions yet.")).toBeVisible();
  await page.goto("/audit");
  await expect(page.getByText("Demo data reset").first()).toBeVisible();
  await page.getByRole("button", { name: "Verify chain" }).click();
  await expect(page.getByRole("region", { name: "Tamper check" }).getByRole("status")).toContainText("Chain intact.");
  await shot(page, "6-reset");
  expect(errors).toEqual([]);
});
