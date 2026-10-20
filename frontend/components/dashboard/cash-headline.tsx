import type { Schemas } from "@/lib/api/client";
import { weekList } from "@/lib/labels";
import { formatCents, formatDay } from "@/lib/money";

type Forecast = Schemas["ForecastOut"];

/** The forecast in one sentence, built from engine fields only (no arithmetic here). */
export function CashHeadline({ forecast }: { forecast: Forecast }) {
  const { gap, lowest, weeks, currency, min_cash_buffer_cents: buffer } = forecast;
  const negative = weeks.filter((w) => w.closing_cents < 0).map((w) => w.week);
  const low = weeks[lowest.week - 1];
  return (
    <div>
      <h1 className="max-w-[32ch] text-[26px] leading-[1.2] font-semibold tracking-tight text-ink md:text-[34px]">
        {gap ? (
          <>
            Cash falls below your {formatCents(buffer, currency, { dropZeroCents: true })} cushion on {formatDay(gap.start)}
            {negative.length > 0 && <> and goes negative in {weekList(negative)}</>}.
          </>
        ) : (
          <>Cash stays above your {formatCents(buffer, currency, { dropZeroCents: true })} cushion for the next {weeks.length} weeks.</>
        )}
      </h1>
      <p className="mt-3 max-w-[60ch] text-[15px] leading-relaxed text-ink-2">
        Lowest point:{" "}
        <span className={`num font-semibold ${low.below_buffer ? "text-risk-ink" : "text-ink"}`}>
          {formatCents(lowest.closing_cents, currency)}
        </span>{" "}
        in week {lowest.week} ({formatDay(low.start)} to {formatDay(low.end)})
        {gap && (
          <>
            , which is <span className="num font-semibold text-ink">{formatCents(gap.amount_cents, currency)}</span> short of your cushion
          </>
        )}
        .
      </p>
    </div>
  );
}
