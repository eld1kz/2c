// Plain-language names for engine enums.

export const INSIGHT_TYPE: Record<string, string> = {
  LATE_PAYER: "Late payer",
  DUPLICATE_SUBSCRIPTION: "Duplicate subscription",
  PRICE_CREEP: "Supplier price rise",
  CASH_GAP: "Cash gap",
  UNUSUAL_EXPENSE: "Unusual expense",
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
