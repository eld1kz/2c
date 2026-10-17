import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "emberoak-demo";

/** Fails the test on any console error or uncaught exception. */
function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => msg.type() === "error" && errors.push(msg.text()));
  page.on("pageerror", (err) => errors.push(err.message));
  return errors;
}

async function signIn(page: Page, role: "owner" | "accountant" | "viewer") {
  await page.goto("/login");
  await page.getByLabel("Email").fill(`${role}@emberoak.demo`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}

test("signed-out visitors are sent to sign in", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard/);
});

test("dashboard shows cash, both dips and top insights", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("goes negative in weeks 6, 9 and 10");
  await expect(page.getByText("$8,650.00")).toBeVisible();
  await expect(page.getByText("−$2,181.99").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "What needs attention" })).toBeVisible();
  await page.screenshot({ path: `e2e/.results/dashboard-${info.project.name}.png`, fullPage: true });

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByRole("button", { name: /^W6/ }).click();
  await expect(page.getByRole("dialog")).toContainText("Crestline Equipment Finance");
  await page.screenshot({ path: `e2e/.results/week6-${info.project.name}.png` });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page scrolls sideways").toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});
