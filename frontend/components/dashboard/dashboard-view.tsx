"use client";

import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useForecast, useInsights } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";
import { formatCents } from "@/lib/money";

import { CashHeadline } from "./cash-headline";
import { ForecastChart } from "./forecast-chart";
import { ForecastTable } from "./forecast-table";
import { InsightCard } from "./insight-card";
import { SideRail } from "./side-rail";
import { WeekDetailSheet } from "./week-detail-sheet";

const TOP_INSIGHTS = 3;

function Legend({ buffer, currency }: { buffer: number; currency: string }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
      <li className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-sm bg-good" aria-hidden /> Above buffer
      </li>
      <li className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-sm bg-risk" aria-hidden /> Below buffer
      </li>
      <li className="flex items-center gap-1.5">
        <span className="w-4 border-t-2 border-dashed border-ink-2" aria-hidden /> {formatCents(buffer, currency, { dropZeroCents: true })} minimum buffer
      </li>
    </ul>
  );
}

export function DashboardView() {
  const forecast = useForecast();
  const insights = useInsights();
  const [week, setWeek] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const fc = forecast.data;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_272px] lg:gap-x-10">
      <div className="lg:col-start-1">
        {fc ? <CashHeadline forecast={fc} /> : <Skeleton className="h-28 max-w-xl" />}
        {forecast.isError && (
          <p role="alert" className="mt-2 text-sm text-risk-ink">
            The forecast couldn&apos;t be loaded. Refresh the page to try again.
          </p>
        )}
      </div>

      <div className="lg:col-start-2 lg:row-span-3 lg:row-start-1">
        <div className="lg:sticky lg:top-8">
          <SideRail />
        </div>
      </div>

      <section className="rounded-[var(--radius-panel)] border border-line bg-surface p-4 md:p-5 lg:col-start-1" aria-labelledby="forecast-title">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="forecast-title" className="text-[15px] font-semibold">
              Closing cash by week, next 13 weeks
            </h2>
            {fc && <div className="mt-1.5"><Legend buffer={fc.min_cash_buffer_cents} currency={fc.currency} /></div>}
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
          {!fc ? (
            <Skeleton className="h-[250px] md:h-[320px]" />
          ) : asTable ? (
            <ForecastTable weeks={fc.weeks} currency={fc.currency} onSelectWeek={setWeek} />
          ) : (
            <ForecastChart weeks={fc.weeks} buffer={fc.min_cash_buffer_cents} currency={fc.currency} onSelectWeek={setWeek} />
          )}
        </div>
        <p className="mt-2 text-xs text-ink-3">Select a week to see each payment behind it and the records it comes from.</p>
      </section>

      <section className="lg:col-start-1" aria-labelledby="insights-title">
        <h2 id="insights-title" className="text-[15px] font-semibold">
          What needs attention
        </h2>
        <div className="mt-1 divide-y divide-line border-t border-line">
          {insights.data
            ? insights.data.slice(0, TOP_INSIGHTS).map((i) => <InsightCard key={i.id} insight={i} />)
            : Array.from({ length: TOP_INSIGHTS }, (_, i) => <Skeleton key={i} className="my-4 h-16" />)}
          {insights.data?.length === 0 && <p className="py-4 text-sm text-ink-3">No open issues right now.</p>}
        </div>
      </section>

      {fc && <WeekDetailSheet week={week} currency={fc.currency} onClose={() => setWeek(null)} />}
    </div>
  );
}
