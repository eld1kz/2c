import { expect, test } from "@playwright/test";

// Credentials only ever travel in the POST body to /api/auth/login: never in a page URL or a request URL,
// with JavaScript (the form's handler) or before it loads (a native submission).

const EMAIL = "owner@emberoak.demo";
const PASSWORD = process.env.DEMO_PASSWORD ?? "emberoak-demo";
const leaks = (url: string) => [EMAIL, encodeURIComponent(EMAIL), PASSWORD].some((s) => decodeURIComponent(url).includes(s) || url.includes(s));

test("signing in never puts the email or password in a URL", async ({ page }) => {
  const urls: string[] = [];
  page.on("request", (r) => urls.push(r.url()));
  page.on("framenavigated", (f) => urls.push(f.url()));
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  const login = page.waitForRequest("**/api/auth/login");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const req = await login;
  expect(req.method()).toBe("POST");
  expect(req.postData()).toContain(EMAIL); // in the body only
  await page.waitForURL("**/today");
  expect(urls.length).toBeGreaterThan(3);
  expect(urls.filter(leaks)).toEqual([]);
});

test("before the app's JavaScript loads, the form can't submit and would only ever POST", async ({ page }) => {
  // the page's own bundles never arrive (a slow network, or a click before hydration); Next's inline scripts still run
  await page.route("**/_next/static/chunks/**", (route) => route.abort());
  const urls: string[] = [];
  page.on("request", (r) => urls.push(r.url()));
  page.on("framenavigated", (f) => urls.push(f.url()));
  await page.goto("/login");
  await expect(page.locator("form").first()).toHaveAttribute("method", "post");
  expect(await page.locator("input[name]").count()).toBe(0); // unnamed inputs: a native submit sends no credentials
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeDisabled();
  await page.getByLabel("Password").press("Enter");
  await expect(page).toHaveURL(/\/login$/);
  expect(urls.filter(leaks)).toEqual([]);
});
