import { EvidenceChip } from "@/components/evidence/evidence-chip";
import { Money } from "@/components/money";
import type { Schemas } from "@/lib/api/client";
import { CATEGORY } from "@/lib/labels";
import { formatDay } from "@/lib/money";

/** Rent and lease payments due in the next 13 weeks, taken from the forecast's recurring lines. */
export function ObligationsTable({ obligations, currency }: { obligations: Schemas["ObligationsOut"]; currency: string }) {
  if (obligations.rows.length === 0) return <p className="text-sm text-ink-3">No recurring rent or lease payments found.</p>;
  return (
    <ul className="divide-y divide-line text-sm" aria-label="Fixed obligations">
      {obligations.rows.map((o) => (
        <li key={`${o.series.ref}-${o.date}`} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="num w-16 text-ink-3">{formatDay(o.date)}</span>
            <span className="text-ink-2">{CATEGORY[o.category as keyof typeof CATEGORY] ?? o.category}</span>
            <EvidenceChip evidence={o.counterparty} />
          </div>
          <Money cents={o.amount_cents} currency={currency} className="font-medium" />
        </li>
      ))}
      <li className="flex justify-between py-2 font-semibold">
        <span>Total, next 13 weeks</span>
        <Money cents={obligations.total_cents} currency={currency} />
      </li>
    </ul>
  );
}
