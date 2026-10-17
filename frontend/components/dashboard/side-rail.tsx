"use client";

import { BudgetMeter } from "@/components/shell/budget-meter";
import { Money } from "@/components/money";
import { Skeleton } from "@/components/ui/skeleton";
import { usePendingActions, usePosition } from "@/lib/api/hooks";
import { formatCents } from "@/lib/money";

export function SideRail() {
  const position = usePosition();
  const pending = usePendingActions();
  const p = position.data;
  return (
    <aside className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius-panel)] border border-line bg-line lg:grid-cols-1">
      <section className="bg-surface p-4">
        <h2 className="text-sm text-ink-2">Cash today</h2>
        {p ? (
          <>
            <Money cents={p.cash_cents} currency={p.currency} className="mt-1 block text-2xl font-semibold tracking-tight" />
            <p className={`mt-1 text-xs ${p.headroom_cents >= 0 ? "text-good-ink" : "text-risk-ink"}`}>
              <span className="num">{formatCents(Math.abs(p.headroom_cents), p.currency)}</span>{" "}
              {p.headroom_cents >= 0 ? "above" : "below"} your buffer
            </p>
          </>
        ) : (
          <Skeleton className="mt-2 h-12" />
        )}
      </section>
      <section className="bg-surface p-4">
        <h2 className="text-sm text-ink-2">Waiting for approval</h2>
        {pending.data ? (
          <>
            <p className="num mt-1 text-2xl font-semibold tracking-tight">{pending.data.length}</p>
            <p className={`mt-1 text-xs ${pending.data.length ? "text-attn-ink" : "text-ink-3"}`}>
              {pending.data.length ? "Nothing runs until someone approves it" : "Nothing to approve"}
            </p>
          </>
        ) : (
          <Skeleton className="mt-2 h-12" />
        )}
      </section>
      <section className="col-span-2 bg-surface p-4 md:hidden">
        <BudgetMeter />
        <p className="mt-2 text-xs text-ink-3">Forecasts and approvals don&apos;t use the AI budget.</p>
      </section>
    </aside>
  );
}
