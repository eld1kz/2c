import { expect, test, type Page } from "@playwright/test";

import { noSideScroll, signIn, watchConsole } from "./helpers";

// GET /team and /today are real; /afford is recorded (the backend side is tests/test_afford.py).
const AFFORD = {
  verdict: "no", earliest_safe_start: null, warnings: [],
  message: "No: your cash already falls below your $5,000.00 cushion in Week 6 (Nov 5) [[forecast_week:6]], before any new cost.",
  citations: [{ ref: "forecast_week:6", valid: true, label: "Week 6 (Nov 5)", reason: null }],
  scenarios: [{ type: "add_recurring", amount_cents: -5_000, cadence: "weekly", start: "2026-10-01" }],
  requested_start: "2026-10-01", short_from: "2026-11-05",
  with_fixes: {
    verdict: "yes", earliest_safe_start: "2026-10-01", short_from: null,
    fixes: [{ kind: "terms_request", name: "Verde Green Coffee Imports", insight_id: 2 }, { kind: "reminder", name: "Harbor Lane Café", insight_id: 3 }],
  },
};

async function recordAfford(page: Page): Promise<string[]> {
  const asked: string[] = [];
  await page.route("**/api/backend/afford", (route) => {
    asked.push((route.request().postDataJSON() as { question: string }).question);
    return route.fulfill({ json: AFFORD });
  });
  return asked;
}

test("the team, the Today line, and a raise opening Can I afford it with both verdicts", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  await expect(page.getByTestId("team-line")).toHaveText("Your team: 5 people, $4,343.55/week");
  await page.getByTestId("team-line").click();
  await expect(page).toHaveURL(/\/team$/);
  const asked = await recordAfford(page);
  const people = page.getByRole("list", { name: "Team" }).getByRole("listitem");
  await expect(people).toHaveCount(5);
  await expect(people.nth(3)).toContainText("Tom Lindqvist");
  await expect(people.nth(3)).toContainText("Barista");
  await expect(people.nth(3)).toContainText("$742.00/week");

  await people.nth(3).getByRole("button", { name: "Give a raise" }).click();
  await people.nth(3).getByRole("button", { name: "Can I afford it?" }).click();
  const box = page.getByRole("region", { name: "Can I afford it?" });
  await expect(box.getByRole("list", { name: "Verdicts" }).getByRole("listitem")).toHaveText([
    "Today: No — already short from Nov 5",
    "If Verde Green Coffee Imports agrees and Harbor Lane Café pays: Yes — from Oct 1",
  ]);
  expect(asked).toEqual(["Give Tom Lindqvist (Barista) a raise of $50.00/week from today?"]);
  await expect(box.getByRole("textbox")).toHaveValue(asked[0]);
  await page.screenshot({ path: `e2e/.results/team-${info.project.name}.png`, fullPage: true });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("+ Hire someone asks with the role and weekly pay", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto("/team");
  const asked = await recordAfford(page);
  const hire = page.getByRole("region", { name: "Hire someone" });
  await hire.getByLabel("Role").fill("Roaster");
  await hire.getByLabel("Weekly pay ($)").fill("820.5");
  await hire.getByRole("button", { name: "Can I afford it?" }).click();
  await expect(page.getByRole("region", { name: "Can I afford it?" }).getByTestId("afford-result")).toBeVisible();
  expect(asked).toEqual(["Hire a Roaster at $820.50/week from today?"]);
});

test("viewers see names and roles but no pay and no buttons", async ({ page }) => {
  await signIn(page, "viewer");
  await expect(page.getByTestId("team-line")).toHaveText("Your team: 5 people");
  await page.goto("/team");
  const team = page.getByRole("list", { name: "Team" });
  await expect(team.getByRole("listitem")).toHaveCount(5);
  await expect(team).toContainText("Maya Okafor");
  await expect(team).toContainText("Head roaster");
  await expect(page.locator("main")).not.toContainText("/week");
  await expect(page.getByRole("button", { name: /Give a raise|Can I afford it/ })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Hire someone" })).toHaveCount(0);
});

test("Team is under More", async ({ page }, info) => {
  await signIn(page, "owner");
  if (info.project.name === "phone") {
    await page.getByRole("navigation", { name: "Main" }).last().getByRole("button", { name: "More" }).click();
    await expect(page.getByRole("navigation", { name: "More" }).getByRole("link", { name: "Team" })).toBeVisible();
  } else {
    await expect(page.getByRole("navigation", { name: "Main" }).first().getByRole("link", { name: "Team" })).toBeVisible();
  }
});
