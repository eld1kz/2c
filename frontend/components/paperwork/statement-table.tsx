import { Help } from "@/components/glossary/help";
import { cn } from "@/lib/cn";
import { formatCents } from "@/lib/money";
import type { StatementRow } from "@/lib/statements";

/** A cash-basis statement: one row per line, one column per period. Figures are the API's cents. */
export function StatementTable({ columns, rows, currency, label }: { columns: string[]; rows: StatementRow[]; currency: string; label: string }) {
  return (
    <div className="-mx-4 overflow-x-auto md:mx-0 print:mx-0 print:overflow-visible">
      <table className={cn("num w-full text-sm", columns.length > 1 && "min-w-[560px] print:min-w-0")} aria-label={label}>
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-3">
            <th className="px-4 py-2 font-medium md:px-2">
              <span className="sr-only">Line</span>
            </th>
            {columns.map((c) => (
              <th key={c} className="px-4 py-2 text-right font-medium md:px-2">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={`${row.label}-${i}`}
              className={cn(
                "border-b border-line last:border-0",
                row.kind === "section" && "border-0",
                row.kind === "grand" && "border-t-2 border-t-line-strong",
              )}
            >
              <th
                scope="row"
                className={cn(
                  "min-w-36 px-4 py-1.5 text-left md:px-2",
                  row.kind === "section" ? "pt-4 text-xs font-semibold tracking-wide text-ink-3 uppercase" : "font-normal",
                  !row.kind && "pl-7 text-ink-2 md:pl-5",
                  (row.kind === "total" || row.kind === "grand") && "font-semibold text-ink",
                )}
              >
                {row.label}
                {row.term && <> <Help term={row.term} /></>}
              </th>
              {row.values.map((v, j) => (
                <td key={j} className={cn("px-4 py-1.5 text-right whitespace-nowrap md:px-2", row.kind ? "font-semibold text-ink" : "text-ink-2")}>
                  {v === null ? "" : formatCents(v, currency)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
