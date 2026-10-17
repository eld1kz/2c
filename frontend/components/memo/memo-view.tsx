"use client";

import { CircleAlertIcon, LoaderCircleIcon, RefreshCwIcon, SparklesIcon } from "lucide-react";

import { Answer } from "@/components/chat/answer";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useCfoMemo, useGenerateMemo, useMe } from "@/lib/api/hooks";
import { formatDate } from "@/lib/money";

function Notice({ tone, children }: { tone: "attn" | "risk"; children: React.ReactNode }) {
  const cls = tone === "risk" ? "bg-risk-soft text-risk-ink" : "bg-attn-soft text-attn-ink";
  return (
    <p role="alert" className={`flex gap-2 rounded-lg px-3 py-2.5 text-sm ${cls}`}>
      <CircleAlertIcon className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

function failure(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "The memo couldn't be written. Check your connection and try again.";
}

/** This week's CFO memo: written by the assistant from engine facts, every figure cited, cached. */
export function MemoView() {
  const me = useMe();
  const memo = useCfoMemo();
  const generate = useGenerateMemo();
  const canWrite = !!me.data && me.data.user.role !== "viewer";
  const unsaved = generate.data?.memo && !generate.data.memo.generated_at ? generate.data.memo : null;
  const shown = unsaved ?? memo.data?.memo ?? null;
  const writing = generate.isPending;

  const button = canWrite && (
    <Button variant={shown ? "secondary" : "primary"} size={shown ? "sm" : "lg"} disabled={writing} onClick={() => generate.mutate()}>
      {writing ? <LoaderCircleIcon className="animate-spin" /> : shown ? <RefreshCwIcon /> : <SparklesIcon />}
      {writing ? "Writing the memo…" : shown ? "Write it again" : "Write this week's memo"}
    </Button>
  );

  return (
    <div className="max-w-3xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-ink-3">{me.data ? `Week of ${formatDate(me.data.as_of)}` : " "}</p>
          <h1 className="mt-1 text-[26px] leading-[1.2] font-semibold tracking-tight text-ink md:text-[30px]">Weekly CFO memo</h1>
        </div>
        {shown && button}
      </div>

      {generate.isError && <Notice tone="risk">{failure(generate.error)}</Notice>}
      {unsaved && (
        <Notice tone="risk">
          Some figures in this memo couldn&apos;t be checked against your records, so it wasn&apos;t saved. Write it again to get a fully
          cited memo.
        </Notice>
      )}
      {!unsaved && memo.data?.stale && (
        <Notice tone="attn">Your numbers have changed since this memo was written{canWrite ? ". Write it again to bring it up to date." : "."}</Notice>
      )}

      {memo.isPending ? (
        <Skeleton className="h-72" />
      ) : shown ? (
        <article className="rounded-[var(--radius-panel)] border border-line bg-surface p-5 md:p-6" aria-label="CFO memo">
          <div data-testid="memo">
            <Answer message={shown.message} citations={shown.citations} warnings={shown.warnings} />
          </div>
          {shown.generated_at && (
            <p className="mt-4 border-t border-line pt-3 text-xs text-ink-3">
              Written by the assistant for {shown.generated_by ?? "your team"} on {formatDate(shown.generated_at.slice(0, 10))}, from the forecast
              and records as of {formatDate(shown.as_of)}. Saved, so reading it again costs nothing. Not financial advice.
            </p>
          )}
        </article>
      ) : (
        <div className="space-y-3 rounded-[var(--radius-panel)] border border-dashed border-line-strong p-6">
          <p className="text-[15px] text-ink-2">
            No memo for this week yet.{" "}
            {canWrite
              ? "The assistant writes it from your cash, forecast, insights and pending approvals, citing every figure. It uses the AI budget once; after that it's saved."
              : "Ask an owner or accountant to write it."}
          </p>
          {button}
          {writing && <p className="text-xs text-ink-3">This usually takes under a minute.</p>}
        </div>
      )}
    </div>
  );
}
