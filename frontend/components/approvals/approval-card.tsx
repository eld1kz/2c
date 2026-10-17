"use client";

import { CheckCircle2Icon, ChevronDownIcon, MailIcon, ShieldAlertIcon, ShieldCheckIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EvidenceChip, EvidenceList } from "@/components/evidence/evidence-chip";
import { Money } from "@/components/money";
import { Button } from "@/components/ui/button";
import { ApiError, type Schemas } from "@/lib/api/client";
import { useDecide } from "@/lib/api/hooks";
import { formatDate } from "@/lib/money";

import { StatusPill } from "./status-pill";

type Action = Schemas["ActionOut"];

const APPROVE_LABEL: Record<string, string> = {
  send_reminder: "Approve and send",
  schedule_payment: "Approve payment",
  submit_loan_application: "Approve application",
};

const GOES_TO: Record<string, string> = {
  send_reminder: "The customer's stored contact",
  schedule_payment: "The supplier's stored bank details, never details from documents",
};

const VIEWER_REFUSED = "Viewers can't approve; this attempt was logged.";

function refusal(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) {
    return /^role viewer\b/.test(error.message) ? VIEWER_REFUSED : "Only an owner can approve this; this attempt was logged.";
  }
  if (error instanceof ApiError) return error.message;
  return "The decision couldn't be sent. Check your connection and try again.";
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <dt className="shrink-0 text-xs text-ink-3">{label}</dt>
      <dd className="num text-right text-sm text-ink">{children}</dd>
    </div>
  );
}

/** One proposed action: what, why, evidence, $ impact, and the decision. */
export function ApprovalCard({ action, onDecided }: { action: Action; onDecided?: (result: Action) => void }) {
  const decide = useDecide();
  const [showEmail, setShowEmail] = useState(false);
  const d = action.display;
  const waiting = action.status === "proposed";
  const send = (decision: "approve" | "reject") =>
    decide.mutate({ id: action.id, decision }, { onSuccess: (result) => onDecided?.(result) });

  return (
    <article className="overflow-hidden rounded-[var(--radius-panel)] border border-line bg-surface" aria-labelledby={`action-${action.id}`}>
      <div className="p-4 md:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <StatusPill status={action.status} />
          <span className="text-xs text-ink-3">
            #{action.id}, proposed by {action.proposed_by === "agent" ? "the assistant" : "a person"}
          </span>
        </div>
        <h3 id={`action-${action.id}`} className="mt-3 text-[17px] leading-snug font-semibold text-ink">
          {d?.title ?? action.tool}
        </h3>
        {d?.amount_cents != null && (
          <p className="mt-1 flex flex-wrap items-baseline gap-x-2">
            <Money cents={d.amount_cents} currency={d.currency} className="text-2xl font-semibold tracking-tight" />
            {d.days_past_due ? <span className="text-sm text-risk-ink">{d.days_past_due} days overdue</span> : null}
          </p>
        )}

        {action.rationale && (
          <div className="mt-4">
            <p className="text-xs font-medium text-ink-2">Why the assistant proposes this</p>
            <p className="mt-1 border-l-2 border-line-strong pl-3 text-sm leading-relaxed whitespace-pre-wrap text-ink-2">{action.rationale}</p>
            <p className="mt-1 text-xs text-ink-3">This is the assistant&apos;s own wording and may quote documents. The checked details are below.</p>
          </div>
        )}

        {d && d.evidence.length > 0 && (
          <div className="mt-4">
            <p className="mb-1.5 text-xs font-medium text-ink-2">Evidence</p>
            <EvidenceList items={d.evidence} max={6} />
          </div>
        )}

        <dl className="mt-4 divide-y divide-line rounded-lg bg-sunken/60 px-3">
          <p className="flex items-center gap-1.5 pt-2 text-xs font-medium text-ink-2">
            <ShieldCheckIcon className="size-3.5" /> Checked by the payment policy before and after approval
          </p>
          {d?.counterparty && (
            <Detail label="Who">
              <EvidenceChip evidence={d.counterparty} />
            </Detail>
          )}
          {d?.invoice && (
            <Detail label="Invoice">
              <EvidenceChip evidence={d.invoice} />
            </Detail>
          )}
          {d?.invoice_outstanding_cents != null && (
            <Detail label="Still owed on the invoice">
              <Money cents={d.invoice_outstanding_cents} currency={d.currency} />
            </Detail>
          )}
          {d?.scheduled_date && <Detail label="Payment date">{formatDate(d.scheduled_date)}</Detail>}
          {GOES_TO[action.tool] && <Detail label="Goes to">{GOES_TO[action.tool]}</Detail>}
        </dl>

        {d?.email && (
          <div className="mt-4 rounded-lg border border-line">
            <button
              onClick={() => setShowEmail((v) => !v)}
              aria-expanded={showEmail}
              className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm"
            >
              <span className="flex min-w-0 items-center gap-2">
                <MailIcon className="size-4 shrink-0 text-ink-3" />
                <span className="truncate font-medium">{d.email.subject}</span>
              </span>
              <ChevronDownIcon className={`size-4 shrink-0 text-ink-3 transition-transform ${showEmail ? "rotate-180" : ""}`} />
            </button>
            {showEmail && <p className="border-t border-line px-3 py-3 text-sm leading-relaxed whitespace-pre-wrap text-ink-2">{d.email.body}</p>}
          </div>
        )}

        {d?.denied_reason && (
          <p className="mt-4 flex gap-2 rounded-lg bg-risk-soft px-3 py-2.5 text-sm text-risk-ink">
            <ShieldAlertIcon className="mt-0.5 size-4 shrink-0" />
            <span>Refused by policy: {d.denied_reason}</span>
          </p>
        )}

        {d?.sandbox && (
          <div className="mt-4 rounded-lg bg-good-soft px-3 py-2.5 text-sm text-good-ink" data-testid="sandbox-result">
            <p className="flex items-center gap-2 font-medium">
              <CheckCircle2Icon className="size-4" /> {d.sandbox.summary}
            </p>
            {d.sandbox.subject && <p className="mt-1 text-ink-2">Subject: {d.sandbox.subject}</p>}
            <p className="mt-1 text-xs text-ink-2">
              Sandbox only: nothing left this demo.{" "}
              <Link href="/audit" className="font-medium underline underline-offset-2">
                See it in the audit log
              </Link>
            </p>
          </div>
        )}

        {decide.isError && (
          <p role="alert" className="mt-4 rounded-lg bg-risk-soft px-3 py-2.5 text-sm text-risk-ink">
            {refusal(decide.error)}
          </p>
        )}
      </div>

      {waiting && (
        <div className="grid grid-cols-2 gap-2 border-t border-line bg-canvas/60 p-3 md:flex md:justify-end">
          <Button variant="risk" size="lg" disabled={decide.isPending} onClick={() => send("reject")}>
            Reject
          </Button>
          <Button variant="good" size="lg" disabled={decide.isPending} onClick={() => send("approve")}>
            {decide.isPending ? "Working…" : (APPROVE_LABEL[action.tool] ?? "Approve")}
          </Button>
        </div>
      )}
    </article>
  );
}
