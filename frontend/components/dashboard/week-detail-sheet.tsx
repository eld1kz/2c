"use client";

import { EvidenceList } from "@/components/evidence/evidence-chip";
import { Money } from "@/components/money";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useForecastWeek } from "@/lib/api/hooks";
import { LINE_KIND } from "@/lib/labels";
import { formatDay } from "@/lib/money";

/** Every forecast line in one week, each with the records it comes from. */
export function WeekDetailSheet({ week, currency, onClose }: { week: number | null; currency: string; onClose: () => void }) {
  const { data, isLoading, isError } = useForecastWeek(week);
  const w = data?.week;
  return (
    <Sheet open={week !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        title={w ? `Week ${w.week}, ${formatDay(w.start)} to ${formatDay(w.end)}` : `Week ${week ?? ""}`}
        description={w ? (w.below_buffer ? "Closes below the buffer" : "Closes above the buffer") : undefined}
      >
        {isLoading && <Skeleton className="h-40" />}
        {isError && <p className="text-sm text-risk-ink">This week couldn&apos;t be loaded. Close the panel and try again.</p>}
        {w && data && (
          <>
            <dl className="num grid grid-cols-3 gap-2 rounded-xl bg-sunken p-3 text-sm">
              <div>
                <dt className="text-xs text-ink-3">Opening</dt>
                <dd className="font-medium">
                  <Money cents={w.opening_cents} currency={currency} />
                </dd>
              </div>
              <div>
                <dt className="text-xs text-ink-3">In and out</dt>
                <dd className="text-xs text-ink-2">
                  <Money cents={w.inflows_cents} currency={currency} signed /> in
                  <br />
                  <Money cents={w.outflows_cents} currency={currency} /> out
                </dd>
              </div>
              <div>
                <dt className="text-xs text-ink-3">Closing</dt>
                <dd className="font-semibold">
                  <Money cents={w.closing_cents} currency={currency} tone={w.below_buffer ? "risk" : "plain"} />
                </dd>
              </div>
            </dl>
            <ul className="mt-4 divide-y divide-line">
              {data.lines.map((ln, i) => (
                <li key={i} className="py-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink">{ln.counterparty_name ?? LINE_KIND[ln.kind] ?? ln.kind}</p>
                      <p className="text-xs text-ink-3">
                        {formatDay(ln.date)}
                        {ln.counterparty_name && `, ${LINE_KIND[ln.kind]?.toLowerCase() ?? ln.kind}`}
                        {ln.probability_bp < 10_000 && `, ${ln.probability_display} likely`}
                      </p>
                    </div>
                    <Money cents={ln.amount_cents} currency={currency} signed className="text-sm font-medium" />
                  </div>
                  <div className="mt-2">
                    <EvidenceList items={ln.sources} max={3} />
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
