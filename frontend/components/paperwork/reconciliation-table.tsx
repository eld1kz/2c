import { CircleAlertIcon, CircleCheckIcon } from "lucide-react";

import { EvidenceChip } from "@/components/evidence/evidence-chip";
import { Money } from "@/components/money";
import type { Schemas } from "@/lib/api/client";
import { formatDate } from "@/lib/money";

function Row({ label, cents, currency, strong }: { label: string; cents: number; currency: string; strong?: boolean }) {
  return (
    <div className={`flex justify-between gap-3 py-1.5 ${strong ? "font-semibold" : "text-ink-2"}`}>
      <dt>{label}</dt>
      <dd>
        <Money cents={cents} currency={currency} />
      </dd>
    </div>
  );
}

function Verdict({ a, currency }: { a: Schemas["AccountReconciliationOut"]; currency: string }) {
  if (a.statement_closing_cents === null || a.difference_cents === null)
    return <p className="text-sm text-ink-3">The bank statement had no running balance, so only your books are shown.</p>;
  const ok = a.difference_cents === 0;
  const Icon = ok ? CircleCheckIcon : CircleAlertIcon;
  return (
    <div className={`flex gap-2 rounded-lg px-3 py-2 text-sm ${ok ? "bg-good-soft text-good-ink" : "bg-risk-soft text-risk-ink"}`}>
      <Icon className="mt-0.5 size-4 shrink-0" />
      <p>
        Bank statement on {a.statement_date ? formatDate(a.statement_date) : "the last day"}:{" "}
        <Money cents={a.statement_closing_cents} currency={currency} className="font-semibold" />.{" "}
        {ok ? "It matches your books to the cent." : <>Difference: <Money cents={a.difference_cents} currency={currency} signed className="font-semibold" />.</>}
      </p>
    </div>
  );
}

/** Books vs. bank, per account, for the closed month. */
export function ReconciliationTable({ rec, currency }: { rec: Schemas["ReconciliationOut"]; currency: string }) {
  return (
    <div className="space-y-4">
      {rec.accounts.map((a) => (
        <div key={a.account.ref} className="space-y-2">
          <EvidenceChip evidence={a.account} />
          <dl className="divide-y divide-line text-sm">
            <Row label="Balance at start (books)" cents={a.book_opening_cents} currency={currency} />
            <Row label="Money in" cents={a.money_in_cents} currency={currency} />
            <Row label="Money out" cents={-a.money_out_cents} currency={currency} />
            <Row label="Balance at end (books)" cents={a.book_closing_cents} currency={currency} strong />
          </dl>
          <Verdict a={a} currency={currency} />
          {a.to_review.length > 0 && (
            <div className="text-sm">
              <p className="text-ink-2">Still to check ({a.to_review.length}): categorize these in Transactions.</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {a.to_review.map((t) => (
                  <EvidenceChip key={t.ref} evidence={t} />
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
