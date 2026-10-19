"use client";

import { CheckCircle2Icon, LoaderCircleIcon, MessageSquareTextIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ApprovalCard } from "@/components/approvals/approval-card";
import { EvidenceChip } from "@/components/evidence/evidence-chip";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { ApiError, type Schemas } from "@/lib/api/client";
import { usePendingActions, usePrepare } from "@/lib/api/hooks";
import { askAbout } from "@/lib/labels";

type Decision = Schemas["TodayDecisionOut"];
type Action = Schemas["ActionOut"];

const OWNER_ONLY = new Set(["price_email", "terms_request"]);

function buttonLabel(d: Decision): string {
  if (d.kind === "reminder") return "Review reminder";
  if (d.kind === "price_email") return "Review price email";
  return `Ask ${d.target_name ?? "the supplier"} for 30 more days`;
}

/** One decision: a sentence from the engine and one button that opens the prepared action for approval. */
export function DecisionCard({ decision, role, onSheet }: { decision: Decision; role: string; onSheet?: (open: boolean) => void }) {
  const prepare = usePrepare();
  const pending = usePendingActions();
  const [action, setActionState] = useState<Action | null>(null);
  const setAction = (a: Action | null) => (setActionState(a), onSheet?.(a !== null));
  const insightId = Number(decision.insight.ref.split(":")[1]);
  const canAct = role === "owner" || (role === "accountant" && !OWNER_ONLY.has(decision.kind));

  function open() {
    const waiting = pending.data?.find((a) => a.id === decision.pending_action_id);
    if (waiting) return setAction(waiting);
    prepare.mutate(insightId, { onSuccess: setAction });
  }

  let control: React.ReactNode;
  if (decision.kind === "ask") {
    control = (
      <Button asChild variant="secondary">
        <Link href={`/chat?q=${encodeURIComponent(askAbout({ type: decision.type, title: decision.text }))}`}>
          <MessageSquareTextIcon /> Ask about it
        </Link>
      </Button>
    );
  } else if (decision.sent_action_id) {
    control = (
      <p className="flex items-center gap-1.5 text-sm font-medium text-good-ink">
        <CheckCircle2Icon className="size-4" /> Sent
      </p>
    );
  } else if (!canAct) {
    control = <p className="text-sm text-ink-3">{role === "viewer" ? "The owner or accountant decides this." : "The owner approves this."}</p>;
  } else {
    control = (
      <Button onClick={open} disabled={prepare.isPending} className="h-auto min-h-10 py-2 text-left whitespace-normal">
        {prepare.isPending && <LoaderCircleIcon className="animate-spin" />}
        {decision.pending_action_id ? "Review and approve" : buttonLabel(decision)}
      </Button>
    );
  }

  return (
    <article className="space-y-3 rounded-[var(--radius-panel)] border border-line bg-surface p-4 md:p-5" aria-label={decision.text}>
      <p className="text-[17px] leading-snug font-medium text-ink">{decision.text}</p>
      <div className="flex flex-wrap gap-1.5">
        {decision.evidence.slice(0, 3).map((e) => (
          <EvidenceChip key={e.ref} evidence={e} />
        ))}
      </div>
      {control}
      {prepare.isError && (
        <p role="alert" className="text-sm text-risk-ink">
          {prepare.error instanceof ApiError ? prepare.error.message : "It couldn't be prepared. Try again."}
        </p>
      )}
      <Sheet open={action !== null} onOpenChange={(isOpen) => !isOpen && setAction(null)}>
        {action && (
          <SheetContent title="Ready for your approval" description="Nothing is sent until you approve it.">
            <ApprovalCard action={action} onDecided={setAction} />
          </SheetContent>
        )}
      </Sheet>
    </article>
  );
}
