"use client";

import { useState } from "react";

import type { Schemas } from "@/lib/api/client";
import { formatDay, formatCents } from "@/lib/money";

type Future = Schemas["FutureOut"];
type Fix = Schemas["FutureFixOut"];

const fixText = (f: Fix) => `${f.name} ${f.kind === "reminder" ? "pays" : "agrees"}`;

/**
 * "Watch your future fix itself": the 13 weekly closings with every approved fix (green above the
 * cushion, red below), the cushion line, and a dashed ghost line for the fixes not approved yet. All
 * figures and sentences come from GET /today (the engine). While `hold` is true (an approval sheet is
 * open) the old curve stays on screen, so the change animates when the owner comes back to it.
 */
export function FutureChart({ future, currency, hold }: { future: Future; currency: string; hold: boolean }) {
  const [shown, setShown] = useState(future);
  if (!hold && shown !== future) setShown(future);
  const f = shown;

  const values = [0, f.cushion_cents, ...f.weeks.flatMap((w) => [w.closing_cents, w.pending_closing_cents ?? w.closing_cents])];
  const top = Math.max(...values);
  const bottom = Math.min(...values);
  const y = (v: number) => ((top - v) / (top - bottom || 1)) * 100; // % from the top of the plot
  const n = f.weeks.length;
  const ghost = f.pending.length > 0
    ? f.weeks.map((w, i) => `${(i + 0.5) * (100 / n)},${y(w.pending_closing_cents ?? w.closing_cents)}`).join(" ")
    : null;

  return (
    <section className="rounded-[var(--radius-panel)] border border-line bg-surface p-4 md:p-5" aria-labelledby="future-title">
      <h2 id="future-title" className="text-xs font-medium text-ink-3">Your next 13 weeks</h2>
      <div aria-live="polite">
        <p className="mt-1 text-[17px] leading-snug font-medium text-ink" data-testid="future-headline">{f.headline}</p>
        <p className="text-sm text-ink-2">{f.detail}</p>
      </div>

      <div className="relative mt-4 h-36" role="img" aria-label={`Weekly cash for 13 weeks. ${f.headline} ${f.detail}`}>
        <div className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }}>
          {f.weeks.map((w) => {
            const a = y(Math.max(w.closing_cents, 0));
            const b = y(Math.min(w.closing_cents, 0));
            return (
              <div key={w.week} className="relative">
                <div
                  data-testid="future-bar"
                  data-below={w.below_cushion}
                  title={`Week ${w.week} (${formatDay(w.start)}): ${formatCents(w.closing_cents, currency)}`}
                  className={`absolute inset-x-[18%] rounded-sm transition-[top,height,background-color] duration-700 ease-out motion-reduce:transition-none ${w.below_cushion ? "bg-risk" : "bg-good"}`}
                  style={{ top: `${a}%`, height: `max(${b - a}%, 2px)` }}
                />
              </div>
            );
          })}
        </div>
        <div className="pointer-events-none absolute inset-x-0 border-t border-dashed border-ink-3" style={{ top: `${y(f.cushion_cents)}%` }}>
          <span className="absolute right-0 -translate-y-full bg-surface/80 px-1 text-[11px] text-ink-3">
            Cushion {formatCents(f.cushion_cents, currency)}
          </span>
        </div>
        {bottom < 0 && <div className="pointer-events-none absolute inset-x-0 border-t border-line-strong" style={{ top: `${y(0)}%` }} />}
        {ghost && (
          <svg className="pointer-events-none absolute inset-0 size-full overflow-visible" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
            <polyline points={ghost} fill="none" stroke="var(--color-brand)" strokeWidth={2} strokeDasharray="5 4"
              vectorEffect="non-scaling-stroke" data-testid="future-ghost" />
          </svg>
        )}
      </div>
      <div className="mt-1 grid text-[11px] text-ink-3" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }} aria-hidden>
        {f.weeks.map((w) => (
          <span key={w.week} className="text-center whitespace-nowrap">{(w.week - 1) % 4 === 0 ? formatDay(w.start) : ""}</span>
        ))}
      </div>

      <ul className="mt-3 space-y-1 text-xs text-ink-2">
        <li className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-good" /> Above your cushion</span>
          <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-risk" /> Below it</span>
        </li>
        {f.applied.length > 0 && <li>Includes the fixes you approved: {f.applied.map(fixText).join(", ")}.</li>}
        {f.pending.length > 0 && f.pending_headline && (
          <li className="flex items-start gap-1.5">
            <svg className="mt-1.5 h-0.5 w-4 shrink-0" aria-hidden><line x1="0" y1="1" x2="16" y2="1" stroke="var(--color-brand)" strokeWidth={2} strokeDasharray="4 3" /></svg>
            <span>Pending fixes ({f.pending.map(fixText).join(", ")}): {f.pending_headline}</span>
          </li>
        )}
      </ul>
      <p className="mt-2 text-[11px] text-ink-3">From your forecast, assuming approved fixes work out. Nothing is sent until you approve it.</p>
    </section>
  );
}
