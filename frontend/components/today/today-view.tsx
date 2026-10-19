"use client";

import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useMe, useToday } from "@/lib/api/hooks";
import Link from "next/link";

import { Money } from "@/components/money";
import { formatDate } from "@/lib/money";

import { AffordBox } from "./afford-box";
import { DecisionCard } from "./decision-card";
import { FutureChart } from "./future-chart";
import { MoneyGoes } from "./money-goes";
import { SafeToSpend } from "./safe-to-spend";

/** "Good morning" / "Good afternoon" / "Good evening" by the viewer's own clock (Today renders client-side only). */
function partOfDay(hour: number): string {
  return hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
}

/** The home screen: up to 3 decisions by money at stake, what's safe to spend, where money went. */
export function TodayView() {
  const me = useMe();
  const { data, isError } = useToday();
  const [sheetOpen, setSheetOpen] = useState(false);
  if (isError) return <p className="text-sm text-risk-ink">Today couldn&apos;t be loaded. Refresh the page to try again.</p>;
  if (!data || !me.data) return <Skeleton className="h-96" />;
  return (
    <div className="mx-auto max-w-2xl space-y-8 md:space-y-10">
      <header className="pt-2 md:pt-4">
        <h1 className="font-display text-[30px] leading-[1.15] font-medium tracking-[-0.01em] text-ink md:text-[38px]">
          Good {partOfDay(new Date().getHours())}, {data.name}.
        </h1>
        <p className="mt-2 text-[17px] text-ink-2">Here&apos;s your money today.</p>
        <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-3">
          <span>{formatDate(data.as_of)}</span>
          <Link href="/team" className="text-brand-ink hover:underline" data-testid="team-line">
            Your team: {data.team.people} people
            {data.team.weekly_total_cents !== null && data.team.weekly_total_cents !== undefined && (
              <>, <Money cents={data.team.weekly_total_cents} currency={data.currency} />/week</>
            )}
          </Link>
        </p>
      </header>
      <FutureChart future={data.future} currency={data.currency} hold={sheetOpen} />
      <section className="space-y-3" aria-labelledby="decisions-title">
        <h2 id="decisions-title" className="text-[17px] font-semibold text-ink">
          {data.decisions.length ? `${data.decisions.length === 1 ? "One decision" : `${data.decisions.length} decisions`} worth your time` : "Nothing needs a decision today"}
        </h2>
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
