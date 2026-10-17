import { expect, test, type Page } from "@playwright/test";

import { noSideScroll, refFor, signIn, watchConsole } from "./helpers";

// The inbox talks to a recorded /actions API here so the local demo data is never changed
// (approving INV-1042's reminder for real would start the 7-day reminder cooldown).
// The backend side of approve/reject is covered by backend/tests/test_api_approvals.py.

async function reminder(page: Page, status: string, sandbox: object | null = null) {
  const invoice = await refFor(page, "invoice", "INV-1042");
  const customer = await refFor(page, "counterparty", "Harbor Lane Café");
  return {
    id: 41, proposed_by: "agent", tool: "send_reminder", params: { invoice_id: Number(invoice.split(":")[1]), draft_id: 40 },
    tier: "EXECUTE", status, rationale: "INV-1042 is 45 days overdue and Harbor Lane usually pays 28 days late.",
    evidence_ids: [invoice], idempotency_key: "conv:abc:send_reminder", decided_by: null, decided_at: null, result: null,
    display: {
      title: "Send a payment reminder to Harbor Lane Café", counterparty: { ref: customer, label: "Harbor Lane Café" },
      invoice: { ref: invoice, label: "INV-1042" }, amount_cents: 480_000, currency: "USD", invoice_outstanding_cents: 480_000,
      days_past_due: 45, scheduled_date: null, denied_reason: null, evidence: [{ ref: invoice, label: "INV-1042" }],
      email: { to_name: "Harbor Lane Café", subject: "Payment overdue: INV-1042 ($4,800.00)", body: "Hello,\n\nINV-1042 for $4,800.00 was due on Aug 17." },
      sandbox,
    },
  };
}

test("owner approves a reminder and sees the sandbox email", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  const waiting = await reminder(page, "proposed");
  const done = await reminder(page, "executed", {
    kind: "email", id: 7, status: "sent", summary: "Sandbox email #7 sent to Harbor Lane Café",
    subject: "Payment overdue: INV-1042 ($4,800.00)", at: "2026-10-17T06:00:00Z",
  });
  let approved = false;
  await page.route("**/api/backend/actions**", (route) => {
    const url = route.request().url();
    if (url.endsWith("/41/approve")) {
      approved = true;
      return route.fulfill({ json: done });
    }
    if (url.includes("status=proposed")) return route.fulfill({ json: approved ? [] : [waiting] });
    return route.fulfill({ json: approved ? [done] : [waiting] });
  });
  await page.goto("/approvals");
  const card = page.getByRole("article", { name: "Send a payment reminder to Harbor Lane Café" });
  await expect(card).toContainText("$4,800.00");
  await expect(card).toContainText("45 days overdue");
  await expect(card).toContainText("may quote documents");
  await card.getByRole("button", { name: /Payment overdue: INV-1042/ }).click();
  await expect(card).toContainText("was due on Aug 17");
  await page.screenshot({ path: `e2e/.results/approval-${info.project.name}.png`, fullPage: true });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);

  await card.getByRole("button", { name: "Approve and send" }).click();
  await expect(card.getByTestId("sandbox-result")).toContainText("Sandbox email #7 sent to Harbor Lane Café");
  await expect(card.getByRole("button", { name: "Approve and send" })).toHaveCount(0);
  await page.screenshot({ path: `e2e/.results/approved-${info.project.name}.png`, fullPage: true });
  expect(errors).toEqual([]);
});

test("viewer sees Approve, the server refuses, and the card says so", async ({ page }) => {
  await signIn(page, "viewer");
  const waiting = await reminder(page, "proposed");
  await page.route("**/api/backend/actions**", (route) =>
    route.request().url().endsWith("/41/approve")
      ? route.fulfill({ status: 403, json: { detail: "role viewer may not approve send_reminder" } })
      : route.fulfill({ json: [waiting] }),
  );
  await page.goto("/approvals");
  const card = page.getByRole("article", { name: "Send a payment reminder to Harbor Lane Café" });
  await card.getByRole("button", { name: "Approve and send" }).click();
  await expect(card.getByRole("alert")).toHaveText("Viewers can't approve; this attempt was logged.");
});

test("a payment refused by policy shows the reason in Decided", async ({ page }) => {
  await signIn(page, "owner");
  const denied = {
    ...(await reminder(page, "denied")), id: 42, tool: "schedule_payment", rationale: "",
    display: {
      title: "Pay QuickShip Logistics", counterparty: null, invoice: null, amount_cents: 465_000, currency: "USD",
      invoice_outstanding_cents: 46_500, days_past_due: null, scheduled_date: "2026-10-08", email: null, sandbox: null,
      denied_reason: "amount exceeds the invoice's outstanding balance", evidence: [],
    },
  };
  await page.route("**/api/backend/actions**", (route) => route.fulfill({ json: [denied] }));
  await page.goto("/approvals");
  await page.getByRole("tab", { name: "Decided" }).click();
  const card = page.getByRole("article", { name: "Pay QuickShip Logistics" });
  await expect(card).toContainText("Refused by policy");
  await expect(card).toContainText("amount exceeds the invoice's outstanding balance");
  await expect(card.getByRole("button", { name: "Approve payment" })).toHaveCount(0);
});

test("the real inbox loads against the backend", async ({ page }) => {
  const errors = watchConsole(page);
  await signIn(page, "accountant");
  await page.goto("/approvals");
  await expect(page.getByRole("tab", { name: /Waiting/ })).toBeVisible();
  expect(errors).toEqual([]);
});
