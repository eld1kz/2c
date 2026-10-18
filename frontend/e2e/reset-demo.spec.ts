import { expect, test } from "@playwright/test";

import { signIn } from "./helpers";

// The confirmed reset is answered by a recorded response so test runs never reset the local demo;
// the reset itself is covered by backend/tests/test_demo_reset.py.

test("owner resets the demo behind a confirm dialog", async ({ page }, info) => {
  await signIn(page, "owner");
  let calls = 0;
  await page.route("**/api/backend/demo/reset", (route) => {
    calls++;
    return route.fulfill({ json: { removed: { actions: 3, sandbox_emails: 1 } } });
  });
  await page.goto("/approvals");
  const reset = page.getByRole("button", { name: "Reset demo data" }).first();
  const open = async () => {
    // on phones it lives in the More menu, which stays open after Cancel
    if (info.project.name === "phone" && !(await reset.isVisible())) await page.getByRole("button", { name: "More" }).click();
    await reset.click();
  };
  await open();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("The audit log is kept as it is and records this reset.");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  expect(calls).toBe(0);

  await open();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reset demo data" }).click();
  await expect(page.getByText("Demo data reset.")).toBeVisible();
  await expect(page).toHaveURL(/\/today$/);
  expect(calls).toBe(1);
});

test("only the owner sees the reset", async ({ page }, info) => {
  await signIn(page, "accountant");
  if (info.project.name === "phone") await page.getByRole("button", { name: "More" }).click();
  await expect(page.getByRole("button", { name: "Reset demo data" })).toHaveCount(0);
});
