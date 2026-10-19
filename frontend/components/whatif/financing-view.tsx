"use client";

import { CheckIcon, CircleAlertIcon, LandmarkIcon, MinusIcon, PlusIcon } from "lucide-react";

import { AskLink } from "@/components/chat/ask-link";
import { EvidenceChip, EvidenceList } from "@/components/evidence/evidence-chip";
import { Skeleton } from "@/components/ui/skeleton";
import type { Schemas } from "@/lib/api/client";
import { useFinancing } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";
import { weekList } from "@/lib/labels";
import { formatCents } from "@/lib/money";
import type { ScenarioInput } from "@/lib/scenarios";
import { Help } from "@/components/glossary/help";
import type { TermId } from "@/lib/glossary";

type Option = Schemas["FinancingOptionOut"];

function Coverage({ o, gap, currency }: { o: Option; gap: number; currency: string }) {
  return o.covers_gap ? (
    <span className="flex items-center gap-1 text-good-ink">
      <CheckIcon className="size-3.5 shrink-0" /> Covers the whole {formatCents(gap, currency)}
    </span>
  ) : (
    <span className="flex items-center gap-1 text-attn-ink">
      <CircleAlertIcon className="size-3.5 shrink-0" /> Not enough alone: up to {formatCents(o.max_amount_cents, currency)} of{" "}
      {formatCents(gap, currency)}
    </span>
  );
}

const OPTION_TERM: Record<string, TermId> = {
  overdraft: "apr", short_term_loan: "apr", invoice_factoring: "factoring",
  supplier_terms_extension: "payment_terms", accelerate_receivables: "receivable",
};

function OptionCard({ o, gap, currency }: { o: Option; gap: number; currency: string }) {
  return (
    <li className={cn("rounded-[var(--radius-panel)] border bg-surface p-4", o.rank === 1 ? "border-brand/50" : "border-line")} aria-label={`Option ${o.rank}: ${o.name}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-ink-3">{o.rank === 1 ? "Rank 1 · cheapest full cover" : `Rank ${o.rank}`}</p>
          <div className="mt-0.5 flex items-start gap-1">
            <h3 className="text-[15px] leading-snug font-semibold text-ink">{o.name}</h3>
            {OPTION_TERM[o.option_id] && <Help term={OPTION_TERM[o.option_id]} />}
          </div>
        </div>
        <p className="shrink-0 text-right">
          <span className="num block text-lg font-semibold text-ink">{formatCents(o.cost_cents, currency)}</span>
          <span className="text-xs text-ink-3">cost for this gap</span>
        </p>
      </div>
      <div className="mt-2 text-sm">
        <Coverage o={o} gap={gap} currency={currency} />
      </div>
      {o.by_counterparty.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm text-ink-2">
          {o.by_counterparty.map((s) => (
            <li key={s.counterparty.ref} className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
              <EvidenceChip evidence={s.counterparty} />
              <span className="num">{formatCents(s.amount_cents, currency)}</span>
              <span className={s.covers_gap_alone ? "text-good-ink" : "text-ink-3"}>{s.covers_gap_alone ? "covers it alone" : "not enough alone"}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
        <ul className="space-y-0.5 text-ink-2" aria-label="Pros">
          {o.pros.map((p) => (
            <li key={p} className="flex gap-1.5">
              <PlusIcon className="mt-0.5 size-3.5 shrink-0 text-good-ink" />
              {p}
            </li>
          ))}
        </ul>
        <ul className="space-y-0.5 text-ink-2" aria-label="Cons">
          {o.cons.map((c) => (
            <li key={c} className="flex gap-1.5">
              <MinusIcon className="mt-0.5 size-3.5 shrink-0 text-risk-ink" />
              {c}
            </li>
          ))}
        </ul>
      </div>
      {o.evidence.length > 0 && (
        <div className="mt-3">
          <EvidenceList items={o.evidence} max={3} />
        </div>
      )}
    </li>
  );
}

/** Financing options for a gap, ranked by the engine: full cover first, then cost. Advisory only. */
export function FinancingView({ scenarios, ask }: { scenarios: ScenarioInput[]; ask: string }) {
  const result = useFinancing(scenarios);
  const f = result.data;
  const leftover = scenarios.length > 0;
  return (
    <section aria-labelledby="financing-title" className="space-y-3">
      <div>
        <h2 id="financing-title" className="flex items-center gap-1.5 text-[17px] font-semibold text-ink">
          <LandmarkIcon className="size-4 text-ink-3" />
          {leftover ? "Ways to cover the gap left after this scenario" : "Ways to cover today's gap"}
        </h2>
        {f?.gap && (
          <p className="mt-1 text-sm text-ink-2">
            Gap: <span className="num font-semibold text-ink">{formatCents(f.gap.amount_cents, f.currency)}</span> below the buffer at the lowest
            point (week {f.gap.low_week}); below it in {weekList(f.gap.weeks_below)}.
          </p>
        )}
      </div>
      {result.isError && (
        <p role="alert" className="text-sm text-risk-ink">
          {result.error.message}
        </p>
      )}
      {!f && !result.isError && <Skeleton className="h-64" />}
      {f && !f.gap && <p className="text-sm font-medium text-good-ink">No week falls below the buffer, so there is no gap to finance.</p>}
      {f?.gap && (
        <>
          <ol className="space-y-3">
            {f.options.map((o) => (
              <OptionCard key={o.option_id} o={o} gap={f.gap?.amount_cents ?? 0} currency={f.currency} />
            ))}
          </ol>
          <p className="text-xs text-ink-3">{f.disclaimer}</p>
          <AskLink question={ask}>Ask the CFO to prepare this</AskLink>
        </>
      )}
    </section>
  );
}
