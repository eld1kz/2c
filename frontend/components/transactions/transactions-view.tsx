"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { EvidenceChip } from "@/components/evidence/evidence-chip";
import { Money } from "@/components/money";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Schemas } from "@/lib/api/client";
import { useMe, useTransactions } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";
import { CATEGORY } from "@/lib/labels";
import { formatDate } from "@/lib/money";

import { CategoryPicker } from "./category-picker";

const SOURCE: Record<string, string> = { rule: "by rule", llm: "by AI", human: "by a person" };

function Category({ t, editable }: { t: Schemas["TransactionOut"]; editable: boolean }) {
  if (editable && (t.needs_review || t.category === null)) return <CategoryPicker transaction={t} />;
  return (
    <span className="text-sm text-ink">
      {t.category ? CATEGORY[t.category] : "Not categorized"}
      {t.category_source && <span className="ml-1 text-xs text-ink-3">{SOURCE[t.category_source] ?? t.category_source}</span>}
    </span>
  );
}

function Row({ t, editable }: { t: Schemas["TransactionOut"]; editable: boolean }) {
  return (
    <li className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 px-4 py-3 md:grid-cols-[6.5rem_minmax(0,1fr)_14rem_8rem] md:items-center">
      <span className="order-3 text-xs text-ink-3 md:order-none md:text-sm md:text-ink-2">{formatDate(t.date)}</span>
      <span className="order-1 min-w-0 md:order-none">
        <span className="block truncate text-sm font-medium text-ink" title={`Bank statement text: ${t.description.untrusted_text}`}>
          {t.description.untrusted_text}
        </span>
        <span className="mt-1 flex flex-wrap gap-1.5">
          {t.counterparty && <EvidenceChip evidence={t.counterparty} />}
          {t.invoice && <EvidenceChip evidence={t.invoice} />}
        </span>
      </span>
      <span className="order-4 col-span-2 md:order-none md:col-span-1">
        <Category t={t} editable={editable} />
      </span>
      <Money cents={t.amount_cents} currency={t.currency} signed className="order-2 text-right text-sm font-medium md:order-none" />
    </li>
  );
}

export function TransactionsView() {
  const [tab, setTab] = useState<"all" | "review">(useSearchParams().get("tab") === "review" ? "review" : "all");
  const [pages, setPages] = useState(1);
  const { data, isLoading, isError, isFetching } = useTransactions(tab === "review", pages);
  const review = useTransactions(true, 1);
  const role = useMe().data?.user.role;
  const editable = role === "owner" || role === "accountant";
  const reviewCount = review.data ? `${review.data.rows.length}${review.data.hasMore ? "+" : ""}` : "";

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Transactions</h1>
          <p className="mt-1 text-sm text-ink-3">Bank activity, newest first. Descriptions are shown exactly as the bank wrote them.</p>
        </div>
        {editable && (
          <Button asChild variant="secondary" size="sm">
            <Link href="/upload">Import a bank statement</Link>
          </Button>
        )}
      </div>

      <div className="mt-5 flex max-w-md rounded-lg bg-sunken p-0.5 text-sm font-medium" role="tablist">
        {(
          [
            ["all", "All"],
            ["review", `Needs review ${reviewCount && `(${reviewCount})`}`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => {
              setTab(key);
              setPages(1);
            }}
            className={cn("flex-1 rounded-md px-3 py-1.5", tab === key ? "bg-surface text-ink shadow-sm" : "text-ink-2")}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "review" && (
        <p className="mt-4 max-w-prose text-sm text-ink-2">
          {editable
            ? "These weren't matched by a rule and the AI wasn't confident enough. Pick a category: it's saved at once and becomes a rule for this payee."
            : "These need a category. Owners and accountants can set them; viewers can only look."}
        </p>
      )}

      {isLoading && <Skeleton className="mt-5 h-80" />}
      {isError && <p className="mt-5 text-sm text-risk-ink">Transactions couldn&apos;t be loaded. Refresh to try again.</p>}
      {data && (
        <>
          <div className="mt-4 hidden grid-cols-[6.5rem_minmax(0,1fr)_14rem_8rem] gap-x-4 px-4 text-xs text-ink-3 md:grid">
            <span>Date</span>
            <span>Description</span>
            <span>Category</span>
            <span className="text-right">Amount</span>
          </div>
          <ol className="mt-2 divide-y divide-line overflow-hidden rounded-[var(--radius-panel)] border border-line bg-surface">
            {data.rows.map((t) => (
              <Row key={t.id} t={t} editable={editable} />
            ))}
            {data.rows.length === 0 && (
              <li className="px-4 py-8 text-center text-sm text-ink-3">
                {tab === "review" ? "Nothing to review. Every transaction has a category." : "No transactions yet."}
              </li>
            )}
          </ol>
          {data.hasMore && (
            <button
              onClick={() => setPages((p) => p + 1)}
              disabled={isFetching}
              className="mt-3 w-full rounded-lg border border-line bg-surface py-2 text-sm font-medium text-ink-2 hover:bg-sunken disabled:opacity-60"
            >
              {isFetching ? "Loading…" : "Show older transactions"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
