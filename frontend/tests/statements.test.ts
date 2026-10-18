import { describe, expect, it } from "vitest";

import type { Schemas } from "@/lib/api/client";
import { cashFlowRows, pnlRows } from "@/lib/statements";

type Pnl = Schemas["ProfitAndLossOut"];
const line = (key: string, amount_cents: number) => ({ key, amount_cents, count: 1 });
const period = (label: string) => ({ start: "2026-09-01", end: "2026-09-30", label });

function pnl(label: string, operating: Pnl["operating_expenses"], other: Pnl["other_income"] = []): Pnl {
  return {
    period: period(label), revenue: [line("revenue_retail", 1000)], cogs: [], operating_expenses: operating, other_income: other,
    total_revenue_cents: 1000, total_cogs_cents: 0, gross_profit_cents: 1000, total_operating_expenses_cents: 600,
    total_other_income_cents: 0, net_profit_cents: 400, transfers_cents: 0, transaction_count: 3,
  };
}

describe("pnlRows", () => {
  it("merges lines across months in category order, with $0 where a month has none", () => {
    const rows = pnlRows([pnl("Jul", [line("uncategorized", 100), line("rent", 500)]), pnl("Aug", [line("taxes", 600)])]);
    const opex = rows.slice(rows.findIndex((r) => r.label === "Operating expenses") + 1, rows.findIndex((r) => r.label === "Total operating expenses"));
    expect(opex.map((r) => r.label)).toEqual(["Rent", "Taxes", "Not yet categorized"]);
    expect(opex.find((r) => r.label === "Taxes")?.values).toEqual([0, 600]);
  });

  it("copies totals from the API and shows Other income only when there is some", () => {
    const rows = pnlRows([pnl("Sep", [line("rent", 600)])]);
    expect(rows.at(-1)).toEqual({ label: "Net profit (cash basis)", values: [400], kind: "grand" });
    expect(rows.some((r) => r.label === "Other income")).toBe(false);
    expect(pnlRows([pnl("Sep", [], [line("other", 50)])]).some((r) => r.label === "Other income")).toBe(true);
  });
});

describe("cashFlowRows", () => {
  it("runs from cash at start to cash at end", () => {
    const rows = cashFlowRows([{ period: period("Sep"), opening_cents: 100, operating_in_cents: 50, operating_out_cents: 30, net_operating_cents: 20, transfers_cents: 0, net_change_cents: 20, closing_cents: 120 }]);
    expect(rows[0]).toMatchObject({ label: "Cash at start", values: [100] });
    expect(rows.find((r) => r.label === "Money out for operations")?.values).toEqual([-30]);
    expect(rows.at(-1)).toMatchObject({ label: "Cash at end", values: [120], kind: "grand" });
  });
});
