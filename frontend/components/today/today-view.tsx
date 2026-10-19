"use client";

import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useMe, useToday } from "@/lib/api/hooks";
import Link from "next/link";

import { formatCents, formatDate } from "@/lib/money";

import { AffordBox } from "./afford-box";
import { DecisionCard } from "./decision-card";
import { FutureChart } from "./future-chart";
import { MoneyGoes } from "./money-goes";
import { SafeToSpend } from "./safe-to-spend";

/** The home screen: up to 3 decisions by money at stake, what's safe to spend, where money went. */
export function TodayView() {
  const me = useMe();
  const { data, isError } = useToday();
  const [sheetOpen, setSheetOpen] = useState(false);
  if (isError) return <p className="text-sm text-risk-ink">Today couldn&apos;t be loaded. Refresh the page to try again.</p>;
  if (!data || !me.data) return <Skeleton className="h-96" />;
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <p className="text-xs font-medium text-ink-3">{formatDate(data.as_of)}</p>
        <h1 className="mt-1 text-[26px] leading-[1.2] font-semibold tracking-tight text-ink md:text-[30px]">Hello, {data.name}</h1>
        <p className="mt-1 text-[15px] text-ink-2">
          {data.decisions.length ? `${data.decisions.length === 1 ? "One decision" : `${data.decisions.length} decisions`} worth your time today.` : "Nothing needs a decision today."}
        </p>
        <Link href="/team" className="mt-1 inline-block text-sm text-brand-ink hover:underline" data-testid="team-line">
          Your team: {data.team.people} people{data.team.weekly_total_cents !== null && data.team.weekly_total_cents !== undefined ? `, ${formatCents(data.team.weekly_total_cents, data.currency)}/week` : ""}
        </Link>
      </div>
      <FutureChart future={data.future} currency={data.currency} hold={sheetOpen} />
      <section className="space-y-3" aria-label="Decisions">
        {data.decisions.map((d) => (
          <DecisionCard key={d.insight.ref} decision={d} role={me.data.user.role} onSheet={setSheetOpen} />
        ))}
      </section>
      {me.data.user.role !== "viewer" && <AffordBox />}
      <SafeToSpend safe={data.safe_to_spend} currency={data.currency} />
      <MoneyGoes spending={data.spending} currency={data.currency} />
    </div>
  );
}
