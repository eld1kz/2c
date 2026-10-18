import { EvidenceChip } from "@/components/evidence/evidence-chip";
import { Money } from "@/components/money";
import type { Schemas } from "@/lib/api/client";
import { formatDay } from "@/lib/money";
import { BUCKET_LABEL, BUCKETS } from "@/lib/statements";

function lateness(days: number): string {
  if (days > 0) return `${days} days late`;
  return days === 0 ? "Due today" : `Due in ${-days} days`;
}

/** Open invoices by how late they are, with bucket totals; every invoice links to its record. */
export function AgingTable({ aging, currency, label }: { aging: Schemas["AgingOut"]; currency: string; label: string }) {
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6" aria-label={`${label} by age`}>
        {BUCKETS.map((b) => (
          <div key={b} className="rounded-lg bg-sunken px-3 py-2 print:bg-transparent print:px-0">
            <dt className="text-xs text-ink-3">{BUCKET_LABEL[b]}</dt>
            <dd className={aging.totals_cents[b] && b !== "current" ? "font-semibold text-attn-ink" : "font-semibold"}>
              <Money cents={aging.totals_cents[b] ?? 0} currency={currency} />
            </dd>
          </div>
        ))}
        <div className="rounded-lg border border-line px-3 py-2">
          <dt className="text-xs text-ink-3">Total open</dt>
          <dd className="font-semibold">
            <Money cents={aging.total_cents} currency={currency} />
          </dd>
        </div>
      </dl>
      {aging.rows.length === 0 ? (
        <p className="text-sm text-ink-3">Nothing open.</p>
      ) : (
        <ul className="divide-y divide-line" aria-label={label}>
          {aging.rows.map((r) => (
            <li key={r.invoice.ref} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2 text-sm">
              <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                <EvidenceChip evidence={{ ref: r.invoice.ref, label: r.number }} />
                <EvidenceChip evidence={r.counterparty} />
              </div>
              <div className="flex items-center gap-3">
                <span className={r.days_past_due > 0 ? "text-attn-ink" : "text-ink-3"}>
                  {lateness(r.days_past_due)} · due {formatDay(r.due_date)}
                </span>
                <Money cents={r.outstanding_cents} currency={currency} className="font-medium" />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
