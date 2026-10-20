import { expect, test } from "@playwright/test";

import { noSideScroll, refFor, signIn, watchConsole } from "./helpers";

// GET /today is real (read-only). Preparing and approving are recorded here so the local demo data
// never changes (a real reminder starts the 7-day cooldown); the backend side is tests/test_today.py.

const reminderAction = (invoice: string, customer: string, status: string, sandbox: object | null) => ({
  id: 77, proposed_by: "user", tool: "send_reminder", params: { invoice_id: Number(invoice.split(":")[1]), draft_id: 76 },
  tier: "EXECUTE", status, rationale: "Harbor Lane Café owes you $4,800.00 and is 45 days late on INV-1042.",
  evidence_ids: [invoice], idempotency_key: "today:1:76", decided_by: null, decided_at: null, result: null,
  display: {
    title: "Send a payment reminder to Harbor Lane Café", counterparty: { ref: customer, label: "Harbor Lane Café" },
    invoice: { ref: invoice, label: "INV-1042" }, amount_cents: 480_000, currency: "USD", invoice_outstanding_cents: 480_000,
    days_past_due: 45, scheduled_date: null, denied_reason: null, evidence: [{ ref: invoice, label: "INV-1042" }],
    email: { to_name: "Harbor Lane Café", subject: "Payment overdue: invoice INV-1042 ($4,800.00)", body: "Hello Harbor Lane Café," },
    sandbox,
  },
});

test("sign-in lands on Today: the chart, three decisions, afford, the team; nothing else", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Good (morning|afternoon|evening), Demo Owner\.$/);
  const decisions = page.getByRole("region", { name: "Decisions" }).getByRole("article");
  await expect(decisions).toHaveCount(3);
  await expect(decisions.nth(0)).toContainText("Verde Green Coffee Imports raised GRN-COL-HUILA by 18%");
  await expect(decisions.nth(0).getByRole("button", { name: "Review price email" })).toBeVisible();
  await expect(decisions.nth(1).getByRole("button", { name: "Ask Verde Green Coffee Imports for 30 more days" })).toBeVisible();
  await expect(decisions.nth(2)).toContainText("Harbor Lane Café owes you $4,800.00 and is 45 days late on INV-1042.");

  await expect(page.getByRole("heading", { name: "3 things to decide" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Your next 13 weeks" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Can I afford it?" })).toBeVisible();
  await expect(page.getByTestId("team-line")).toBeVisible();
  // safe to spend and last month's spending moved to Overview
  await expect(page.getByRole("heading", { name: /safe to spend/ })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /Where your money went/ })).toHaveCount(0);
  await expect(page.locator("main").getByRole("button", { name: /^What is this\?/ })).toHaveCount(4); // the key terms only

  await page.screenshot({ path: `e2e/.results/today-${info.project.name}.png`, fullPage: true });
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Nothing is safe to spend this week" })).toBeVisible();
  await expect(page.getByText("This week's bills would take you $5,292.54 below your cushion.")).toBeVisible();
  await page.getByRole("button", { name: /Nothing is safe to spend/ }).click();
  await expect(page.getByText("Your cushion (money you keep for surprises)")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Where your money went in September" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open the full profit and loss" })).toHaveAttribute("href", "/paperwork");
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("one tap prepares the reminder and opens it for approval", async ({ page }) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  const invoice = await refFor(page, "invoice", "INV-1042");
  const customer = await refFor(page, "counterparty", "Harbor Lane Café");
  const action = (status: string, sandbox: object | null) => reminderAction(invoice, customer, status, sandbox);
  let prepared = 0;
  await page.route("**/api/backend/today/decisions/*/prepare", (route) => {
    prepared += 1;
    return route.fulfill({ json: action("proposed", null) });
  });
  await page.route("**/api/backend/actions/77/approve", (route) =>
    route.fulfill({ json: action("executed", { kind: "email", id: 9, status: "sent", summary: "Sandbox email #9 sent to Harbor Lane Café", subject: "x", at: "2026-10-01T09:00:00Z" }) }),
  );
  await page.goto("/today");
  await page.getByRole("button", { name: "Review reminder" }).click();
  const sheet = page.getByRole("dialog", { name: "Ready for your approval" });
  await expect(sheet).toContainText("Nothing is sent until you approve it.");
  const card = sheet.getByRole("article", { name: "Send a payment reminder to Harbor Lane Café" });
  await card.getByRole("button", { name: "Approve and send" }).click();
  await expect(card.getByTestId("sandbox-result")).toContainText("Sandbox email #9 sent to Harbor Lane Café");
  expect(prepared).toBe(1);
  await page.keyboard.press("Escape");
  const sent = page.getByRole("article", { name: /Harbor Lane Café owes you/ }).getByTestId("sent-mark");
  await expect(sent).toHaveText("Sent"); // shown once the sheet closes, with the one-time check animation
  await expect(sent).toHaveAttribute("data-fresh", "true");
  expect(errors).toEqual([]);
});

