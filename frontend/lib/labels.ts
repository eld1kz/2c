import type { Schemas } from "@/lib/api/client";

// Plain-language names for engine enums.

export const INSIGHT_TYPE: Record<string, string> = {
  LATE_PAYER: "Paying late",
  DUPLICATE_SUBSCRIPTION: "Paying twice",
  PRICE_CREEP: "Price went up",
  CASH_GAP: "Cash runs short",
  UNUSUAL_EXPENSE: "Unusual cost",
};

export const SEVERITY: Record<string, string> = { high: "High", med: "Medium", low: "Low" };

export const IMPACT_PERIOD: Record<string, string> = { year: "per year", once: "" };

export const LINE_KIND: Record<string, string> = {
  opening: "Opening balance",
  recurring: "Recurring",
  ar_expected: "Expected customer payment",
  ap_due: "Supplier bill due",
  baseline_in: "Typical sales",
  baseline_out: "Typical spending",
  scenario: "Scenario",
};

/** [6] → "week 6"; [6, 9] → "weeks 6 and 9"; [6, 9, 10] → "weeks 6, 9 and 10". */
export function weekList(weeks: number[]): string {
  if (weeks.length === 1) return `week ${weeks[0]}`;
  return `weeks ${weeks.slice(0, -1).join(", ")} and ${weeks[weeks.length - 1]}`;
}

/** The question "Ask the CFO" fills in for an insight. */
export function askAbout(insight: { type: string; title: string }): string {
  switch (insight.type) {
    case "LATE_PAYER":
      return `What should I do about this late payment? ${insight.title}`;
    case "CASH_GAP":
      return "What's the cheapest way to cover the cash gap?";
    case "DUPLICATE_SUBSCRIPTION":
      return `Am I paying for the same thing twice? ${insight.title}`;
    case "PRICE_CREEP":
      return `How should I respond to this price rise? ${insight.title}`;
    default:
      return `Explain this and what I should do: ${insight.title}`;
  }
}


/** Every engine category (SPEC §6.2), named for people. `satisfies` makes tsc catch a new backend value. */
export const CATEGORY = {
  revenue_retail: "Café sales",
  revenue_wholesale: "Wholesale sales",
  cogs_beans: "Green coffee",
  cogs_packaging: "Packaging",
  rent: "Rent",
  utilities: "Utilities",
  payroll: "Payroll",
  software: "Software",
  equipment: "Equipment",
  logistics: "Shipping",
  marketing: "Marketing",
  fees: "Bank and card fees",
  taxes: "Taxes",
  transfer: "Transfers",
  other: "Other",
} satisfies Record<Schemas["Category"], string>;

export const CATEGORIES = Object.keys(CATEGORY) as Schemas["Category"][];
