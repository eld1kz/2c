import type { Schemas } from "@/lib/api/client";
import type { TermId } from "@/lib/glossary";
import { weekList } from "@/lib/labels";
import { formatCents } from "@/lib/money";
import { Help } from "@/components/glossary/help";

type Gap = Schemas["GapOut"] | null;

function GapLine({ label, gap, currency, emphasis, term }: { label: string; gap: Gap; currency: string; emphasis?: boolean; term?: TermId }) {
  return (
    <div className={emphasis ? "text-ink" : "text-ink-2"}>
      <dt className="flex items-center gap-1 text-xs font-medium text-ink-3">{label}{term && <Help term={term} />}</dt>
      <dd className="mt-0.5 text-[15px] leading-snug">
        {gap ? (
          <>
            <span className={`num font-semibold ${emphasis ? "text-risk-ink" : ""}`}>{formatCents(gap.amount_cents, currency)}</span> short of
            the buffer at the lowest point (week {gap.low_week}); below it in {weekList(gap.weeks_below)}.
          </>
        ) : (
          <span className="font-semibold text-good-ink">Cash stays above the buffer in every week.</span>
        )}
      </dd>
    </div>
  );
}

/** The gap before and after the scenario, from the engine's own gap fields. */
export function WhatIfSummary({ result }: { result: Schemas["WhatIfOut"] }) {
  return (
    <dl className="grid gap-3 sm:grid-cols-2" data-testid="whatif-summary">
      <GapLine label="Today's forecast" gap={result.base_gap} currency={result.currency} term="forecast" />
      <GapLine label="If the assumption holds" gap={result.scenario_gap} currency={result.currency} emphasis term="cash_gap" />
    </dl>
  );
}

/** "What if Harbor Lane Café pays INV-1042?" for a single collection, else a generic title. */
export function whatIfTitle(result: Schemas["WhatIfOut"]): string {
  const [first, ...rest] = result.assumptions;
  if (first?.type === "collect_receivable" && rest.length === 0 && first.counterparty_name) {
    return `What if ${first.counterparty_name} pays ${first.invoice?.label ?? "the invoice"}?`;
  }
  return "What-if scenario";
}
