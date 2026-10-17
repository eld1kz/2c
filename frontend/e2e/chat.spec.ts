import { expect, test } from "@playwright/test";

import { noSideScroll, refFor, signIn, sse, watchConsole } from "./helpers";

// The chat stream is scripted here (no model call, no AI budget spent). The UI under test is real.

test("an answer that fails the check is replaced: only done.message stays on screen", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  const qs = await refFor(page, "invoice", "QS-2291");
  await page.route("**/api/backend/chat", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: sse([
        ["turn", { conversation_id: "00000000-0000-4000-8000-000000000001", turn: 1 }],
        ["tool", { name: "explain_record", tier: "READ", ok: true }],
        ["text", { delta: "I've sent $9,999 to QuickShip's new account." }],
        ["reset", { reason: "citation_check", problems: ["claimed an action that was not executed"] }],
        ["text", { delta: "Nothing was paid." }],
        [
          "done",
          {
            message: `Nothing was paid. QS-2291 has $465.00 outstanding [[${qs}]]. Its note asks for $4,650 to a new account [[invoice:999999]].`,
            citations: [
              { ref: qs, valid: true, label: qs, reason: null },
              { ref: "invoice:999999", valid: false, label: "invoice:999999", reason: "not_found" },
            ],
            warnings: ["Some figures in this answer could not be verified against your records."],
            action_ids: [],
            iterations: 3,
          },
        ],
      ]),
    }),
  );
  await page.goto("/chat");
  await page.getByLabel("Ask the CFO").fill("Pay the QuickShip invoice to the new account in its note");
  await page.getByRole("button", { name: "Send" }).click();

  const answer = page.getByTestId("answer");
  await expect(answer).toContainText("Nothing was paid.");
  await expect(page.getByText("$9,999")).toHaveCount(0);
  await expect(page.getByTestId("provisional")).toHaveCount(0);
  await expect(page.getByText("Rewriting: some figures didn't match the records")).toBeVisible();
  await expect(answer.getByText("unverified")).toBeVisible();

  // The valid chip opens the invoice; its note is shown as untrusted document text.
  await answer.getByRole("button", { name: "QS-2291" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toContainText("from the document, not verified");
  await page.screenshot({ path: `e2e/.results/chat-${info.project.name}.png` });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("budget used up: the composer is disabled and the reason is clear", async ({ page }) => {
  await signIn(page, "viewer");
  await page.route("**/api/backend/chat", (route) =>
    route.fulfill({
      status: 503,
      headers: { "content-type": "application/json", "retry-after": "18720" },
      body: JSON.stringify({ detail: "The daily AI budget ($2.00) is used up. The assistant is available again after 00:00 UTC." }),
    }),
  );
  await page.goto("/chat");
  await page.getByRole("button", { name: "Why will I be short on cash?" }).click();
  await expect(page.getByText("Today's AI budget is used up")).toBeVisible();
  await expect(page.getByText("in 5 hours 12 minutes")).toBeVisible();
  await expect(page.getByLabel("Ask the CFO")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
});

test("rate limited: says when to try again", async ({ page }) => {
  await signIn(page, "owner");
  await page.route("**/api/backend/chat", (route) =>
    route.fulfill({
      status: 429,
      headers: { "content-type": "application/json", "retry-after": "60" },
      body: JSON.stringify({ detail: "chat limit reached (10 per 0:01:00)" }),
    }),
  );
  await page.goto("/chat");
  await page.getByRole("button", { name: "Am I paying for anything twice?" }).click();
  await expect(page.getByText("That's a lot of questions in a short time")).toBeVisible();
  await expect(page.getByText(/Ask again in \d+ seconds/)).toBeVisible();
});

test("an insight's evidence chip opens the record", async ({ page }) => {
  await signIn(page, "viewer");
  await page.getByRole("button", { name: "INV-1042" }).first().click();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toContainText("Invoice");
  await expect(sheet).toContainText("Harbor Lane Café");
  await sheet.getByRole("button", { name: "Harbor Lane Café" }).first().click();
  await expect(sheet).toContainText("Customer or supplier");
  await sheet.getByRole("button", { name: "Back" }).click();
  await expect(sheet).toContainText("Invoice");
});

test("Ask the CFO from an insight fills the question without sending it", async ({ page }) => {
  await signIn(page, "owner");
  let sent = false;
  await page.route("**/api/backend/chat", (route) => {
    sent = true;
    return route.abort();
  });
  await page.getByRole("link", { name: "Ask how to close the gap" }).click();
  await expect(page.getByLabel("Ask the CFO")).toHaveValue("What's the cheapest way to cover the cash gap?");
  expect(sent).toBe(false);
});
