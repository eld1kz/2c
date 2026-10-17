"use client";

import { ClockIcon, MessageSquarePlusIcon, SparklesIcon, XIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import type { Notice } from "@/lib/chat/reducer";
import { formatDuration } from "@/lib/duration";

/** Why the assistant can't answer right now, and what to do instead. */
export function ChatNotice({ notice, onDismiss, onNewConversation }: { notice: Notice; onDismiss: () => void; onNewConversation: () => void }) {
  const [left, setLeft] = useState(notice.kind === "rate" ? (notice.retryAfter ?? 0) : 0);
  useEffect(() => {
    if (notice.kind !== "rate" || !notice.retryAfter) return;
    const timer = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [notice]);
  useEffect(() => {
    if (notice.kind === "rate" && notice.retryAfter && notice.retryAfter <= 120 && left === 0) onDismiss();
  }, [left, notice, onDismiss]);

  if (notice.kind === "budget") {
    return (
      <div role="status" className="rounded-xl border border-attn/40 bg-attn-soft px-4 py-3 text-sm text-attn-ink">
        <p className="flex items-center gap-2 font-medium">
          <SparklesIcon className="size-4" /> Today&apos;s AI budget is used up
        </p>
        <p className="mt-1 text-ink-2">
          The assistant is back after 00:00 UTC{notice.retryAfter ? `, in ${formatDuration(notice.retryAfter)}` : ""}. The forecast,
          insights and approvals keep working: they don&apos;t use AI.
        </p>
      </div>
    );
  }
  if (notice.kind === "rate") {
    const daily = (notice.retryAfter ?? 0) > 120;
    return (
      <div role="status" className="flex items-start justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
        <div>
          <p className="flex items-center gap-2 font-medium text-ink">
            <ClockIcon className="size-4 text-attn-ink" />
            {/still streaming/i.test(notice.message) ? "The previous answer is still being written" : "That's a lot of questions in a short time"}
          </p>
          <p className="mt-1 text-ink-2">
            {daily
              ? `You've reached today's question limit. Try again in ${formatDuration(notice.retryAfter ?? 0)}.`
              : `Ask again in ${formatDuration(left)}.`}
          </p>
        </div>
        <button onClick={onDismiss} className="rounded-md p-1 text-ink-3 hover:bg-sunken" aria-label="Dismiss">
          <XIcon className="size-4" />
        </button>
      </div>
    );
  }
  if (notice.kind === "full") {
    return (
      <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
        <p className="text-ink-2">This conversation is full. Start a new one to keep asking.</p>
        <Button size="sm" variant="secondary" onClick={onNewConversation}>
          <MessageSquarePlusIcon /> New conversation
        </Button>
      </div>
    );
  }
  return (
    <div role="status" className="flex items-start justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink-2">
      <p>{notice.message}</p>
      <button onClick={onDismiss} className="rounded-md p-1 text-ink-3 hover:bg-sunken" aria-label="Dismiss">
        <XIcon className="size-4" />
      </button>
    </div>
  );
}