test("viewer sees the decisions but no buttons", async ({ page }) => {
  await signIn(page, "viewer");
  const decisions = page.getByRole("region", { name: "Decisions" }).getByRole("article");
  await expect(decisions).toHaveCount(3);
  await expect(decisions.getByRole("button", { name: /^(Review|Ask .* for 30 more days)/ })).toHaveCount(0);
  await expect(decisions.first()).toContainText("The owner or accountant decides this.");
});

test("navigation is Today, Ask, Approvals, Team and a grouped More", async ({ page }, info) => {
  await signIn(page, "owner");
  const groups = { Money: ["Overview", "Findings", "What-if", "Paperwork"], Records: ["Transactions", "Import"], Safety: ["Audit log", "Trust"] };
  let nav;
  if (info.project.name === "phone") {
    const bar = page.getByRole("navigation", { name: "Main" }).last();
    await expect(bar.getByRole("link")).toHaveText(["Today", "Ask", "Approvals", "Team"]);
    await bar.getByRole("button", { name: "More", exact: true }).click();
    nav = page.getByRole("navigation", { name: "More" });
  } else {
    nav = page.getByRole("navigation", { name: "Main" }).first();
    await expect(nav.getByRole("link").first()).toHaveText("Today");
    await expect(nav.getByText("More", { exact: true })).toBeVisible();
  }
  for (const [group, labels] of Object.entries(groups)) {
    await expect(nav.getByRole("group", { name: group }).getByRole("link")).toHaveText(labels);
  }
});

