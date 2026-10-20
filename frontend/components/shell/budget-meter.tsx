"use client";


import { useBudget } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";
import { formatCents } from "@/lib/money";

const MICRO_PER_CENT = 10_000;

/** Today's AI budget. The engine (dashboard, forecast, approvals) works without it. */
export function BudgetMeter({ className }: { className?: string }) {
  const { data } = useBudget();
  if (!data) return <div className={cn("h-10", className)} />;
  const left = formatCents(Math.trunc(data.remaining_microusd / MICRO_PER_CENT));
  const limit = formatCents(Math.trunc(data.limit_microusd / MICRO_PER_CENT));
  const pct = data.limit_microusd > 0 ? Math.round((data.remaining_microusd * 100) / data.limit_microusd) : 0;
  return (
    <div className={cn("text-xs", className)}>
      <div className="flex items-center justify-between gap-2 text-ink-2">
        <span className="flex items-center gap-1.5">
          AI budget
        </span>
        <span className={cn("num whitespace-nowrap font-medium", data.exhausted ? "text-risk-ink" : "text-ink")}>
          {data.exhausted ? "Used up" : `${left} of ${limit}`}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sunken" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label="AI budget remaining">
        <div className={cn("h-full rounded-full", pct < 20 ? "bg-attn" : "bg-brand")} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
