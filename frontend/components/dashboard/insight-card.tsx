import { EvidenceList } from "@/components/evidence/evidence-chip";
import { Money } from "@/components/money";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { IMPACT_PERIOD, INSIGHT_TYPE, SEVERITY } from "@/lib/labels";

const SEVERITY_TONE: Record<string, string> = {
  high: "bg-risk",
  med: "bg-attn",
  low: "bg-ink-3",
};

/** One detected problem or opportunity with its $ impact and the records behind it. */
export function InsightCard({ insight, action }: { insight: Schemas["InsightOut"]; action?: React.ReactNode }) {
  const period = IMPACT_PERIOD[insight.impact_period] ?? insight.impact_period;
  return (
    <article className="flex flex-col gap-3 py-4 md:flex-row md:items-start md:gap-6">
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 text-xs text-ink-3">
          <span className={cn("size-2 rounded-full", SEVERITY_TONE[insight.severity])} aria-hidden />
          <span>
            {INSIGHT_TYPE[insight.type] ?? insight.type}, {SEVERITY[insight.severity]?.toLowerCase() ?? insight.severity} priority
          </span>
        </p>
        <h3 className="mt-1 text-[15px] leading-snug font-medium text-ink">{insight.title}</h3>
        <div className="mt-2">
          <EvidenceList items={insight.evidence} max={3} />
        </div>
      </div>
      <div className="flex shrink-0 items-center justify-between gap-4 md:flex-col md:items-end">
        <p className="text-right">
          <Money cents={insight.impact_cents} currency={insight.currency} className="text-lg font-semibold" />
          {period && <span className="ml-1 text-xs text-ink-3">{period}</span>}
        </p>
        {action}
      </div>
    </article>
  );
}
