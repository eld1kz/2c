import { CheckIcon, CircleAlertIcon, ListChecksIcon, LoaderCircleIcon, RotateCcwIcon } from "lucide-react";
import Link from "next/link";

import type { TrailItem } from "@/lib/chat/reducer";
import { cn } from "@/lib/cn";

const STEP: Record<string, string> = {
  get_cash_position: "Checked cash",
  get_ledger: "Searched the ledger",
  get_forecast: "Read the forecast",
  get_insights: "Checked the findings",
  explain_record: "Opened a record",
  run_what_if: "Ran a what-if",
  rank_financing: "Compared financing",
  draft_reminder: "Drafted a reminder",
  draft_terms_request: "Drafted a terms request",
  draft_price_request: "Drafted a price-review email",
  draft_cfo_memo: "Drafted the CFO memo",
  send_reminder: "Proposed a reminder",
  send_terms_request: "Proposed a terms request",
  send_price_request: "Proposed a price-review email",
  schedule_payment: "Proposed a payment",
  submit_loan_application: "Proposed a loan application",
};

const ACTION_STATUS: Record<string, string> = {
  proposed: "waiting for approval",
  denied: "refused by policy",
  executed: "done",
};

/** What the agent did while answering, as a compact row of steps. */
export function ToolTrail({ items, working }: { items: TrailItem[]; working: boolean }) {
  if (items.length === 0 && !working) return null;
  return (
    <ol className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-ink-3" aria-label="Steps">
      {items.map((item, i) => {
        const prev = items[i - 1];
        if (item.kind === "tool" && prev?.kind === "action" && prev.action.tool === item.name) return null; // already shown as the proposal
        if (item.kind === "tool") {
          return (
            <li key={i} className="flex items-center gap-1">
              {item.ok ? <CheckIcon className="size-3.5 text-good-ink" /> : <CircleAlertIcon className="size-3.5 text-attn-ink" />}
              {STEP[item.name] ?? item.name}
            </li>
          );
        }
        if (item.kind === "action") {
          const denied = item.action.status === "denied";
          return (
            <li key={i}>
              <Link
                href="/approvals"
                className={cn(
                  "flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium",
                  denied ? "bg-risk-soft text-risk-ink" : "bg-attn-soft text-attn-ink",
                )}
              >
                <ListChecksIcon className="size-3.5" />
                {STEP[item.action.tool] ?? item.action.tool}: {ACTION_STATUS[item.action.status] ?? item.action.status}
              </Link>
            </li>
          );
        }
        return (
          <li key={i} className="flex items-center gap-1 text-attn-ink">
            <RotateCcwIcon className="size-3.5" />
            Rewriting: some figures didn&apos;t match the records
          </li>
        );
      })}
      {working && (
        <li className="flex items-center gap-1">
          <LoaderCircleIcon className="size-3.5 animate-spin" />
          Working
        </li>
      )}
    </ol>
  );
}
