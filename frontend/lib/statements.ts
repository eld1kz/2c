import type { Schemas } from "@/lib/api/client";
import { CATEGORIES, CATEGORY } from "@/lib/labels";
import type { TermId } from "@/lib/glossary";

// Rows for the cash-basis statement tables. Every figure is copied from the API (integer cents);
// nothing here adds or subtracts. A statement with several periods gets one column per period.

export type StatementRow = { label: string; values: (number | null)[]; kind?: "section" | "total" | "grand"; term?: TermId };

type Pnl = Schemas["ProfitAndLossOut"];
type Section = "revenue" | "cogs" | "operating_expenses" | "other_income";

export function lineLabel(key: string): string {
  if (key === "uncategorized") return "Not yet categorized";
  return CATEGORY[key as keyof typeof CATEGORY] ?? key;
}

const ORDER: string[] = [...CATEGORIES, "uncategorized"];

function sectionRows(pnls: Pnl[], section: Section): StatementRow[] {
  const keys = ORDER.filter((key) => pnls.some((p) => p[section].some((line) => line.key === key)));
  return keys.map((key) => ({
    label: lineLabel(key),
    values: pnls.map((p) => p[section].find((line) => line.key === key)?.amount_cents ?? 0),
  }));
}

export function pnlRows(pnls: Pnl[]): StatementRow[] {
  const total = (label: string, pick: (p: Pnl) => number, kind: StatementRow["kind"] = "total"): StatementRow => ({
    label,
    values: pnls.map(pick),
    kind,
  });
  const otherIncome = pnls.some((p) => p.other_income.length > 0);
  return [
    { label: "Income", values: pnls.map(() => null), kind: "section", term: "revenue" },
    ...sectionRows(pnls, "revenue"),
    total("Total income", (p) => p.total_revenue_cents),
    { label: "Cost of goods sold", values: pnls.map(() => null), kind: "section", term: "cogs" },
    ...sectionRows(pnls, "cogs"),
    total("Total cost of goods sold", (p) => p.total_cogs_cents),
    total("Gross profit", (p) => p.gross_profit_cents),
    { label: "Operating expenses", values: pnls.map(() => null), kind: "section", term: "operating_expenses" },
    ...sectionRows(pnls, "operating_expenses"),
    total("Total operating expenses", (p) => p.total_operating_expenses_cents),
    ...(otherIncome
      ? [
          { label: "Other income", values: pnls.map(() => null), kind: "section" as const },
          ...sectionRows(pnls, "other_income"),
          total("Total other income", (p) => p.total_other_income_cents),
        ]
      : []),
    { ...total("Net profit (cash basis)", (p) => p.net_profit_cents, "grand"), term: "net_profit" },
  ];
}

export function cashFlowRows(flows: Schemas["CashFlowOut"][]): StatementRow[] {
  const row = (label: string, pick: (c: Schemas["CashFlowOut"]) => number, kind?: StatementRow["kind"]): StatementRow => ({
    label,
    values: flows.map(pick),
    kind,
  });
  return [
    row("Cash at start", (c) => c.opening_cents, "total"),
    row("Money in from operations", (c) => c.operating_in_cents),
    row("Money out for operations", (c) => -c.operating_out_cents),
    row("Net cash from operations", (c) => c.net_operating_cents, "total"),
    row("Transfers", (c) => c.transfers_cents),
    row("Net change in cash", (c) => c.net_change_cents, "total"),
    row("Cash at end", (c) => c.closing_cents, "grand"),
  ];
}

export const BUCKET_LABEL: Record<string, string> = {
  current: "Not yet due",
  "1_30": "1–30 days late",
  "31_60": "31–60 days late",
  "61_90": "61–90 days late",
  over_90: "Over 90 days late",
};
export const BUCKETS = Object.keys(BUCKET_LABEL);

/** What a lender may also ask for that bank and invoice records can't produce. */
export const NOT_INCLUDED = [
  { title: "Balance sheet", why: "It needs assets, liabilities and equity beyond your bank account and invoices." },
  { title: "Tax returns", why: "Filed returns come from your tax preparer; Ledgerwise does not prepare or file taxes." },
  {
    title: "Legal documents",
    why: "Business registration, ownership details, and lease or loan agreements come from you or your lawyer.",
  },
];
