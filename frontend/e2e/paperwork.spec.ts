import { expect, test } from "@playwright/test";

import { noSideScroll, signIn, watchConsole } from "./helpers";

// Paperwork Center against the seeded demo (read-only; nothing here calls the model).

const DISCLAIMER = "Prepared from your records for review; not audited; not tax or legal advice.";

test("close my month: September reconciles and every report renders", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "viewer");
  await page.goto("/paperwork");
  await expect(page.getByRole("heading", { name: "Paperwork", level: 1 })).toBeVisible();
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  await expect(page.getByText("Cash basis", { exact: false }).first()).toBeVisible();
  for (const title of ["Bank reconciliation", "Cash-flow statement", "Profit and loss", "Money customers owe you", "Bills you owe"]) {
    await expect(page.getByRole("heading", { name: title, level: 2 })).toBeVisible();
  }
  await expect(page.getByText("It matches your books to the cent.")).toBeVisible();
  await expect(page.getByRole("table", { name: "Profit and loss" })).toContainText("Net profit (cash basis)");
  await expect(page.getByRole("list", { name: "Receivables" }).getByRole("button", { name: "INV-1042" })).toBeVisible();
  await page.screenshot({ path: `e2e/.results/paperwork-month-${info.project.name}.png`, fullPage: true });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("bank-ready pack: all sections, Not included, and a one-file PDF", async ({ page }, info) => {
  const errors = watchConsole(page);
  await signIn(page, "owner");
  await page.goto("/paperwork");
  await page.getByRole("link", { name: "Get bank-ready" }).click();
  await expect(page).toHaveURL(/tab=bank/);
  const pack = page.getByTestId("bank-pack");
  await expect(pack.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  for (const title of ["Profit and loss", "Cash-flow statement", "13-week cash forecast", "Fixed obligations", "Receivables aging", "Not included"]) {
    await expect(pack.getByRole("heading", { name: title, level: 2 })).toBeVisible();
  }
  await expect(page.getByRole("table", { name: "Profit and loss, by month" })).toContainText("September");
  await expect(page.getByRole("list", { name: "Fixed obligations" })).toContainText("$12,000.00");
  await expect(page.getByTestId("not-included")).toContainText("Balance sheet");
  await expect(page.getByTestId("not-included")).toContainText("Tax returns");
  await expect(page.getByTestId("not-included")).toContainText("Legal documents");
  await expect(page.getByRole("button", { name: "Download PDF" })).toBeVisible();
  await page.screenshot({ path: `e2e/.results/paperwork-bank-${info.project.name}.png`, fullPage: true });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);

  if (info.project.name === "desktop") {
    // Every printed sheet carries the review label in its footer (an @page margin box).
    const footers = await page.evaluate(() =>
      Array.from(document.styleSheets).flatMap((sheet) => Array.from(sheet.cssRules).map((r) => r.cssText)).filter((t) => t.startsWith("@page {")),
    );
    expect(footers.some((t) => t.includes("@bottom-center") && t.includes(DISCLAIMER))).toBe(true);
    await page.emulateMedia({ media: "print" });
    await expect(page.getByRole("button", { name: "Download PDF" })).toBeHidden();
    await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
    const pdf = await page.pdf({ format: "A4", preferCSSPageSize: true, path: "e2e/.results/bank-ready-pack.pdf" });
    expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
    expect(pdf.length).toBeGreaterThan(20_000);
  }
  expect(errors).toEqual([]);
});
