"use client";

import { CircleAlertIcon, LandmarkIcon } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Schemas } from "@/lib/api/client";
import { useMe, useWhatIf } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";
import { formatCents } from "@/lib/money";
import { parseScenarios } from "@/lib/scenarios";

import { Assumptions } from "./assumptions";
import { FinancingView } from "./financing-view";
import { Playground } from "./playground";
import { WhatIfChart, WhatIfLegend } from "./whatif-chart";
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

const ASK_BASE = "What's the cheapest way to cover the cash gap? Prepare what you recommend for my approval.";

/** The question "Ask the CFO to prepare this" fills in (the person still presses Send). */
function askFor(r: Schemas["WhatIfOut"] | undefined, leftover: boolean): string {
  const [a, ...rest] = r?.assumptions ?? [];
  if (!leftover || !a || rest.length || a.type !== "collect_receivable" || !a.counterparty_name) return ASK_BASE;
  const invoice = a.invoice?.label ?? "the invoice";
  return `If ${a.counterparty_name} pays ${invoice} now, what's the cheapest way to cover the cash gap that's left? Prepare a reminder that gets ${invoice} paid and the cheapest fix for the rest, for my approval.`;
}

/** The what-if page: a scenario from the URL, today's forecast next to the scenario, and its assumptions. */
export function WhatIfView() {
  const params = useSearchParams();
  const raw = params.get("s");
  const scenarios = useMemo(() => parseScenarios(raw), [raw]);
  const me = useMe();
  const viewer = me.data?.user.role === "viewer";
  const result = useWhatIf(scenarios ?? [], !!me.data && !viewer);
  const [asTable, setAsTable] = useState(false);
  const [financing, setFinancing] = useState<"scenario" | "base" | null>(params.get("view") === "financing" ? "scenario" : null);
  const r = result.data;
  const hasScenario = !!scenarios?.length;
  const basis = hasScenario ? financing : financing && "base";

  return (
    <div className="max-w-4xl space-y-5">
      <div>
        <p className="text-xs font-medium text-ink-3">Simulation · nothing in your books changes</p>
        <h1 className="mt-1 text-[26px] leading-[1.2] font-semibold tracking-tight text-ink md:text-[30px]">{r ? whatIfTitle(r) : hasScenario ? "What if…" : "What if…?"}</h1>
      </div>

      {viewer && <Problem>Simulations need an owner or accountant. Viewers can see the forecast on the overview.</Problem>}
      {scenarios === null && <Problem>This what-if link isn&apos;t valid. Start again from the overview or the chat.</Problem>}
      {scenarios?.length === 0 && !viewer && me.data && !basis && <Playground today={me.data.as_of} />}
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

          {r && financing === null && (
            <Button variant="primary" size="lg" onClick={() => setFinancing(r.scenario_gap ? "scenario" : "base")}>
              <LandmarkIcon />
              {r.scenario_gap
                ? `Compare financing for the ${formatCents(r.scenario_gap.amount_cents, r.currency)} left`
                : "Compare financing for today's gap"}
            </Button>
          )}
        </>
      )}

      {basis && !viewer && (
        <div className="space-y-3 border-t border-line pt-5">
          {hasScenario && (
            <div className="flex w-fit rounded-lg bg-sunken p-0.5 text-xs font-medium" role="group" aria-label="Gap to finance">
              {([["scenario", "Gap left after this scenario"], ["base", "Today's gap"]] as const).map(([v, label]) => (
                <button
                  key={v}
                  onClick={() => setFinancing(v)}
                  aria-pressed={basis === v}
                  className={cn("rounded-md px-2.5 py-1", basis === v ? "bg-surface text-ink shadow-sm" : "text-ink-2")}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
          <FinancingView scenarios={basis === "scenario" && scenarios ? scenarios : []} ask={askFor(r, basis === "scenario")} />
        </div>
      )}
    </div>
  );
}
