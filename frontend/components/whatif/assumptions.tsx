import { FlaskConicalIcon } from "lucide-react";

import { EvidenceChip } from "@/components/evidence/evidence-chip";
import type { Schemas } from "@/lib/api/client";
import { formatCents, formatDate } from "@/lib/money";

type Assumption = Schemas["AssumptionOut"];

const CADENCE: Record<string, string> = { weekly: "weekly", monthly: "monthly", quarterly: "quarterly" };

function Amount({ a, currency }: { a: Assumption; currency: string }) {
  if (a.amount_cents == null) return null;
  const text = formatCents(Math.abs(a.amount_cents), currency);
  return a.amount_source === "supplied" ? (
    <span className="num rounded bg-attn-soft px-1 font-medium text-attn-ink" title="Typed in, not taken from your records">
      {text} (assumed)
    </span>
  ) : (
    <span className="num font-medium">{text}</span>
  );
}

function Sentence({ a, currency }: { a: Assumption; currency: string }) {
  const who = a.counterparty_name ?? "The customer";
  switch (a.type) {
    case "collect_receivable":
      return (
        <>
          {who} pays {a.invoice && <EvidenceChip evidence={a.invoice} />} in full: <Amount a={a} currency={currency} />, the balance still
          owed on record, received {a.on ? formatDate(a.on) : "now"}.
        </>
      );
    case "delay_receivable":
      return (
        <>
          {who} pays {a.invoice && <EvidenceChip evidence={a.invoice} />} (<Amount a={a} currency={currency} /> owed on record) {a.days} days
          later than the forecast expects.
        </>
      );
    case "remove_series":
      return (
        <>
          The {a.cadence ? CADENCE[a.cadence] : "recurring"} payment {a.series && <EvidenceChip evidence={a.series} />}
          {a.counterparty_name && <> with {a.counterparty_name}</>} (<Amount a={a} currency={currency} /> each time on record) stops.
        </>
      );
    case "one_off":
      return (
        <>
          A one-off {(a.amount_cents ?? 0) < 0 ? "payment" : "receipt"} of <Amount a={a} currency={currency} /> on {a.on && formatDate(a.on)}.
        </>
      );
    case "add_recurring":
      return (
        <>
          A new {a.cadence ? CADENCE[a.cadence] : "recurring"} {(a.amount_cents ?? 0) < 0 ? "cost" : "income"} of{" "}
          <Amount a={a} currency={currency} /> from {a.on && formatDate(a.on)}.
        </>
      );
    default:
      return <>{a.type}</>;
  }
}

/** The scenario inputs, boxed as assumptions: they are what someone asked to imagine, not recorded facts. */
export function Assumptions({ items, currency }: { items: Assumption[]; currency: string }) {
  return (
    <section aria-labelledby="assumptions-title" className="rounded-[var(--radius-panel)] border border-dashed border-attn/60 bg-attn-soft/40 p-4">
      <h2 id="assumptions-title" className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-attn-ink uppercase">
        <FlaskConicalIcon className="size-3.5" /> Assumption, not a recorded fact
      </h2>
      <ul className="mt-2 space-y-1.5 text-[15px] leading-relaxed text-ink">
        {items.map((a, i) => (
          <li key={i}>
            <Sentence a={a} currency={currency} />
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink-2">
        The scenario below assumes this happens. Nothing in your books was changed
        {items.some((a) => a.amount_source === "supplied") && "; amounts marked “assumed” were typed in, not taken from your records"}.
      </p>
    </section>
  );
}
