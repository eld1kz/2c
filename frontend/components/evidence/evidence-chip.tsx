import { FileTextIcon, LandmarkIcon, ReceiptIcon, RepeatIcon, UserIcon, LightbulbIcon, ListChecksIcon, CalendarRangeIcon } from "lucide-react";

import { cn } from "@/lib/cn";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  transaction: ReceiptIcon,
  invoice: FileTextIcon,
  counterparty: UserIcon,
  recurring_series: RepeatIcon,
  account: LandmarkIcon,
  insight: LightbulbIcon,
  action: ListChecksIcon,
  forecast_week: CalendarRangeIcon,
};

export type Evidence = { ref: string; label: string | null };

/** A cited record. `valid: false` marks a citation the server could not verify. */
export function EvidenceChip({ evidence, valid = true, className }: { evidence: Evidence; valid?: boolean; className?: string }) {
  const kind = evidence.ref.split(":")[0];
  const Icon = ICONS[kind] ?? FileTextIcon;
  return (
    <span
      title={valid ? evidence.ref : `${evidence.ref} could not be verified`}
      className={cn(
        "inline-flex max-w-[16rem] items-center gap-1 rounded-[var(--radius-chip)] border px-1.5 py-0.5 align-middle text-xs font-medium",
        valid ? "border-line bg-sunken text-ink-2" : "border-dashed border-attn bg-attn-soft text-attn-ink",
        className,
      )}
    >
      <Icon className="size-3 shrink-0" />
      <span className="truncate">{evidence.label ?? evidence.ref}</span>
      {!valid && <span className="shrink-0">unverified</span>}
    </span>
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
