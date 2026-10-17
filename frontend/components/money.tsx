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
}: {
  cents: number;
  currency?: string;
  signed?: boolean;
  tone?: Tone;
  className?: string;
}) {
  return <span className={cn("num whitespace-nowrap", TONES[tone], className)}>{formatCents(cents, currency, { signed })}</span>;
}
