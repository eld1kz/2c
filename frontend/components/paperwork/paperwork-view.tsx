"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { cn } from "@/lib/cn";

import { BankPackView } from "./bank-pack-view";
import { MonthCloseView } from "./month-close-view";

const TABS = [
  { id: "month", label: "Close my month", href: "/paperwork" },
  { id: "bank", label: "Get bank-ready", href: "/paperwork?tab=bank" },
] as const;

/** Paperwork Center: month-end reports and the bank-ready pack, all computed by the engine. */
export function PaperworkView() {
  const tab = useSearchParams().get("tab") === "bank" ? "bank" : "month";
  return (
    <div className="space-y-5">
      <div className="print:hidden">
        <h1 className="text-[26px] leading-[1.2] font-semibold tracking-tight text-ink md:text-[30px]">Paperwork</h1>
        <p className="mt-1 text-sm text-ink-3">Month-end reports and a pack for your bank, built from your records. Every figure is computed, not written by AI.</p>
      </div>
      <nav className="flex w-fit rounded-lg bg-sunken p-0.5 text-sm font-medium print:hidden" aria-label="Paperwork">
        {TABS.map((t) => (
          <Link
            key={t.id}
            href={t.href}
            aria-current={tab === t.id ? "page" : undefined}
            className={cn("rounded-md px-3 py-1.5", tab === t.id ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink")}
          >
            {t.label}
          </Link>
        ))}
      </nav>
      {tab === "bank" ? <BankPackView /> : <MonthCloseView />}
    </div>
  );
}
