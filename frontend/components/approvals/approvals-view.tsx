"use client";

import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import type { Schemas } from "@/lib/api/client";
import { useActions } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";

import { ApprovalCard } from "./approval-card";

type Action = Schemas["ActionOut"];

export function ApprovalsView() {
  const { data, isLoading, isError } = useActions();
  const [tab, setTab] = useState<"waiting" | "decided">("waiting");
  const [justDecided, setJustDecided] = useState<Action[]>([]);
  const executable = (data ?? []).filter((a) => a.tier === "EXECUTE");
  const decidedIds = new Set(justDecided.map((a) => a.id));
  const waiting = executable.filter((a) => a.status === "proposed" && !decidedIds.has(a.id));
  const decided = executable.filter((a) => a.status !== "proposed");

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold tracking-tight">Approvals</h1>
      <p className="mt-1 text-sm text-ink-3">
        The assistant can only propose. Nothing is paid or sent until an owner approves it here, and the payment policy checks it again before it runs.
      </p>

      <div className="mt-5 flex rounded-lg bg-sunken p-0.5 text-sm font-medium" role="tablist">
        {(
          [
            ["waiting", `Waiting (${waiting.length})`],
            ["decided", "Decided"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn("flex-1 rounded-md px-3 py-1.5", tab === key ? "bg-surface text-ink shadow-sm" : "text-ink-2")}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-5 space-y-4">
        {isLoading && <Skeleton className="h-64" />}
        {isError && <p className="text-sm text-risk-ink">Approvals couldn&apos;t be loaded. Refresh the page to try again.</p>}
        {tab === "waiting" && (
          <>
            {justDecided.map((a) => (
              <ApprovalCard key={a.id} action={a} />
            ))}
            {waiting.map((a) => (
              <ApprovalCard key={a.id} action={a} onDecided={(result) => setJustDecided((d) => [result, ...d])} />
            ))}
            {data && waiting.length === 0 && justDecided.length === 0 && (
              <p className="rounded-xl border border-dashed border-line-strong px-4 py-8 text-center text-sm text-ink-3">
                Nothing is waiting. When the assistant proposes a reminder, payment or loan application, it appears here.
              </p>
            )}
          </>
        )}
        {tab === "decided" &&
          (decided.length ? decided.map((a) => <ApprovalCard key={a.id} action={a} />) : data && <p className="text-sm text-ink-3">No decisions yet.</p>)}
      </div>
    </div>
  );
}