test("can I afford it: a chip asks, both engine verdicts (today, with Today's fixes), a cited sentence and the chart", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  let asked = "";
  await page.route("**/api/backend/afford", async (route) => {
    asked = (route.request().postDataJSON() as { question: string }).question;
    return route.fulfill({
      json: {
        verdict: "no", earliest_safe_start: null, warnings: [],
        message: "No: your cash already falls below your $5,000.00 cushion in Week 6 (Nov 5) [[forecast_week:6]], before any new cost.",
        citations: [{ ref: "forecast_week:6", valid: true, label: "Week 6 (Nov 5)", reason: null }],
        scenarios: [{ type: "add_recurring", amount_cents: -250_000, cadence: "monthly", start: "2026-11-01" }],
        requested_start: "2026-11-01", short_from: "2026-11-05",
        with_fixes: {
          verdict: "not_yet", earliest_safe_start: "2026-12-06", short_from: null,
          fixes: [{ kind: "terms_request", name: "Verde Green Coffee Imports", insight_id: 2 }, { kind: "reminder", name: "Harbor Lane Café", insight_id: 3 }],
        },
      },
    });
  });
  const box = page.getByRole("region", { name: "Can I afford it?" });
  await expect(box.getByRole("textbox", { name: "Can I afford it?" })).toHaveAttribute("placeholder", "Hire a barista at $2,500/month from November?");
  await box.getByRole("button", { name: "Hire a barista at $2,500/month from November?" }).click();
  const result = box.getByTestId("afford-result");
  // advice, not a gate: risk levels, what happens if you go ahead anyway, and how to make it work
  await expect(result.getByRole("list", { name: "Verdicts" }).getByRole("listitem")).toHaveText(["Today: Risky — already short from Nov 5"]);
  await expect(result.getByRole("region", { name: "If you go ahead anyway" }).getByTestId("go-ahead"))
    .toHaveText(/^Lowest point: Nov 26, \$[\d,]+\.\d\d below your cushion\.$/); // the engine's what-if (POST /whatif)
  const howTo = result.getByRole("region", { name: "How to make it work" });
  await expect(howTo.getByRole("list", { name: "With today's fixes" }).getByRole("listitem"))
    .toHaveText(["If Verde Green Coffee Imports agrees and Harbor Lane Café pays: Tight — safe from Dec 6"]);
  await expect(howTo.getByRole("link", { name: "Compare ways to cover the gap" })).toHaveAttribute("href", /\/what-if\?s=.*add_recurring.*&view=financing$/);
  await expect(result).toContainText("This is advice. You decide.");
  await expect(result.getByText(/^(No|Not yet|Yes)$/)).toHaveCount(0); // no hard verdict badges
  await expect(result).toContainText("falls below your $5,000.00 cushion");
  await expect(result.getByRole("button", { name: "Week 6 (Nov 5)" })).toBeVisible();
  await expect(result.getByRole("region", { name: "What-if result" })).toBeVisible();
  expect(asked).toBe("Hire a barista at $2,500/month from November?");
  await expect(box.getByRole("textbox")).toHaveValue(asked);
  await page.screenshot({ path: `e2e/.results/afford-${info.project.name}.png`, fullPage: true });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("viewers get no afford box", async ({ page }) => {
  await signIn(page, "viewer");
  await expect(page.getByRole("region", { name: "Decisions" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Can I afford it?" })).toHaveCount(0);
});

test("watch your future fix itself: the chart, the ghost line, and the curve lifting after an approval", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  const invoice = await refFor(page, "invoice", "INV-1042");
  const customer = await refFor(page, "counterparty", "Harbor Lane Café");
  let approved = false;
  // the real GET /today; after the (recorded) approval, the response is what the engine returns once both fixes are sent
  await page.route("**/api/backend/today", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    if (approved) {
      const f = body.future;
      body.future = {
        ...f, applied: f.pending, pending: [], pending_headline: null,
        headline: "Cash stays above your cushion for all 13 weeks.", detail: "Lowest week: Nov 26, $1,920.01 above your cushion.",
        weeks: f.weeks.map((w: { pending_closing_cents: number }) => ({ ...w, closing_cents: w.pending_closing_cents, pending_closing_cents: null, below_cushion: false })),
      };
    }
    return route.fulfill({ response, json: body });
  });
  await page.route("**/api/backend/today/decisions/*/prepare", (route) => route.fulfill({ json: reminderAction(invoice, customer, "proposed", null) }));
  await page.route("**/api/backend/actions/77/approve", (route) => {
    approved = true;
    return route.fulfill({ json: reminderAction(invoice, customer, "executed", { kind: "email", id: 9, status: "sent", summary: "Sandbox email #9 sent to Harbor Lane Café", subject: "x", at: "2026-10-01T09:00:00Z" }) });
  });
  await page.goto("/today");

  const chart = page.getByRole("region", { name: "Your next 13 weeks" });
  const headline = chart.getByTestId("future-headline");
  await expect(headline).toHaveText("Cash stays above your cushion until Nov 5.");
  const bars = chart.getByTestId("future-bar");
  await expect(bars).toHaveCount(13);
  await expect(chart.locator('[data-testid="future-bar"][data-below="true"]')).toHaveCount(7); // weeks 6–10, 12, 13
  await expect(chart.getByTestId("future-ghost")).toHaveCount(1);
  await expect(chart).toContainText("Pending fixes (Verde Green Coffee Imports agrees, Harbor Lane Café pays): Cash stays above your cushion for all 13 weeks.");
  expect(await bars.first().evaluate((el) => getComputedStyle(el).transitionDuration)).toBe("0.7s");
  await page.screenshot({ path: `e2e/.results/future-before-${info.project.name}.png`, fullPage: true });

  await page.getByRole("button", { name: "Review reminder" }).click();
  const sheet = page.getByRole("dialog", { name: "Ready for your approval" });
  const refetched = page.waitForResponse((r) => r.url().endsWith("/api/backend/today") && approved);
  await sheet.getByRole("button", { name: "Approve and send" }).click();
  await refetched;
  await expect(headline).toHaveText("Cash stays above your cushion until Nov 5."); // held while the sheet is open
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(headline).toHaveText("Cash stays above your cushion for all 13 weeks.");
  await expect(chart.locator('[data-testid="future-bar"][data-below="true"]')).toHaveCount(0);
  await expect(chart.getByTestId("future-ghost")).toHaveCount(0);
  await expect(chart).toContainText("Includes the fixes you approved: Verde Green Coffee Imports agrees, Harbor Lane Café pays.");
  await page.screenshot({ path: `e2e/.results/future-after-${info.project.name}.png`, fullPage: true });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("the chart doesn't animate with reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await signIn(page, "viewer");
  const bar = page.getByRole("region", { name: "Your next 13 weeks" }).getByTestId("future-bar").first();
  const seconds = await bar.evaluate((el) => parseFloat(getComputedStyle(el).transitionDuration));
  expect(seconds).toBeLessThan(0.001); // motion-reduce (and the global reduced-motion rule) turn it off
});
