"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import type { Schemas } from "@/lib/api/client";
import { formatCents, formatCentsCompact, formatDay } from "@/lib/money";

type Week = Schemas["ForecastWeekOut"];
type Row = Week & { name: string };

const GOOD = "var(--color-good)";
const RISK = "var(--color-risk)";
const INK_3 = "#6f7a90";
const LABEL_ROOM = 80_000; // cents of space under the lowest bar for its label

type LabelArgs = { x?: number | string; y?: number | string; width?: number | string; height?: number | string; index?: number };

function WeekTooltip({ active, payload, currency }: TooltipContentProps & { currency: string }) {
  const row = payload?.[0]?.payload as Row | undefined;
  if (!active || !row) return null;
  return (
    <div className="min-w-[200px] rounded-lg border border-line bg-surface px-3 py-2.5 text-xs shadow-lg">
      <p className="font-semibold text-ink">
        Week {row.week}, {formatDay(row.start)} to {formatDay(row.end)}
      </p>
      <dl className="num mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-ink-2">
        <dt>Money in</dt>
        <dd className="text-right">{formatCents(row.inflows_cents, currency, { signed: true })}</dd>
        <dt>Money out</dt>
        <dd className="text-right">{formatCents(row.outflows_cents, currency)}</dd>
        <dt className="font-medium text-ink">Closing cash</dt>
        <dd className={`text-right font-semibold ${row.below_buffer ? "text-risk-ink" : "text-ink"}`}>
          {formatCents(row.closing_cents, currency)}
        </dd>
      </dl>
      <p className={`mt-2 font-medium ${row.below_buffer ? "text-risk-ink" : "text-good-ink"}`}>
        {row.below_buffer ? "Below your cushion" : "Above your cushion"}
      </p>
      <p className="mt-1 text-ink-3">Select the bar to see every line.</p>
    </div>
  );
}

/** Weekly closing cash for 13 weeks against the minimum buffer. Values stay integer cents. */
export function ForecastChart({
  weeks,
  buffer,
  currency,
  onSelectWeek,
}: {
  weeks: Week[];
  buffer: number;
  currency: string;
  onSelectWeek: (week: number) => void;
}) {
  const rows: Row[] = weeks.map((w) => ({ ...w, name: String(w.week) }));
  const floor = Math.min(0, ...weeks.map((w) => w.closing_cents)) - LABEL_ROOM;

  const negativeLabel = ({ x, y, width, height, index }: LabelArgs) => {
    const row = index === undefined ? undefined : rows[index];
    if (!row || row.closing_cents >= 0) return null;
    const cx = Number(x) + Number(width) / 2;
    const bottom = Number(y) + Math.max(Number(height), 0);
    return (
      <text x={cx} y={bottom + 14} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--color-risk-ink)" className="num">
        {formatCentsCompact(row.closing_cents, currency)}
      </text>
    );
  };

  return (
    <div className="h-[250px] w-full md:h-[320px]">
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 720, height: 320 }}>
        <BarChart data={rows} margin={{ top: 18, right: 8, bottom: 6, left: 0 }} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke="var(--color-line)" />
          <ReferenceArea y1={floor} y2={buffer} fill="var(--color-risk-soft)" fillOpacity={0.7} ifOverflow="extendDomain" />
          <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fill: INK_3, fontSize: 11 }} interval={0} />
          <YAxis
            tickFormatter={(v: number) => formatCentsCompact(v, currency)}
            tickLine={false}
            axisLine={false}
            tick={{ fill: INK_3, fontSize: 11 }}
            width={48}
            domain={[floor, "auto"]}
            allowDecimals={false}
          />
          <ReferenceLine y={0} stroke="var(--color-line-strong)" />
          <ReferenceLine
            y={buffer}
            stroke="var(--color-ink-2)"
            strokeDasharray="5 4"
          />
          <Tooltip cursor={{ fill: "var(--color-sunken)" }} content={(props) => <WeekTooltip {...props} currency={currency} />} />
          <Bar dataKey="closing_cents" isAnimationActive={false} radius={4} maxBarSize={40} onClick={(_, index) => onSelectWeek(rows[index].week)} className="cursor-pointer">
            {rows.map((r) => (
              <Cell key={r.week} fill={r.below_buffer ? RISK : GOOD} stroke="var(--color-surface)" strokeWidth={1} />
            ))}
            <LabelList dataKey="closing_cents" content={(props) => negativeLabel(props as LabelArgs)} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
