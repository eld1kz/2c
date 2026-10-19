import { expect, test } from "@playwright/test";

import { noSideScroll, signIn } from "./helpers";

// "What is this?" popovers on Today, Team, What-if and Paperwork (definitions: lib/glossary.ts).
test("financial terms explain themselves in plain English", async ({ page }, info) => {
  await signIn(page, "owner");
  const open = async (name: string, expected: string) => {
    await page.getByRole("button", { name: `What is this? ${name}` }).first().click();
    const pop = page.getByRole("dialog").filter({ hasText: name });
    await expect(pop).toContainText(expected);
    expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
    await page.keyboard.press("Escape");
    await expect(pop).toBeHidden();
  };
  await open("Cushion", "The minimum cash you want to keep in the bank for surprises.");
  if (info.project.name === "phone") await page.screenshot({ path: "e2e/.results/glossary-phone.png" });
  await page.goto("/team");
  await open("Payroll", "The wages you pay your staff");
  await page.goto('/what-if?s=[{"type":"collect_receivable","invoice_id":30}]');
  await open("Cash gap", "fall below your cushion");
  await page.goto("/paperwork");
  await open("Bank reconciliation", "A difference of $0.00 means they agree.");
  await open("Net profit", "What is left after all costs are taken from your income.");
});
