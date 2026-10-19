"use client";

import { LoaderCircleIcon } from "lucide-react";
import { useState } from "react";

import { Answer } from "@/components/chat/answer";
import { WhatIfPanel } from "@/components/whatif/whatif-panel";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useAfford } from "@/lib/api/hooks";
import type { components } from "@/lib/api/schema";
import { formatDay } from "@/lib/money";
import type { ScenarioInput } from "@/lib/scenarios";

const EXAMPLES = ["Hire a barista at $2,500/month from November?", "Give staff a 3% raise?", "Buy a $3,000 espresso machine?"];

const VERDICT: Record<string, { label: string; cls: string }> = {
  yes: { label: "Yes", cls: "bg-good-soft text-good-ink" },
  not_yet: { label: "Not yet", cls: "bg-attn-soft text-attn-ink" },
  no: { label: "No", cls: "bg-risk-soft text-risk-ink" },
};

type Afford = components["schemas"]["AffordOut"];
type Fix = components["schemas"]["AffordFixOut"];

/** "Yes from Nov 1" · "Not yet: safe from Dec 6" · "No: already short from Nov 5". */
function detail(verdict: string, requested: string | null | undefined, earliest: string | null | undefined,
  shortFrom: string | null | undefined): string {
  if (verdict === "yes") return requested ? `from ${formatDay(requested)}` : "";
  if (verdict === "not_yet") return earliest ? `safe from ${formatDay(earliest)}` : "";
  return shortFrom ? `already short from ${formatDay(shortFrom)}` : "nothing in the next 13 weeks is safe";
}

const ifFixes = (fixes: Fix[]) =>
  "If " + fixes.map((f) => `${f.name} ${f.kind === "reminder" ? "pays" : "agrees"}`).join(" and ");

function VerdictLine({ label, verdict, text }: { label: string; verdict: string; text: string }) {
  const v = VERDICT[verdict];
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="text-ink-2">{label}:</span>{" "}
      <span className={`rounded-full px-2.5 py-0.5 font-semibold ${v.cls}`}>{v.label}</span>
      {text && <span className="text-ink-2">{" "}— {text}</span>}
    </li>
  );
}

function Verdicts({ r }: { r: Afford }) {
  if (!r.verdict) return null;
  const fixed = r.with_fixes;
  return (
    <div className="space-y-1.5 text-sm">
      <ul className="space-y-1.5" aria-label="Verdicts">
        <VerdictLine label="Today" verdict={r.verdict} text={detail(r.verdict, r.requested_start, r.earliest_safe_start, r.short_from)} />
        {fixed && (
          <VerdictLine label={ifFixes(fixed.fixes)} verdict={fixed.verdict}
            text={detail(fixed.verdict, r.requested_start, fixed.earliest_safe_start, fixed.short_from)} />
        )}
      </ul>
      <p className="text-xs text-ink-3">
        From your 13-week forecast. Safe means no week ends below your cushion.
        {fixed && " The second line assumes the actions prepared on Today work out; nothing is sent until you approve it."}
      </p>
    </div>
  );
}

/** One question → the agent maps it to a what-if → the engine's verdict, a cited sentence and a chart. */
export function AffordBox() {
  const [question, setQuestion] = useState("");
  const ask = useAfford();
  const r = ask.data;

  function submit(q: string) {
    if (q.trim().length >= 3 && !ask.isPending) ask.mutate(q.trim());
  }

  return (
    <section className="rounded-[var(--radius-panel)] border border-line bg-surface p-4 md:p-5" aria-labelledby="afford-title">
      <h2 id="afford-title" className="text-[15px] font-semibold">Can I afford it?</h2>
      <form className="mt-3 flex gap-2" onSubmit={(e) => (e.preventDefault(), submit(question))}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={300}
          placeholder={EXAMPLES[0]}
          aria-label="Can I afford it?"
          className="h-10 min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-3 text-sm outline-none focus:border-brand"
        />
        <Button type="submit" disabled={ask.isPending || question.trim().length < 3}>
          {ask.isPending ? <LoaderCircleIcon className="animate-spin" /> : null}
          Check
        </Button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((q) => (
          <button key={q} type="button" onClick={() => (setQuestion(q), submit(q))} disabled={ask.isPending}
            className="rounded-full bg-sunken px-2.5 py-1 text-xs text-ink-2 hover:text-ink disabled:opacity-50">
            {q}
          </button>
        ))}
      </div>
      {ask.isPending && <p className="mt-3 text-sm text-ink-3">Checking it against your next 13 weeks…</p>}
      {ask.isError && (
        <p role="alert" className="mt-3 text-sm text-risk-ink">
          {ask.error instanceof ApiError ? ask.error.message : "That couldn't be checked. Try again."}
        </p>
      )}
      {r && !ask.isPending && (
        <div className="mt-4 space-y-3" data-testid="afford-result">
          <Verdicts r={r} />
          <Answer message={r.message} citations={r.citations} warnings={r.warnings} />
          {r.scenarios.length > 0 && <WhatIfPanel scenarios={r.scenarios as ScenarioInput[]} />}
        </div>
      )}
    </section>
  );
}
