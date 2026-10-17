"use client";

import { ChevronRightIcon } from "lucide-react";
import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useAuditEvents, useMe } from "@/lib/api/hooks";
import { actorLabel, eventLabel, eventTone, GROUPS } from "@/lib/audit";
import { cn } from "@/lib/cn";

import { VerifyPanel } from "./verify-panel";

const TONE = { good: "bg-good", risk: "bg-risk", plain: "bg-line-strong" };
const PAGE = 50;

function when(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false }) + " UTC";
}

export function AuditView() {
  const { data, isLoading, isError } = useAuditEvents();
  const me = useMe().data;
  const [group, setGroup] = useState<keyof typeof GROUPS>("All");
  const [open, setOpen] = useState<number | null>(null);
  const [shown, setShown] = useState(PAGE);
  const rows = (data ?? []).filter((e) => GROUPS[group](e.event_type));

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Audit log</h1>
        <p className="mt-1 text-sm text-ink-3">
          Every sign-in, question, tool call, proposal, decision and refusal, in order. Events can be added, never changed or removed.
        </p>
      </div>

      <VerifyPanel />

      <section aria-labelledby="events-title">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="events-title" className="text-[15px] font-semibold">
            Events {data && <span className="num font-normal text-ink-3">({rows.length.toLocaleString("en-US")})</span>}
          </h2>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter events">
            {Object.keys(GROUPS).map((g) => (
              <button
                key={g}
                aria-pressed={group === g}
                onClick={() => {
                  setGroup(g);
                  setShown(PAGE);
                }}
                className={cn("rounded-full border px-3 py-1 text-xs font-medium", group === g ? "border-ink bg-ink text-white" : "border-line bg-surface text-ink-2")}
              >
                {g}
              </button>
            ))}
          </div>
        </div>
        {isLoading && <Skeleton className="mt-4 h-64" />}
        {isError && <p className="mt-4 text-sm text-risk-ink">The audit log couldn&apos;t be loaded. Refresh to try again.</p>}
        <ol className="mt-3 divide-y divide-line overflow-hidden rounded-[var(--radius-panel)] border border-line bg-surface">
          {rows.slice(0, shown).map((e) => (
            <li key={e.seq}>
              <button
                onClick={() => setOpen(open === e.seq ? null : e.seq)}
                aria-expanded={open === e.seq}
                className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-sunken/50"
              >
                <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", TONE[eventTone(e.event_type)])} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-ink">{eventLabel(e.event_type)}</span>
                  <span className="block text-xs text-ink-3">
                    #{e.seq}, {when(e.ts)}, {actorLabel(e.actor, me?.user.id)}
                  </span>
                </span>
                <span className="hidden font-mono text-xs text-ink-3 sm:block" title={e.hash}>
                  {e.hash.slice(0, 10)}
                </span>
                <ChevronRightIcon className={cn("mt-0.5 size-4 shrink-0 text-ink-3 transition-transform", open === e.seq && "rotate-90")} />
              </button>
              {open === e.seq && (
                <div className="space-y-2 bg-sunken/50 px-4 py-3 text-xs">
                  <p className="break-all text-ink-2">
                    <span className="text-ink-3">Hash</span> {e.hash}
                  </p>
                  <p className="break-all text-ink-2">
                    <span className="text-ink-3">Previous</span> {e.prev_hash}
                  </p>
                  <pre className="overflow-x-auto rounded-md bg-surface p-3 whitespace-pre-wrap text-ink-2">{JSON.stringify(e.payload, null, 2)}</pre>
                </div>
              )}
            </li>
          ))}
          {data && rows.length === 0 && <li className="px-4 py-6 text-sm text-ink-3">No events in this group yet.</li>}
        </ol>
        {rows.length > shown && (
          <button onClick={() => setShown((n) => n + PAGE)} className="mt-3 w-full rounded-lg border border-line bg-surface py-2 text-sm font-medium text-ink-2 hover:bg-sunken">
            Show {Math.min(PAGE, rows.length - shown)} older events
          </button>
        )}
      </section>
    </div>
  );
}
