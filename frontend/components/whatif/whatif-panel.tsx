"use client";

import { ArrowRightIcon, FlaskConicalIcon } from "lucide-react";
import Link from "next/link";

import { Skeleton } from "@/components/ui/skeleton";
import { useWhatIf } from "@/lib/api/hooks";
import { type ScenarioInput, whatIfHref } from "@/lib/scenarios";

import { WhatIfChart } from "./whatif-chart";
import { WhatIfSummary, whatIfTitle } from "./whatif-summary";

/** A chat what-if as a before/after chart, recomputed by the engine from the scenario the assistant ran. */
export function WhatIfPanel({ scenarios }: { scenarios: ScenarioInput[] }) {
  const result = useWhatIf(scenarios);
  if (result.isError) return null; // the answer still explains it; the link would only fail again
  const r = result.data;
  return (
    <section className="rounded-[var(--radius-panel)] border border-line bg-surface p-3 md:p-4" aria-label="What-if result">
      <p className="flex items-center gap-1.5 text-xs font-medium text-ink-3">
        <FlaskConicalIcon className="size-3.5" /> Simulation from your records; the scenario is an assumption
      </p>
      {r ? (
        <>
          <h3 className="mt-1 text-[15px] font-semibold text-ink">{whatIfTitle(r)}</h3>
          <div className="mt-2">
            <WhatIfSummary result={r} />
          </div>
          <div className="mt-2">
            <WhatIfChart weeks={r.weeks} buffer={r.min_cash_buffer_cents} currency={r.currency} compact />
          </div>
        </>
      ) : (
        <Skeleton className="mt-2 h-[220px]" />
      )}
      <Link href={whatIfHref(scenarios)} className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-brand-ink hover:underline">
        Open the what-if <ArrowRightIcon className="size-3.5" />
      </Link>
    </section>
  );
}
