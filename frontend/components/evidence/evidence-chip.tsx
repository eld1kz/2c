"use client";

import { CalendarRangeIcon, FileTextIcon, FlaskConicalIcon, LandmarkIcon, LightbulbIcon, ListChecksIcon, ReceiptIcon, RepeatIcon, UserIcon } from "lucide-react";

import { cn } from "@/lib/cn";

import { canOpen, useEvidence } from "./evidence-provider";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  transaction: ReceiptIcon,
  invoice: FileTextIcon,
  counterparty: UserIcon,
  recurring_series: RepeatIcon,
  account: LandmarkIcon,
  insight: LightbulbIcon,
  action: ListChecksIcon,
  forecast_week: CalendarRangeIcon,
  whatif: FlaskConicalIcon,
  financing: LandmarkIcon,
};

const NOT_STORED = "A simulation from this conversation, not a stored record.";

export type Evidence = { ref: string; label: string | null };

/** A readable name for refs the server has no label for (computed results such as what-ifs). */
export function fallbackLabel(ref: string): string {
  const [kind, id] = ref.split(":");
  if (kind === "whatif") return `What-if ${id}`;
  if (kind === "forecast_week") return `Week ${id}`;
  if (kind === "financing") return "Financing option";
  return ref;
}

/** A cited record; opens it in the evidence sheet. `valid: false` marks a citation the server could not verify. */
export function EvidenceChip({ evidence, valid = true, className }: { evidence: Evidence; valid?: boolean; className?: string }) {
  const sheet = useEvidence();
  const kind = evidence.ref.split(":")[0];
  const Icon = ICONS[kind] ?? FileTextIcon;
  const openable = valid && sheet !== null && canOpen(evidence.ref);
  const look = cn(
    "inline-flex max-w-[16rem] items-center gap-1 rounded-[var(--radius-chip)] border px-1.5 py-0.5 align-middle text-xs font-medium",
    valid ? "border-line bg-sunken text-ink-2" : "border-dashed border-attn bg-attn-soft text-attn-ink",
    openable && "hover:border-brand/40 hover:bg-brand-soft hover:text-brand-ink",
    className,
  );
  const body = (
    <>
      <Icon className="size-3 shrink-0" />
      <span className="truncate">{evidence.label ?? fallbackLabel(evidence.ref)}</span>
      {!valid && <span className="shrink-0">unverified</span>}
    </>
  );
  if (!openable) {
    const title = !valid ? `${evidence.ref} could not be verified against your records` : canOpen(evidence.ref) ? evidence.ref : NOT_STORED;
    return (
      <span title={title} className={look}>
        {body}
      </span>
    );
  }
  return (
    <button type="button" onClick={() => sheet.open(evidence.ref)} title={`Open ${evidence.ref}`} className={look}>
      {body}
    </button>
  );
}

export function EvidenceList({ items, max = 4 }: { items: Evidence[]; max?: number }) {
  const shown = items.slice(0, max);
  return (
    <span className="flex flex-wrap gap-1.5">
      {shown.map((e) => (
        <EvidenceChip key={e.ref} evidence={e} />
      ))}
      {items.length > max && <span className="self-center text-xs text-ink-3">+{items.length - max} more</span>}
    </span>
  );
}
