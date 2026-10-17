import type { Schemas } from "@/lib/api/client";
import { formatCents, formatDay } from "@/lib/money";

/** The before/after chart as a table (accessible view, and exact figures). */
export function WhatIfTable({ weeks, currency }: { weeks: Schemas["WhatIfWeekOut"][]; currency: string }) {
  return (
    <div className="-mx-4 overflow-x-auto md:mx-0">
      <table className="num w-full min-w-[480px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-3">
            <th className="px-4 py-2 font-medium md:px-2">Week</th>
            <th className="px-2 py-2 text-right font-medium">Today&apos;s forecast</th>
            <th className="px-2 py-2 text-right font-medium">If the assumption holds</th>
            <th className="px-4 py-2 text-right font-medium md:px-2">Change</th>
          </tr>
        </thead>
        <tbody>
          {weeks.map((w) => (
            <tr key={w.week} className="border-b border-line last:border-0">
              <td className="px-4 py-2 md:px-2">
                <span className="font-medium">W{w.week}</span> <span className="text-ink-3">{formatDay(w.start)}</span>
              </td>
              <td className={`px-2 py-2 text-right ${w.base_below_buffer ? "text-risk-ink" : "text-ink-2"}`}>{formatCents(w.base_closing_cents, currency)}</td>
              <td className={`px-2 py-2 text-right font-medium ${w.scenario_below_buffer ? "text-risk-ink" : "text-ink"}`}>
                {formatCents(w.scenario_closing_cents, currency)}
              </td>
              <td className="px-4 py-2 text-right text-ink-2 md:px-2">{formatCents(w.change_cents, currency, { signed: true })}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
