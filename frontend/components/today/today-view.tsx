"use client";

import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { Lineup } from "@/components/team/lineup";
import { useMe, useTeam, useToday } from "@/lib/api/hooks";
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
  const team = useTeam();
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
        <p className="mt-3 text-sm text-ink-3">{formatDate(data.as_of)}</p>
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
      <Link href="/team" aria-label="Your team: open the Team page"
        className="group flex flex-wrap items-end justify-between gap-x-6 gap-y-3 rounded-[var(--radius-panel)] border border-line bg-surface px-5 pt-4 pb-3 hover:border-line-strong">
        <span className="pb-2">
          <span className="block text-[15px] font-semibold text-ink" data-testid="team-line">
            Your team: {data.team.people} people
            {data.team.weekly_total_cents !== null && data.team.weekly_total_cents !== undefined && (
              <>, <Money cents={data.team.weekly_total_cents} currency={data.currency} />/week</>
            )}
          </span>
        </span>
        {team.data && <Lineup people={team.data.people} size="sm" />}
      </Link>
      {me.data.user.role !== "viewer" && <AffordBox />}
      <SafeToSpend safe={data.safe_to_spend} currency={data.currency} />
      <MoneyGoes spending={data.spending} currency={data.currency} />
    </div>
  );
}
