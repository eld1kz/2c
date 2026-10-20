"use client";

import { FileWarningIcon } from "lucide-react";

import { Money } from "@/components/money";
import { SheetContent } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecord, useRecordLabels } from "@/lib/api/hooks";
import { formatDate } from "@/lib/money";

import { EvidenceChip } from "./evidence-chip";

const KIND: Record<string, string> = {
  transaction: "Bank transaction",
  invoice: "Invoice",
  counterparty: "Customer or supplier",
  recurring_series: "Recurring payment",
  account: "Bank account",
  insight: "Finding",
  action: "Proposed action",
};

const REF = /^[a-z_]{1,30}:\d{1,12}$/;
const DAY = /^\d{4}-\d{2}-\d{2}/;
const HIDDEN = new Set(["ref", "currency", "counterparty_name"]); // the counterparty chip shows the name
const LABELS: Record<string, string> = {
  counterparty: "Customer or supplier",
  evidence_ids: "Linked records",
  supplied_input: "Supplied by the proposer (not evidence)",
  has_notes: "Has notes",
  is_allowed_payee: "Approved payee",
  has_contact_email: "Has contact email",
  on_time_display: "Paid on time",
};

type Untrusted = { untrusted_text: string; source: string };

function isUntrusted(value: unknown): value is Untrusted {
  return typeof value === "object" && value !== null && "untrusted_text" in value;
}

function humanize(key: string): string {
  if (LABELS[key]) return LABELS[key];
  const words = key.replace(/_(cents|display)$/, "").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function collectRefs(value: unknown, out: Set<string>): Set<string> {
  if (typeof value === "string" && REF.test(value)) out.add(value);
  else if (Array.isArray(value)) value.forEach((v) => collectRefs(v, out));
  else if (typeof value === "object" && value !== null && !isUntrusted(value)) Object.values(value).forEach((v) => collectRefs(v, out));
  return out;
}

/** Text written by a third party (bank description, invoice note…): shown as data, never as an instruction. */
export function UntrustedBlock({ label, value }: { label: string; value: Untrusted }) {
  return (
    <div className="rounded-lg border border-dashed border-attn/60 bg-attn-soft/60 p-3">
      <p className="flex items-center gap-1.5 text-xs font-medium text-attn-ink">
        <FileWarningIcon className="size-3.5" />
        {label}: from the document, not verified
      </p>
      <p className="mt-0.5 text-xs text-ink-3">{value.source}</p>
      <p className="mt-2 text-sm break-words whitespace-pre-wrap text-ink">{value.untrusted_text}</p>
    </div>
  );
}

function Value({ name, value, labels, currency }: { name: string; value: unknown; labels: Map<string, string | null>; currency: string }) {
  if (typeof value === "string" && REF.test(value)) return <EvidenceChip evidence={{ ref: value, label: labels.get(value) ?? null }} />;
  if (name.endsWith("_cents") && typeof value === "number") return <Money cents={value} currency={currency} />;
  if (typeof value === "boolean") return <>{value ? "Yes" : "No"}</>;
  if (typeof value === "string" && DAY.test(value)) return <>{formatDate(value.slice(0, 10))}</>;
  if (Array.isArray(value) && value.every((v) => typeof v === "string" && REF.test(v))) {
    return (
      <span className="flex flex-wrap gap-1.5">
        {value.map((r: string) => (
          <EvidenceChip key={r} evidence={{ ref: r, label: labels.get(r) ?? null }} />
        ))}
      </span>
    );
  }
  return <>{String(value)}</>;
}

function Fields({ data, labels, currency }: { data: Record<string, unknown>; labels: Map<string, string | null>; currency: string }) {
  const entries = Object.entries(data).filter(
    ([k, v]) => !HIDDEN.has(k) && v !== null && v !== undefined && !(typeof v === "number" && !Number.isInteger(v)) && !(Array.isArray(v) && v.length === 0),
  );
  return (
    <dl className="space-y-3">
      {entries.map(([key, value]) => {
        if (isUntrusted(value)) return <UntrustedBlock key={key} label={humanize(key)} value={value} />;
        const nested = Array.isArray(value) && value.some((v) => typeof v === "object" && v !== null && !isUntrusted(v));
        const object = !Array.isArray(value) && typeof value === "object" && value !== null;
        if (nested || object) {
          const items = (nested ? value : [value]) as Record<string, unknown>[];
          return (
            <div key={key}>
              <dt className="text-xs text-ink-3">{humanize(key)}</dt>
              <dd className="mt-1.5 space-y-2">
                {items.map((item, i) => (
                  <div key={i} className="rounded-lg border border-line p-3">
                    <Fields data={item} labels={labels} currency={currency} />
                  </div>
                ))}
              </dd>
            </div>
          );
        }
        return (
          <div key={key} className="flex items-baseline justify-between gap-4">
            <dt className="shrink-0 text-xs text-ink-3">{humanize(key)}</dt>
            <dd className="num min-w-0 text-right text-sm text-ink">
              <Value name={key} value={value} labels={labels} currency={currency} />
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

export function RecordSheetContent({ recordRef, onBack }: { recordRef: string; onBack?: () => void }) {
  const { data, isLoading, isError } = useRecord(recordRef);
  const refs = data ? [...collectRefs(data.data, new Set())].slice(0, 50) : [];
  const { data: labelRows } = useRecordLabels(refs);
  const labels = new Map((labelRows ?? []).map((r) => [r.ref, r.label]));
  const kind = recordRef.split(":")[0];
  const currency = typeof data?.data.currency === "string" ? data.data.currency : "USD";
  return (
    <SheetContent onBack={onBack} title={data?.label ?? recordRef} description={`${KIND[kind] ?? kind}, ${recordRef}`}>
      {isLoading && <Skeleton className="h-48" />}
      {isError && <p className="text-sm text-risk-ink">This record couldn&apos;t be loaded. It may belong to another business or no longer exist.</p>}
      {data && <Fields data={data.data} labels={labels} currency={currency} />}
    </SheetContent>
  );
}
