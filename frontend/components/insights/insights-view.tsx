"use client";

import { useState } from "react";

import { InsightActions } from "@/components/dashboard/insight-actions";
import { InsightCard } from "@/components/dashboard/insight-card";
import { Skeleton } from "@/components/ui/skeleton";
import { useInsights } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";
import { SEVERITY } from "@/lib/labels";

const FILTERS = ["all", "high", "med", "low"] as const;

export function InsightsView() {
  const { data, isLoading, isError } = useInsights();
  const [severity, setSeverity] = useState<(typeof FILTERS)[number]>("all");
  const rows = (data ?? []).filter((i) => severity === "all" || i.severity === severity);
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold tracking-tight">Insights</h1>
      <p className="mt-1 text-sm text-ink-3">
        Problems and savings the engine found in your records, largest first. Each amount is computed from the linked records, not by the AI.
      </p>
      <div className="mt-5 flex flex-wrap gap-1.5" role="group" aria-label="Filter by priority">
        {FILTERS.map((f) => (
          <button
            key={f}
            aria-pressed={severity === f}
            onClick={() => setSeverity(f)}
            className={cn("rounded-full border px-3 py-1 text-xs font-medium", severity === f ? "border-ink bg-ink text-white" : "border-line bg-surface text-ink-2")}
          >
            {f === "all" ? "All" : `${SEVERITY[f]} priority`}
            {data && <span className="num ml-1 opacity-70">{f === "all" ? data.length : data.filter((i) => i.severity === f).length}</span>}
          </button>
        ))}
      </div>
      <div className="mt-3 divide-y divide-line border-t border-line">
        {isLoading && <Skeleton className="my-4 h-40" />}
        {isError && <p className="py-4 text-sm text-risk-ink">Insights couldn&apos;t be loaded. Refresh to try again.</p>}
        {rows.map((i) => (
          <InsightCard key={i.id} insight={i} action={<InsightActions insight={i} />} />
        ))}
        {data && rows.length === 0 && <p className="py-6 text-sm text-ink-3">Nothing at this priority.</p>}
      </div>
    </div>
  );
}
