import { describe, expect, it } from "vitest";

import { isAllowed } from "@/lib/backend-routes";
import { safeNext } from "@/lib/safe-next";
import { isSameOrigin } from "@/lib/session";

describe("backend proxy allowlist", () => {
  it.each([
    ["GET", "me"],
    ["GET", "forecast"],
    ["GET", "forecast/weeks/6"],
    ["GET", "actions"],
    ["POST", "whatif"],
    ["POST", "financing"],
    ["GET", "memo"],
    ["POST", "memo"],
    ["GET", "paperwork/month-close"],
    ["GET", "paperwork/bank-pack"],
    ["GET", "today"],
    ["POST", "today/decisions/4/prepare"],
  ])("allows %s /%s", (method, path) => expect(isAllowed(method, path)).toBe(true));

  it.each([
    ["POST", "actions"], // proposing is the agent's job, never the browser's
    ["GET", "auth/login"],
    ["DELETE", "actions/1"],
    ["GET", "forecast/weeks/6/../../admin"],
    ["GET", "me/"],
    ["GET", "openapi.json"],
    ["GET", "whatif"], // a simulation is a POST with a JSON body only
    ["POST", "whatif/1"],
    ["POST", "paperwork/month-close"], // read-only
    ["GET", "paperwork/other"],
    ["POST", "today"],
    ["GET", "today/decisions/4/prepare"],
  ])("refuses %s /%s", (method, path) => expect(isAllowed(method, path)).toBe(false));
});

describe("safeNext", () => {
  it.each([
    [null, "/today"],
    ["/approvals", "/approvals"],
    ["//evil.example", "/today"],
    ["/\\evil.example", "/today"],
    ["https://evil.example", "/today"],
    ["/login", "/today"],
  ])("%s → %s", (next, out) => expect(safeNext(next)).toBe(out));
});

describe("isSameOrigin", () => {
  it("accepts only a matching host", () => {
    expect(isSameOrigin("http://localhost:3000", "localhost:3000")).toBe(true);
    expect(isSameOrigin("https://evil.example", "localhost:3000")).toBe(false);
    expect(isSameOrigin(null, "localhost:3000")).toBe(false);
    expect(isSameOrigin("not a url", "localhost:3000")).toBe(false);
  });
});
