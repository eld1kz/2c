"use client";

import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from "recharts";

import type { Schemas } from "@/lib/api/client";
import { formatCents, formatCentsCompact, formatDay } from "@/lib/money";

type Week = Schemas["WhatIfWeekOut"];
type Row = Week & { name: string };

const BEFORE = "var(--color-line-strong)";
const GOOD = "var(--color-good)";
const RISK = "var(--color-risk)";
const INK_3 = "#6f7a90";

function WeekTooltip({ active, payload, currency }: TooltipContentProps & { currency: string }) {
  const row = payload?.[0]?.payload as Row | undefined;
  if (!active || !row) return null;
  return (
    <div className="min-w-[210px] rounded-lg border border-line bg-surface px-3 py-2.5 text-xs shadow-lg">
      <p className="font-semibold text-ink">
        Week {row.week}, {formatDay(row.start)} to {formatDay(row.end)}
      </p>
      <dl className="num mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-ink-2">
        <dt>Today&apos;s forecast</dt>
        <dd className={`text-right ${row.base_below_buffer ? "text-risk-ink" : ""}`}>{formatCents(row.base_closing_cents, currency)}</dd>
        <dt className="font-medium text-ink">If the assumption holds</dt>
        <dd className={`text-right font-semibold ${row.scenario_below_buffer ? "text-risk-ink" : "text-ink"}`}>
          {formatCents(row.scenario_closing_cents, currency)}
        </dd>
        <dt>Change</dt>
        <dd className="text-right">{formatCents(row.change_cents, currency, { signed: true })}</dd>
      </dl>
    </div>
  );
}

/** Closing cash per week: today's forecast (grey) next to the scenario (green above buffer, red below). */
export function WhatIfChart({ weeks, buffer, currency, compact = false }: { weeks: Week[]; buffer: number; currency: string; compact?: boolean }) {
  const rows: Row[] = weeks.map((w) => ({ ...w, name: String(w.week) }));
  return (
    <div className={compact ? "h-[180px] w-full" : "h-[250px] w-full md:h-[320px]"}>
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 720, height: compact ? 180 : 320 }}>
        <BarChart data={rows} margin={{ top: 12, right: 8, bottom: 6, left: 0 }} barCategoryGap="18%" barGap={1}>
          <CartesianGrid vertical={false} stroke="var(--color-line)" />
          <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fill: INK_3, fontSize: 11 }} interval={0} />
          <YAxis
            tickFormatter={(v: number) => formatCentsCompact(v, currency)}
            tickLine={false}
            axisLine={false}
            tick={{ fill: INK_3, fontSize: 11 }}
            width={48}
            allowDecimals={false}
          />
          <ReferenceLine y={0} stroke="var(--color-line-strong)" />
          <ReferenceLine y={buffer} stroke="var(--color-ink-2)" strokeDasharray="5 4" />
          <Tooltip cursor={{ fill: "var(--color-sunken)" }} content={(props) => <WeekTooltip {...props} currency={currency} />} />
          <Bar dataKey="base_closing_cents" name="Today's forecast" fill={BEFORE} isAnimationActive={false} radius={3} maxBarSize={22} />
          <Bar dataKey="scenario_closing_cents" name="If the assumption holds" isAnimationActive={false} radius={3} maxBarSize={22}>
            {rows.map((r) => (
              <Cell key={r.week} fill={r.scenario_below_buffer ? RISK : GOOD} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function WhatIfLegend({ buffer, currency }: { buffer: number; currency: string }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
      <li className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-sm bg-line-strong" aria-hidden /> Today&apos;s forecast
      </li>
      <li className="flex items-center gap-1.5">
        <span className="flex gap-px" aria-hidden>
          <span className="size-2.5 rounded-l-sm bg-good" />
          <span className="size-2.5 rounded-r-sm bg-risk" />
        </span>
        If the assumption holds (red: below your cushion)
      </li>
      <li className="flex items-center gap-1.5">
        <span className="w-4 border-t-2 border-dashed border-ink-2" aria-hidden /> {formatCents(buffer, currency, { dropZeroCents: true })} minimum buffer
      </li>
    </ul>
  );
}
