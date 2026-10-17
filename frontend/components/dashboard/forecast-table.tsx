import type { Schemas } from "@/lib/api/client";
import { formatCents, formatDay } from "@/lib/money";

/** The chart's data as a table (accessible view, and exact figures). */
export function ForecastTable({ weeks, currency, onSelectWeek }: { weeks: Schemas["ForecastWeekOut"][]; currency: string; onSelectWeek: (week: number) => void }) {
  return (
    <div className="-mx-4 overflow-x-auto md:mx-0">
      <table className="num w-full min-w-[520px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-3">
            <th className="px-4 py-2 font-medium md:px-2">Week</th>
            <th className="px-2 py-2 text-right font-medium">Money in</th>
            <th className="px-2 py-2 text-right font-medium">Money out</th>
            <th className="px-4 py-2 text-right font-medium md:px-2">Closing</th>
          </tr>
        </thead>
        <tbody>
          {weeks.map((w) => (
            <tr key={w.week} onClick={() => onSelectWeek(w.week)} className="cursor-pointer border-b border-line last:border-0 hover:bg-sunken">
              <td className="px-4 py-2 md:px-2">
                <button className="text-left" onClick={() => onSelectWeek(w.week)}>
                  <span className="font-medium">W{w.week}</span> <span className="text-ink-3">{formatDay(w.start)}</span>
                </button>
              </td>
              <td className="px-2 py-2 text-right text-ink-2">{formatCents(w.inflows_cents, currency, { signed: true })}</td>
              <td className="px-2 py-2 text-right text-ink-2">{formatCents(w.outflows_cents, currency)}</td>
              <td className={`px-4 py-2 text-right font-medium md:px-2 ${w.below_buffer ? "text-risk-ink" : "text-ink"}`}>
                {formatCents(w.closing_cents, currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
