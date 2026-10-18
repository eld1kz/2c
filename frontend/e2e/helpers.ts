import type { Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "emberoak-demo";

/** Collects console errors and uncaught exceptions; assert it's empty at the end of a test. */
export function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => msg.type() === "error" && errors.push(msg.text()));
  page.on("pageerror", (err) => errors.push(err.message));
  return errors;
}

export async function signIn(page: Page, role: "owner" | "accountant" | "viewer") {
  await page.goto("/login");
  await page.getByLabel("Email").fill(`${role}@emberoak.demo`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/today");
}

export async function noSideScroll(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

/** Server-sent events body, as POST /chat streams it. */
export function sse(events: [string, unknown][]): string {
  return events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join("");
}

/** The id of a record by its label (e.g. an invoice number), via the labels endpoint. */
export async function refFor(page: Page, kind: string, label: string): Promise<string> {
  const refs = Array.from({ length: 50 }, (_, i) => `ref=${kind}:${i + 1}`).join("&");
  const rows: { ref: string; label: string | null }[] = await (await page.request.get(`/api/backend/records?${refs}`)).json();
  const hit = rows.find((r) => r.label === label);
  if (!hit) throw new Error(`${kind} ${label} not found`);
  return hit.ref;
}
