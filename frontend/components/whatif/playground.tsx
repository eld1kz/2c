"use client";

import { BanknoteIcon, CalendarClockIcon, HandCoinsIcon, LandmarkIcon, PackageIcon, TrendingUpIcon, UserMinusIcon, UserPlusIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useForecast, useMonthClose, useWhatIf } from "@/lib/api/hooks";
import { formatCents, formatDay } from "@/lib/money";
import { whatIfHref, type ScenarioInput } from "@/lib/scenarios";

import { Assumptions } from "./assumptions";
import { WhatIfChart, WhatIfLegend } from "./whatif-chart";

type Kind = "hire" | "raise" | "equipment" | "late" | "lose" | "harbor";
type Item = { id: number; kind: Kind; value: number; date: string; invoiceId?: number };
type Invoice = { id: number; label: string };

const MAX_STACK = 3;

// Each preset: what the owner sets (one slider and/or a date). The values are assumptions typed in here,
// never records; the engine does every calculation (POST /whatif).
const PRESETS: Record<Kind, { title: string; icon: React.ComponentType<{ className?: string }>; slider?: { label: string; min: number; max: number; step: number; start: number; show: (v: number) => string }; dateLabel?: string }> = {
  hire: { title: "Hire someone", icon: UserPlusIcon, slider: { label: "Pay per month", min: 500, max: 6000, step: 100, start: 2500, show: (v) => `$${v.toLocaleString("en-US")}` }, dateLabel: "Starts" },
  raise: { title: "Give a raise", icon: TrendingUpIcon, slider: { label: "Raise for all staff", min: 1, max: 20, step: 1, start: 3, show: (v) => `${v}%` }, dateLabel: "Starts" },
  equipment: { title: "Buy equipment", icon: PackageIcon, slider: { label: "Price", min: 500, max: 20000, step: 250, start: 3000, show: (v) => `$${v.toLocaleString("en-US")}` }, dateLabel: "Paid on" },
  late: { title: "A customer pays late", icon: CalendarClockIcon, slider: { label: "Days late", min: 7, max: 60, step: 1, start: 30, show: (v) => `${v} days` } },
  lose: { title: "Lose a customer", icon: UserMinusIcon, slider: { label: "Sales lost per month", min: 500, max: 10000, step: 250, start: 2000, show: (v) => `$${v.toLocaleString("en-US")}` }, dateLabel: "From" },
  harbor: { title: "Harbor Lane pays", icon: HandCoinsIcon, dateLabel: "Paid on" },
};

