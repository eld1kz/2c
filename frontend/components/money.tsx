import { formatCents } from "@/lib/money";
import { cn } from "@/lib/cn";

type Tone = "plain" | "good" | "risk";
const TONES: Record<Tone, string> = { plain: "", good: "text-good-ink", risk: "text-risk-ink" };

/** Integer cents rendered with tabular figures. Colour is chosen by the caller from API flags. */
export function Money({
  cents,
  currency = "USD",
  signed,
  tone = "plain",
  className,
  split,
}: {
  cents: number;
  currency?: string;
  signed?: boolean;
  tone?: Tone;
  className?: string;
  split?: boolean; // cents small and raised (headline amounts)
}) {
  const text = formatCents(cents, currency, { signed });
  const dot = text.lastIndexOf(".");
  if (!split || dot < 0) return <span className={cn("num whitespace-nowrap", TONES[tone], className)}>{text}</span>;
  return (
    <span className={cn("num whitespace-nowrap", TONES[tone], className)}>
      {text.slice(0, dot)}
      <span className="cents">{text.slice(dot)}</span>
    </span>
  );
}
