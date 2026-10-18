import { expect, test, type Page } from "@playwright/test";

import { signIn, watchConsole } from "./helpers";

// P4 end to end with the real assistant (spends AI budget). Starts from the golden state (run
// `python -m seed.reset` first if needed) and ends by pressing "Reset demo data", so it can be repeated.
// Run with LIVE=1, desktop only.
test.skip(!process.env.LIVE, "set LIVE=1 to call the real assistant");

const shot = (page: Page, name: string) => page.screenshot({ path: `e2e/.results/p4-${name}.png`, fullPage: true });

const REMINDER = /Proposed a reminder: waiting for approval/;
const TERMS = /Proposed a terms request: waiting for approval/;
const FOLLOW_UP =
  "Please draft a firm but polite reminder for INV-1042 and a request to Verde Green Coffee Imports for 30 more days on payment terms, and propose sending both for my approval.";

async function ask(page: Page, question: string) {
  const turns = page.getByRole("article");
  const before = await turns.count();
  await page.getByLabel("Ask the CFO").fill(question);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const turn = turns.nth(before);
  await expect(turn.getByTestId("answer").or(turn.getByRole("alert"))).toBeVisible({ timeout: 150_000 });
  await expect(turn.getByTestId("answer")).toBeVisible();
  return turn;
}

test("live P4: cash gap → what-if → leftover financing → reminder + terms request → approve both → audit", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one live run is enough");
  test.setTimeout(480_000);
  const errors = watchConsole(page);
  await signIn(page, "owner");
  await page.goto("/dashboard");

  // 1. the cash-gap card → what-if
  const gapCard = page.getByRole("article").filter({ hasText: "Cash falls below" });
  await expect(gapCard).toBeVisible();
  await shot(page, "1-dashboard");
  await gapCard.getByRole("link", { name: "What if Harbor Lane Café pays INV-1042?" }).click();
  await expect(page.getByRole("region", { name: "Assumption, not a recorded fact" })).toContainText("$4,800.00");
  await expect(page.getByTestId("whatif-summary")).toContainText("If the assumption holds$2,381.99 short of the buffer");
  await shot(page, "2-whatif");

  // 2. one click to the financing ranking for the gap that is left
  await page.getByRole("button", { name: "Compare financing for the $2,381.99 left" }).click();
  const financing = page.getByRole("region", { name: "Ways to cover the gap left after this scenario" });
  const options = financing.getByRole("listitem").filter({ has: page.getByRole("heading") });
  await expect(options.first()).toHaveAccessibleName("Option 1: Ask suppliers for +30 days on payment terms");
  await expect(options.first()).toContainText("$0.00");
  await expect(options.first()).toContainText("covers it alone");
  await expect(options.nth(1)).toHaveAccessibleName("Option 2: Sandbox bank overdraft (18% APR)");
  await expect(financing).toContainText("Not financial advice.");
  await financing.scrollIntoViewIfNeeded();
  await shot(page, "3-financing");

  // 3. chat: the assistant proposes the Harbor Lane reminder and the Verde terms request
  await financing.getByRole("link", { name: "Ask the CFO to prepare this" }).click();
  await expect(page.getByLabel("Ask the CFO")).toHaveValue(/Harbor Lane Café pays INV-1042.*reminder/);
  let turn = await ask(page, await page.getByLabel("Ask the CFO").inputValue());
  if (!(await page.getByRole("link", { name: REMINDER }).count()) || !(await page.getByRole("link", { name: TERMS }).count())) {
    turn = await ask(page, FOLLOW_UP);
  }
  await expect(page.getByRole("link", { name: REMINDER }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: TERMS }).first()).toBeVisible();
  await expect(turn.getByTestId("answer").getByRole("button").first()).toBeVisible(); // cites records
  await expect(turn.getByTestId("answer")).not.toContainText(/yourself|manually/i);
  await shot(page, "4-chat");

  // 4. approve both in the inbox → two sandbox emails
  await page.getByRole("link", { name: TERMS }).first().click();
  const reminder = page.getByRole("article", { name: "Send a payment reminder to Harbor Lane Café" });
  const terms = page.getByRole("article", { name: /^Ask Verde Green Coffee Imports for \+\d+ days on payment terms$/ });
  await expect(reminder).toContainText("$4,800.00");
  await expect(terms).toContainText("The supplier's stored contact");
  await terms.getByRole("button", { name: /Request to extend payment terms/ }).click(); // open the email draft
  await expect(terms).toContainText("starting with invoices issued from");
  await shot(page, "5-approvals");
  await reminder.getByRole("button", { name: "Approve and send" }).click();
  await expect(reminder.getByTestId("sandbox-result")).toContainText(/Sandbox email #\d+ sent to Harbor Lane Café/);
  await terms.getByRole("button", { name: "Approve and send" }).click();
  await expect(terms.getByTestId("sandbox-result")).toContainText(/Sandbox email #\d+ sent to Verde Green Coffee Imports/);
  await shot(page, "6-sent");

  // 5. the audit log records both and the chain verifies
  await terms.getByRole("link", { name: "See it in the audit log" }).click();
  await expect(page.getByText("Action carried out in the sandbox").nth(1)).toBeVisible();
  await page.getByRole("button", { name: "Verify chain" }).click();
  await expect(page.getByRole("region", { name: "Tamper check" }).getByRole("status")).toContainText("Chain intact.");
  await shot(page, "7-audit");

  // 6. reset: back to the golden state, audit log kept and still verifying
  await page.getByRole("button", { name: "Reset demo data" }).first().click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reset demo data" }).click();
  await expect(page).toHaveURL(/\/today$/);
  await page.goto("/approvals");
  await expect(page.getByRole("tab", { name: "Waiting (0)" })).toBeVisible();
  await page.goto("/audit");
  await expect(page.getByText("Demo data reset").first()).toBeVisible();
  await page.getByRole("button", { name: "Verify chain" }).click();
  await expect(page.getByRole("region", { name: "Tamper check" }).getByRole("status")).toContainText("Chain intact.");
  await shot(page, "8-reset");
  expect(errors).toEqual([]);
});
