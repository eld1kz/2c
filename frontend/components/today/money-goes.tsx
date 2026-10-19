import Link from "next/link";

import { Money } from "@/components/money";
import type { Schemas } from "@/lib/api/client";
import { lineLabel } from "@/lib/statements";

const SHOWN = 5;

/** Last month's spending by category (cash basis), largest first; links to the full P&L. */
export function MoneyGoes({ spending, currency }: { spending: Schemas["SpendingOut"]; currency: string }) {
  const top = spending.lines.slice(0, SHOWN);
  const largest = Math.max(...top.map((l) => l.amount_cents), 1);
  return (
    <section className="rounded-[var(--radius-panel)] border border-line bg-surface p-4 md:p-5" aria-labelledby="goes-title">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="goes-title" className="text-[15px] font-semibold">Where your money went in {spending.period.label.split(" ")[0]}</h2>
        <Money cents={spending.total_cents} currency={currency} className="text-[17px] font-semibold" split />
      </div>
      <Link href="/paperwork" className="mt-3 block space-y-2.5 rounded-lg outline-offset-4" aria-label="Open the full profit and loss">
        {top.map((l) => (
          <div key={l.key}>
            <div className="flex justify-between gap-3 text-sm">
              <span className="text-ink-2">{lineLabel(l.key)}</span>
              <Money cents={l.amount_cents} currency={currency} />
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-sunken">
              <div className="h-1.5 rounded-full bg-brand" style={{ width: `${Math.max((l.amount_cents / largest) * 100, 2)}%` }} />
            </div>
          </div>
        ))}
        <p className="pt-1 text-sm font-medium text-brand-ink">See the full profit and loss</p>
      </Link>
    </section>
  );
}
