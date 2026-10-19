"use client";

import { PlusIcon } from "lucide-react";
import { useState } from "react";

import { EvidenceChip } from "@/components/evidence/evidence-chip";
import { Money } from "@/components/money";
import { AffordBox } from "@/components/today/afford-box";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe, useTeam } from "@/lib/api/hooks";

const input = "h-10 rounded-lg border border-line-strong bg-surface px-3 text-sm outline-none focus:border-brand";

/** "$742" or "742.50" → "$742.50"; anything else → null. Only reformats what was typed; the engine does the maths. */
function dollars(typed: string): string | null {
  const m = typed.trim().replace(/^\$/, "").replace(/,/g, "").match(/^(\d{1,6})(?:\.(\d{1,2}))?$/);
  if (!m || Number(m[1]) === 0 && !Number(m[2] ?? 0)) return null;
  return `$${Number(m[1]).toLocaleString("en-US")}.${(m[2] ?? "").padEnd(2, "0")}`;
}

/**
 * The team: a fixed, labelled breakdown of the payroll series (not a staff data model). Pay comes from
 * GET /team, which leaves it out for viewers. "+ Hire someone" and "Give a raise" open "Can I afford
 * it?" with the question filled in, so both engine verdicts appear here.
 */
export function TeamView() {
  const me = useMe();
  const { data, isError } = useTeam();
  const [check, setCheck] = useState<{ question: string; n: number } | null>(null);
  const [hireRole, setHireRole] = useState("Barista");
  const [hirePay, setHirePay] = useState("700");
  const [raiseFor, setRaiseFor] = useState<string | null>(null);
  const [raiseBy, setRaiseBy] = useState("50");
  if (isError) return <p className="text-sm text-risk-ink">The team couldn&apos;t be loaded. Refresh the page to try again.</p>;
  if (!data || !me.data) return <Skeleton className="h-96" />;
  const canAsk = me.data.user.role !== "viewer";

  function open(question: string) {
    setCheck((c) => ({ question, n: (c?.n ?? 0) + 1 }));
    requestAnimationFrame(() => document.getElementById("team-afford")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }
  const hire = dollars(hirePay);
  const raise = dollars(raiseBy);

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <header className="pt-2 md:pt-4">
        <h1 className="font-display text-[30px] leading-[1.15] font-medium tracking-[-0.01em] text-ink md:text-[38px]">Your team</h1>
        <p className="mt-2 text-[17px] text-ink-2">
          {data.people.length} people
          {data.weekly_total_cents !== null && data.weekly_total_cents !== undefined && (
            <>, <Money cents={data.weekly_total_cents} className="font-semibold text-ink" split />/week</>
          )}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-3">
          <span>A breakdown of your payroll payments{data.pay_visible ? "" : " (pay is visible to the owner and accountant)"}.</span>
          {data.payroll && <EvidenceChip evidence={data.payroll} />}
        </div>
        {!data.matches_payroll && data.pay_visible && (
          <p role="alert" className="mt-2 text-sm text-attn-ink">This list no longer adds up to the payroll in your books.</p>
        )}
      </header>

      <ul className="divide-y divide-line overflow-hidden rounded-[var(--radius-panel)] border border-line bg-surface" aria-label="Team">
        {data.people.map((p) => (
          <li key={p.name} className="space-y-3 px-5 py-4 md:px-6">
            <div className="flex items-center gap-4">
              <span aria-hidden className="flex size-11 shrink-0 items-center justify-center rounded-full bg-brand-soft font-display text-[15px] font-medium text-brand-ink">{p.initials}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-medium text-ink">{p.name}</span>
                <span className="block text-sm text-ink-2">{p.role}</span>
              </span>
              {p.weekly_pay_cents !== null && p.weekly_pay_cents !== undefined && (
                <span className="text-[15px] whitespace-nowrap text-ink"><Money cents={p.weekly_pay_cents} className="font-medium" />/week</span>
              )}
            </div>
            {canAsk && (raiseFor === p.name ? (
              <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => (e.preventDefault(), raise && open(`Give ${p.name} (${p.role}) a raise of ${raise}/week from today?`))}>
                <label className="flex items-center gap-2 text-sm text-ink-2">
                  Raise per week ($)
                  <input value={raiseBy} onChange={(e) => setRaiseBy(e.target.value)} inputMode="decimal" className={`${input} w-24`} aria-label={`Raise for ${p.name} per week`} />
                </label>
                <Button type="submit" size="sm" disabled={!raise}>Can I afford it?</Button>
              </form>
            ) : (
              <Button variant="secondary" size="sm" onClick={() => setRaiseFor(p.name)}>Give a raise</Button>
            ))}
          </li>
        ))}
      </ul>

      {canAsk && (
        <section className="rounded-[var(--radius-panel)] border border-dashed border-line-strong bg-surface p-5 md:p-6" aria-labelledby="hire-title">
          <h2 id="hire-title" className="flex items-center gap-1.5 text-[15px] font-semibold"><PlusIcon className="size-4" /> Hire someone</h2>
          <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => (e.preventDefault(), hire && hireRole.trim() && open(`Hire a ${hireRole.trim()} at ${hire}/week from today?`))}>
            <label className="text-sm text-ink-2">Role
              <input value={hireRole} onChange={(e) => setHireRole(e.target.value)} maxLength={40} className={`${input} mt-1 block w-44`} />
            </label>
            <label className="text-sm text-ink-2">Weekly pay ($)
              <input value={hirePay} onChange={(e) => setHirePay(e.target.value)} inputMode="decimal" className={`${input} mt-1 block w-28`} />
            </label>
            <Button type="submit" disabled={!hire || !hireRole.trim()}>Can I afford it?</Button>
          </form>
        </section>
      )}

      {canAsk && check && (
        <div id="team-afford" className="scroll-mt-20">
          <AffordBox key={check.n} initialQuestion={check.question} />
        </div>
      )}
    </div>
  );
}
