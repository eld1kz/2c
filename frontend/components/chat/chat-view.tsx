"use client";

import { MessageSquarePlusIcon } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { useBudget } from "@/lib/api/hooks";
import { useChat } from "@/lib/chat/use-chat";

import { ChatNotice } from "./chat-notice";
import { Composer } from "./composer";
import { TurnView } from "./turn-view";

const SUGGESTIONS = [
  "Why will I be short on cash?",
  "Which customers pay late, and what should I do about it?",
  "Am I paying for anything twice?",
  "What's the cheapest way to cover the cash gap?",
];

export function ChatView() {
  const prefill = useSearchParams().get("q")?.slice(0, 4000) ?? "";
  const { state, send, reset, dismissNotice, streaming } = useChat();
  const budget = useBudget();
  const end = useRef<HTMLDivElement>(null);
  const last = state.turns.at(-1);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [state.turns.length, last?.status, last?.trail.length]);

  const notice = state.notice ?? (budget.data?.exhausted ? { kind: "budget" as const, message: "", retryAfter: null } : null);
  const blocked = streaming || notice?.kind === "budget" || notice?.kind === "rate" || notice?.kind === "full";

  return (
    <div className="mx-auto flex min-h-[calc(100dvh-10rem)] max-w-3xl flex-col md:min-h-[calc(100dvh-5rem)]">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Ask the CFO</h1>
          <p className="text-sm text-ink-3">Every figure links to the record it comes from. Nothing is paid or sent without your approval.</p>
        </div>
        {state.turns.length > 0 && (
          <Button variant="secondary" size="sm" onClick={reset} disabled={streaming}>
            <MessageSquarePlusIcon /> New
          </Button>
        )}
      </header>

      <div className="mt-6 flex-1 space-y-8">
        {state.turns.length === 0 && (
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                disabled={blocked}
                onClick={() => void send(s)}
                className="rounded-full border border-line bg-surface px-3.5 py-2 text-left text-sm text-ink-2 hover:border-brand/40 hover:text-ink disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {state.turns.map((t) => (
          <TurnView key={t.id} turn={t} />
        ))}
        <div ref={end} />
      </div>

      <div className="sticky bottom-[calc(env(safe-area-inset-bottom)+4.5rem)] mt-6 space-y-2 bg-canvas/90 pt-2 pb-1 backdrop-blur md:bottom-4">
        {notice && <ChatNotice notice={notice} onDismiss={dismissNotice} onNewConversation={reset} />}
        <Composer key={prefill} initial={prefill} disabled={blocked} onSend={(text) => void send(text)} />
        <p className="px-1 text-xs text-ink-3">Answers come from your records and the forecast engine. Not financial advice.</p>
      </div>
    </div>
  );
}
