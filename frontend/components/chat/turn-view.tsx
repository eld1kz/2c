import { CircleAlertIcon } from "lucide-react";
import Link from "next/link";

import { WhatIfPanel } from "@/components/whatif/whatif-panel";
import { plainCitations } from "@/lib/chat/citations";
import type { Turn } from "@/lib/chat/reducer";

import { Answer } from "./answer";
import { ToolTrail } from "./tool-trail";

/** One question and its answer. Streamed text is a visibly marked draft; only `done.message` is final. */
export function TurnView({ turn }: { turn: Turn }) {
  const streaming = turn.status === "streaming";
  const whatIf = turn.trail.findLast((t) => t.kind === "tool" && t.name === "run_what_if" && t.ok && t.scenarios?.length);
  return (
    <article className="space-y-3">
      <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-[15px] leading-relaxed text-white">
        {turn.question}
      </p>
      <ToolTrail items={turn.trail} working={streaming} />
      {streaming && turn.provisional && (
        <div aria-live="off" data-testid="provisional">
          <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-ink-3">
            <span className="size-1.5 animate-pulse rounded-full bg-attn" aria-hidden />
            Drafting. Figures are checked against your records before the answer is final.
          </p>
          <p className="text-[15px] leading-relaxed whitespace-pre-wrap text-ink-3 italic">{plainCitations(turn.provisional)}</p>
        </div>
      )}
      {turn.answer && (
        <div aria-live="polite" data-testid="answer">
          <Answer {...turn.answer} />
        </div>
      )}
      {whatIf?.kind === "tool" && whatIf.scenarios && <WhatIfPanel scenarios={whatIf.scenarios} />}
      {turn.error && (
        <div role="alert" className="flex gap-2 rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-ink-2">
          <CircleAlertIcon className="mt-0.5 size-4 shrink-0 text-attn-ink" />
          <div>
            <p>{turn.error}</p>
            {turn.actionIds.length > 0 && (
              <Link href="/approvals" className="mt-1 inline-block font-medium text-brand-ink underline-offset-2 hover:underline">
                Review what was already proposed
              </Link>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
