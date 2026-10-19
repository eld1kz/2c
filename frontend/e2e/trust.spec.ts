import { expect, test } from "@playwright/test";

import { noSideScroll, signIn, watchConsole } from "./helpers";

// GET /trust is real (the backend side is tests/test_trust.py).
for (const role of ["owner", "viewer"] as const) {
  test(`${role}: Trust shows the limits, the tool table and an intact audit chain`, async ({ page }) => {
    const errors = watchConsole(page);
    await signIn(page, role);
    await page.goto("/trust");
    await expect(page.getByRole("heading", { name: "Trust & guardrails" })).toBeVisible();
    await expect(page.getByText("$5,000.00").first()).toBeVisible();
    await expect(page.getByTestId("trust-chain")).toContainText("Audit log intact");
    await expect(page.getByRole("table", { name: "Assistant tools and who may use them" })).toContainText("schedule payment");
    await expect(page.getByTestId("trust-action_denied")).toBeVisible();
    expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
    expect(errors).toEqual([]);
  });
}
