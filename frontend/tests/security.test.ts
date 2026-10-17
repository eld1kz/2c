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
  ])("allows %s /%s", (method, path) => expect(isAllowed(method, path)).toBe(true));

  it.each([
    ["POST", "actions"], // proposing is the agent's job, never the browser's
    ["GET", "auth/login"],
    ["DELETE", "actions/1"],
    ["GET", "forecast/weeks/6/../../admin"],
    ["GET", "me/"],
    ["GET", "openapi.json"],
  ])("refuses %s /%s", (method, path) => expect(isAllowed(method, path)).toBe(false));
});

describe("safeNext", () => {
  it.each([
    [null, "/dashboard"],
    ["/approvals", "/approvals"],
    ["//evil.example", "/dashboard"],
    ["/\\evil.example", "/dashboard"],
    ["https://evil.example", "/dashboard"],
    ["/login", "/dashboard"],
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
