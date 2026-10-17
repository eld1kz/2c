import { expect, test } from "@playwright/test";

import { signIn, watchConsole } from "./helpers";

// Real model call through the whole stack (spends AI budget). Run with LIVE=1, desktop only.
test.skip(!process.env.LIVE, "set LIVE=1 to call the real assistant");

test("live: a cash question streams, is checked, and cites records", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one live call is enough");
  test.setTimeout(180_000);
  const errors = watchConsole(page);
  await signIn(page, "owner");
  await page.goto("/chat");
  await page.getByRole("button", { name: "Why will I be short on cash?" }).click();
  const answer = page.getByTestId("answer");
  await expect(answer.or(page.getByRole("article").getByRole("alert"))).toBeVisible({ timeout: 170_000 }); // fail fast on an error
  await expect(answer).toBeVisible();
  await expect(page.getByTestId("provisional")).toHaveCount(0);
  await expect(answer.getByRole("button").first()).toBeVisible(); // at least one openable evidence chip
  await page.screenshot({ path: "e2e/.results/live-chat.png", fullPage: true });
  expect(errors).toEqual([]);
});
