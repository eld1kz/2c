"use client";

import { CircleAlertIcon } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useMe, useWhatIf } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";
import { parseScenarios } from "@/lib/scenarios";

import { Assumptions } from "./assumptions";
import { WhatIfChart, WhatIfLegend } from "./whatif-chart";
import { WhatIfLinks } from "./whatif-links";
import { WhatIfSummary, whatIfTitle } from "./whatif-summary";
import { WhatIfTable } from "./whatif-table";

function Problem({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="mt-4 flex gap-2 rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-ink-2">
      <CircleAlertIcon className="mt-0.5 size-4 shrink-0 text-attn-ink" />
      <span>{children}</span>
    </p>
  );
}

/** The what-if page: a scenario from the URL, today's forecast next to the scenario, and its assumptions. */
export function WhatIfView() {
  const raw = useSearchParams().get("s");
  const scenarios = useMemo(() => parseScenarios(raw), [raw]);
  const me = useMe();
  const viewer = me.data?.user.role === "viewer";
  const result = useWhatIf(scenarios ?? [], !!me.data && !viewer);
  const [asTable, setAsTable] = useState(false);
  const r = result.data;

  return (
    <div className="max-w-4xl space-y-5">
      <div>
        <p className="text-xs font-medium text-ink-3">Simulation · nothing in your books changes</p>
        <h1 className="mt-1 text-[26px] leading-[1.2] font-semibold tracking-tight text-ink md:text-[30px]">{r ? whatIfTitle(r) : "What if…"}</h1>
      </div>

      {viewer && <Problem>Simulations need an owner or accountant. Viewers can see the forecast on the overview.</Problem>}
      {scenarios === null && <Problem>This what-if link isn&apos;t valid. Start again from the overview or the chat.</Problem>}
      {scenarios?.length === 0 && !viewer && (
        <div className="space-y-3">
          <p className="text-[15px] text-ink-2">Pick a scenario to compare with today&apos;s forecast, or ask the CFO to run one.</p>
          <div className="flex flex-wrap gap-2">
            <WhatIfLinks />
          </div>
        </div>
      )}
      {result.isError && <Problem>{result.error.message}</Problem>}

      {scenarios && scenarios.length > 0 && !viewer && !result.isError && (
        <>
          {r ? <Assumptions items={r.assumptions} currency={r.currency} /> : <Skeleton className="h-24" />}
          {r ? <WhatIfSummary result={r} /> : <Skeleton className="h-14" />}

          <section className="rounded-[var(--radius-panel)] border border-line bg-surface p-4 md:p-5" aria-labelledby="whatif-chart-title">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 id="whatif-chart-title" className="text-[15px] font-semibold">
                  Closing cash by week, before and after
                </h2>
                {r && <div className="mt-1.5"><WhatIfLegend buffer={r.min_cash_buffer_cents} currency={r.currency} /></div>}
              </div>
              <div className="flex rounded-lg bg-sunken p-0.5 text-xs font-medium" role="group" aria-label="View">
                {(["Chart", "Table"] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setAsTable(v === "Table")}
                    aria-pressed={asTable === (v === "Table")}
                    className={cn("rounded-md px-2.5 py-1", asTable === (v === "Table") ? "bg-surface text-ink shadow-sm" : "text-ink-2")}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-4">
              {!r ? (
                <Skeleton className="h-[250px] md:h-[320px]" />
              ) : asTable ? (
                <WhatIfTable weeks={r.weeks} currency={r.currency} />
              ) : (
                <WhatIfChart weeks={r.weeks} buffer={r.min_cash_buffer_cents} currency={r.currency} />
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
