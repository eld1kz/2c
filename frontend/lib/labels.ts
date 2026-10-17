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
