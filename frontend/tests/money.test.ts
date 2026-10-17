import { describe, expect, it } from "vitest";

import { formatCents, formatCentsCompact, formatDate, formatDay, MINUS } from "@/lib/money";

describe("formatCents", () => {
  it.each([
    [865_000, "$8,650.00"],
    [-199_767, `${MINUS}$1,997.67`],
    [-218_199, `${MINUS}$2,181.99`],
    [5, "$0.05"],
    [0, "$0.00"],
    [123_456_789, "$1,234,567.89"],
  ])("%i → %s", (cents, text) => expect(formatCents(cents)).toBe(text));

  it("signs positives only when asked", () => {
    expect(formatCents(365_000, "USD", { signed: true })).toBe("+$3,650.00");
    expect(formatCents(0, "USD", { signed: true })).toBe("$0.00");
  });

  it("drops .00 only when asked and only when the cents are zero", () => {
    expect(formatCents(500_000, "USD", { dropZeroCents: true })).toBe("$5,000");
    expect(formatCents(500_001, "USD", { dropZeroCents: true })).toBe("$5,000.01");
  });

  it("prefixes unknown currencies with their code", () => expect(formatCents(1_000, "EUR")).toBe("EUR 10.00"));

  it("refuses non-integer amounts", () => {
    expect(() => formatCents(10.5)).toThrow();
    expect(() => formatCentsCompact(Number.NaN)).toThrow();
  });
});

describe("formatCentsCompact", () => {
  it.each([
    [500_000, "$5k"],
    [1_208_090, "$12.1k"],
    [-218_199, `${MINUS}$2.2k`],
    [-199_767, `${MINUS}$2k`],
    [99_949, "$999"],
    [0, "$0"],
  ])("%i → %s", (cents, text) => expect(formatCentsCompact(cents)).toBe(text));
});

describe("dates", () => {
  it("formats ISO days without time-zone drift", () => {
    expect(formatDay("2026-11-05")).toBe("Nov 5");
    expect(formatDate("2026-10-01")).toBe("Oct 1, 2026");
  });
});
