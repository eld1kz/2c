"use client";

import { ChevronDownIcon } from "lucide-react";
import { useState } from "react";

import { EvidenceChip } from "@/components/evidence/evidence-chip";
import { Money } from "@/components/money";
import type { Schemas } from "@/lib/api/client";
import { formatCents, formatDay } from "@/lib/money";
import { Help } from "@/components/glossary/help";

/** "You can safely spend $X this week": cash − your cushion − bills due in 7 days, from the engine. */
export function SafeToSpend({ safe, currency }: { safe: Schemas["SafeToSpendOut"]; currency: string }) {
  const [open, setOpen] = useState(false);
  const nothing = safe.amount_cents <= 0;
  return (
    <section className="rounded-[var(--radius-panel)] border border-line bg-surface p-4 md:p-5" aria-labelledby="safe-title">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-start justify-between gap-3 text-left">
        <div>
          <h2 id="safe-title" className="text-[15px] font-semibold">
            {nothing ? "Nothing is safe to spend this week" : <>You can safely spend <Money cents={safe.amount_cents} currency={currency} /> this week</>}
          </h2>
          <p className="mt-1 text-sm text-ink-2">
            {nothing
              ? `This week's bills would take you ${formatCents(safe.short_by_cents, currency)} below your cushion.`
              : "Without touching your cushion, even if no money comes in."}
          </p>
        </div>
        <ChevronDownIcon className={`mt-1 size-4 shrink-0 text-ink-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <dl className="mt-3 divide-y divide-line border-t border-line text-sm">
          <div className="flex items-center justify-between gap-3 py-2">
            <dt className="flex flex-wrap items-center gap-1.5">
              Cash now {safe.accounts.map((a) => <EvidenceChip key={a.ref} evidence={a} />)}
            </dt>
            <dd><Money cents={safe.cash_cents} currency={currency} /></dd>
          </div>
          <div className="flex justify-between gap-3 py-2">
            <dt className="flex items-center gap-1">Your cushion (money you keep for surprises) <Help term="cushion" /></dt>
            <dd><Money cents={-safe.cushion_cents} currency={currency} /></dd>
          </div>
          {safe.bills.map((b) => (
            <div key={`${b.source.ref}-${b.date}`} className="flex items-center justify-between gap-3 py-2">
              <dt className="flex flex-wrap items-center gap-1.5 text-ink-2">
                Bill on {formatDay(b.date)} <EvidenceChip evidence={b.source} /> <Help term="bill" />
              </dt>
              <dd><Money cents={-b.amount_cents} currency={currency} /></dd>
            </div>
          ))}
          <div className="flex justify-between gap-3 py-2 font-semibold">
            <dt className="flex items-center gap-1">Safe to spend <Help term="safe_to_spend" /></dt>
            <dd><Money cents={safe.amount_cents} currency={currency} tone={nothing ? "risk" : "good"} /></dd>
          </div>
        </dl>
      )}
    </section>
  );
}