function toScenario(it: Item): ScenarioInput | null {
  switch (it.kind) {
    case "hire":
    case "lose":
      return { type: "add_recurring", amount_cents: -it.value * 100, cadence: "monthly", start: it.date };
    case "raise":
      return { type: "raise_payroll", percent: it.value, start: it.date };
    case "equipment":
      return { type: "one_off", amount_cents: -it.value * 100, on: it.date };
    case "late":
      return it.invoiceId ? { type: "delay_receivable", invoice_id: it.invoiceId, days: it.value } : null;
    case "harbor":
      return it.invoiceId ? { type: "collect_receivable", invoice_id: it.invoiceId, on: it.date } : null;
  }
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

const addDays = (iso: string, days: number) => new Date(Date.parse(`${iso}T00:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);

const RISK = {
  safe: { label: "Safe", cls: "bg-good-soft text-good-ink", note: "No week ends below your cushion." },
  tight: { label: "Tight", cls: "bg-attn-soft text-attn-ink", note: "Below your cushion, but no deeper than your forecast already is." },
  risky: { label: "Risky", cls: "bg-risk-soft text-risk-ink", note: "Deeper below your cushion than your forecast already is." },
};

/** What-if as a playground: preset cards, live sliders, up to three stacked scenarios, the engine's result on top. */
export function Playground({ today }: { today: string }) {
  const forecast = useForecast();
  const close = useMonthClose();
  const [stack, setStack] = useState<Item[]>([]);
  const [nextId, setNextId] = useState(1);
  const harbor = forecast.data?.at_risk_receivables[0];
  const lateInvoices: Invoice[] = (close.data?.receivables.rows ?? [])
    .filter((r) => r.invoice.ref !== harbor?.invoice.ref)
    .map((r) => ({ id: Number(r.invoice.ref.split(":")[1]), label: `${r.number} · ${r.counterparty.label ?? ""}` }));

  const scenarios = stack.map(toScenario).filter((s): s is ScenarioInput => s !== null);
  const live = useDebounced(scenarios, 250);
  const result = useWhatIf(live, true, true);
  const r = result.data;
  const gap = r?.scenario_gap;
  const low = gap ? r?.weeks[gap.low_week - 1] : undefined;
  const risk = !r ? null : !gap ? RISK.safe : r.base_gap && gap.amount_cents <= r.base_gap.amount_cents ? RISK.tight : RISK.risky;

  function add(kind: Kind) {
    const p = PRESETS[kind];
    const invoiceId = kind === "harbor" ? (harbor ? Number(harbor.invoice.ref.split(":")[1]) : undefined) : kind === "late" ? lateInvoices[0]?.id : undefined;
    setStack((s) => [...s, { id: nextId, kind, value: p.slider?.start ?? 0, date: today, invoiceId }]);
    setNextId((n) => n + 1);
  }
  const update = (id: number, patch: Partial<Item>) => setStack((s) => s.map((it) => (it.id === id ? { ...it, ...patch } : it)));
  const full = stack.length >= MAX_STACK;

  return (
    <div className="space-y-5">
      <section aria-label="Scenarios to try">
        <p className="text-[15px] text-ink-2">Try a change and watch your next 13 weeks. Stack up to {MAX_STACK}.</p>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {(Object.keys(PRESETS) as Kind[]).map((k) => {
            const p = PRESETS[k];
            const unavailable = (k === "harbor" && !harbor) || (k === "late" && lateInvoices.length === 0);
            return (
              <button key={k} type="button" onClick={() => add(k)} disabled={full || unavailable}
                className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-3 text-left text-sm font-medium text-ink hover:border-brand disabled:opacity-50">
                <p.icon className="size-4 shrink-0 text-brand-ink" /> {p.title}
              </button>
            );
          })}
        </div>
      </section>

      {stack.length > 0 && (
        <ul className="space-y-2" aria-label="Your scenarios">
          {stack.map((it) => {
            const p = PRESETS[it.kind];
            return (
              <li key={it.id} className="rounded-xl border border-dashed border-attn/60 bg-attn-soft/30 p-3" aria-label={p.title}>
                <div className="flex items-center justify-between gap-2">
                  <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <p.icon className="size-4 text-brand-ink" /> {p.title}
                    <span className="rounded-full bg-attn-soft px-2 py-0.5 text-[11px] font-medium text-attn-ink">Assumption</span>
                  </p>
                  <button type="button" onClick={() => setStack((s) => s.filter((x) => x.id !== it.id))} aria-label={`Remove ${p.title}`}
                    className="rounded-full p-1 text-ink-3 hover:bg-sunken hover:text-ink">
                    <XIcon className="size-4" />
                  </button>
                </div>
                <div className="mt-2 grid gap-3 sm:grid-cols-2">
                  {p.slider && (
                    <label className="text-xs text-ink-2">
                      <span className="flex justify-between"><span>{p.slider.label}</span><span className="num font-semibold text-ink">{p.slider.show(it.value)}</span></span>
                      <input type="range" min={p.slider.min} max={p.slider.max} step={p.slider.step} value={it.value}
                        onChange={(e) => update(it.id, { value: Number(e.target.value) })} className="mt-1 w-full accent-[var(--color-brand)]"
                        aria-label={`${p.title}: ${p.slider.label}`} />
                    </label>
                  )}
                  {it.kind === "late" && (
                    <label className="text-xs text-ink-2">Invoice
                      <select value={it.invoiceId} onChange={(e) => update(it.id, { invoiceId: Number(e.target.value) })}
                        className="mt-1 block h-9 w-full rounded-lg border border-line-strong bg-surface px-2 text-sm text-ink">
                        {lateInvoices.map((inv) => <option key={inv.id} value={inv.id}>{inv.label}</option>)}
                      </select>
                    </label>
                  )}
                  {p.dateLabel && (
                    <label className="text-xs text-ink-2">{p.dateLabel}
                      <input type="date" min={today} max={addDays(today, 90)} value={it.date}
                        onChange={(e) => e.target.value && update(it.id, { date: e.target.value })}
                        className="mt-1 block h-9 w-full rounded-lg border border-line-strong bg-surface px-2 text-sm text-ink"
                        aria-label={`${p.title}: ${p.dateLabel}`} />
                    </label>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {result.isError && stack.length > 0 && (
        <p role="alert" className="text-sm text-risk-ink">{result.error.message}</p>
      )}

      {stack.length > 0 && (
        <section className="space-y-4 rounded-[var(--radius-panel)] border border-line bg-surface p-4 md:p-5" aria-label="Result">
          {!r ? <Skeleton className="h-16" /> : (
            <div className="space-y-1" data-testid="playground-result">
              <p className="flex flex-wrap items-center gap-2 text-[17px] font-medium text-ink">
                {risk && <span className={`rounded-full px-2.5 py-0.5 text-sm font-semibold ${risk.cls}`}>{risk.label}</span>}
                <span data-testid="playground-lowest">
                  {gap && low ? `Lowest point: ${formatDay(low.start)}, ${formatCents(gap.amount_cents, r.currency)} below your cushion` : "Cash stays above your cushion every week"}
                </span>
              </p>
              {risk && <p className="text-sm text-ink-2">{risk.note}</p>}
              {gap && (
                <Button asChild variant="secondary" size="sm" className="mt-2">
                  <Link href={whatIfHref(live, "financing")}><LandmarkIcon /> Compare ways to cover the gap</Link>
                </Button>
              )}
            </div>
          )}
          {r && <WhatIfLegend buffer={r.min_cash_buffer_cents} currency={r.currency} />}
          {r ? <WhatIfChart weeks={r.weeks} buffer={r.min_cash_buffer_cents} currency={r.currency} /> : <Skeleton className="h-[250px]" />}
          {r && <Assumptions items={r.assumptions} currency={r.currency} />}
        </section>
      )}
      {stack.length === 0 && (
        <p className="flex items-center gap-2 text-sm text-ink-3"><BanknoteIcon className="size-4" /> Nothing in your books changes. Pick a card to start.</p>
      )}
    </div>
  );
}
