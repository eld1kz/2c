import type { Schemas } from "@/lib/api/client";

// What-if scenarios travel in the page URL (`/what-if?s=<json>`), from the chat or the cash-gap card.
// They are ids, dates, enums and integer cents only; the server validates them again on every request.

export type ScenarioInput = Schemas["WhatIfIn"]["scenarios"][number];

const TYPES = new Set(["collect_receivable", "delay_receivable", "add_recurring", "one_off", "remove_series", "raise_payroll"]);
const MAX_SCENARIOS = 5;

/** "invoice:30" → collect it now. */
export function collect(invoiceRef: string): ScenarioInput {
  return { type: "collect_receivable", invoice_id: Number(invoiceRef.split(":")[1]) };
}

export function whatIfHref(scenarios: ScenarioInput[], view?: "financing"): string {
  const params = new URLSearchParams();
  if (scenarios.length) params.set("s", JSON.stringify(scenarios));
  if (view) params.set("view", view);
  const query = params.toString();
  return query ? `/what-if?${query}` : "/what-if";
}

/** The scenarios in `?s=`, or null when the value is not a plausible list (the server checks the rest). */
export function parseScenarios(raw: string | null): ScenarioInput[] | null {
  if (!raw) return [];
  try {
    const value: unknown = JSON.parse(raw);
    if (!Array.isArray(value) || value.length > MAX_SCENARIOS) return null;
    const ok = value.every((s) => typeof s === "object" && s !== null && TYPES.has((s as { type?: unknown }).type as string));
    return ok ? (value as ScenarioInput[]) : null;
  } catch {
    return null;
  }
}
