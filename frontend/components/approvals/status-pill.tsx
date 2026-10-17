import { cn } from "@/lib/cn";

const STATUS: Record<string, { label: string; tone: string }> = {
  proposed: { label: "Waiting for approval", tone: "bg-attn-soft text-attn-ink" },
  approved: { label: "Approved", tone: "bg-good-soft text-good-ink" },
  executed: { label: "Done in the sandbox", tone: "bg-good-soft text-good-ink" },
  rejected: { label: "Rejected", tone: "bg-sunken text-ink-2" },
  denied: { label: "Refused by policy", tone: "bg-risk-soft text-risk-ink" },
  failed: { label: "Failed", tone: "bg-risk-soft text-risk-ink" },
};

export function StatusPill({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, tone: "bg-sunken text-ink-2" };
  return <span className={cn("inline-flex rounded-full px-2 py-0.5 text-xs font-medium", s.tone)}>{s.label}</span>;
}
