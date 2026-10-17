"use client";

import { LogOutIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useMe, usePendingActions } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/money";

import { BudgetMeter } from "./budget-meter";
import { NAV, type NavItem } from "./nav-items";

async function signOut() {
  await fetch("/api/auth/logout", { method: "POST" });
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload drops cached data after sign-out
  window.location.assign("/login");
}

function useBadge(item: NavItem): number | null {
  const pending = usePendingActions();
  return item.badge === "approvals" && pending.data?.length ? pending.data.length : null;
}

function NavLink({ item, compact }: { item: NavItem; compact?: boolean }) {
  const active = usePathname().startsWith(item.href);
  const badge = useBadge(item);
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        compact
          ? "relative flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px]"
          : "flex items-center gap-3 rounded-lg px-3 py-2 text-sm",
        active ? "font-semibold text-ink" : "text-ink-2 hover:text-ink",
        !compact && (active ? "bg-sunken" : "hover:bg-sunken/60"),
      )}
    >
      <Icon className={cn("size-[18px]", active && "text-brand")} />
      <span>{item.label}</span>
      {badge !== null && (
        <span
          className={cn(
            "num rounded-full bg-attn px-1.5 text-[11px] leading-[18px] font-semibold text-white",
            compact ? "absolute top-1 left-1/2 ml-2" : "ml-auto",
          )}
        >
          {badge}
        </span>
      )}
    </Link>
  );
}

function RoleBadge({ role }: { role: string }) {
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium capitalize", role === "owner" ? "bg-brand-soft text-brand-ink" : "bg-sunken text-ink-2")}>
      {role}
    </span>
  );
}

function Wordmark() {
  return (
    <span className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-ink">
      <svg viewBox="0 0 20 20" className="size-5" aria-hidden>
        <rect x="1" y="1" width="18" height="18" rx="5" fill="var(--color-ink)" />
        <path d="M5.5 13.5 9 9.5l2.5 2 3-4" fill="none" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Ledgerwise
    </span>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { data: me } = useMe();
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[232px_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-line bg-surface px-3 py-5 md:flex">
        <div className="px-3">
          <Wordmark />
          <p className="mt-4 truncate text-sm font-medium text-ink">{me?.business.name ?? " "}</p>
          <p className="text-xs text-ink-3">{me ? `Data as of ${formatDate(me.as_of)}` : " "}</p>
        </div>
        <nav className="mt-6 flex flex-col gap-0.5" aria-label="Main">
          {NAV.map((item) => (
            <NavLink key={item.href} item={item} />
          ))}
        </nav>
        <div className="mt-auto space-y-4 px-3">
          <BudgetMeter />
          <div className="flex items-center justify-between gap-2 border-t border-line pt-4">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{me?.user.name}</p>
              {me && <RoleBadge role={me.user.role} />}
            </div>
            <button onClick={signOut} className="rounded-md p-1.5 text-ink-3 hover:bg-sunken hover:text-ink" aria-label="Sign out" title="Sign out">
              <LogOutIcon className="size-4" />
            </button>
          </div>
        </div>
      </aside>

      <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-line bg-surface/95 px-4 py-3 backdrop-blur md:hidden">
        <div className="min-w-0">
          <Wordmark />
          <p className="truncate text-xs text-ink-3">{me ? `${me.business.name}, as of ${formatDate(me.as_of)}` : " "}</p>
        </div>
        <div className="flex items-center gap-1">
          {me && <RoleBadge role={me.user.role} />}
          <button onClick={signOut} className="rounded-md p-1.5 text-ink-3 hover:bg-sunken" aria-label="Sign out">
            <LogOutIcon className="size-4" />
          </button>
        </div>
      </header>

      <main className="min-w-0 px-4 pt-5 pb-28 md:px-8 md:pt-8 md:pb-12">
        <div className="mx-auto max-w-[1120px]">{children}</div>
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden" aria-label="Main">
        {NAV.map((item) => (
          <NavLink key={item.href} item={item} compact />
        ))}
      </nav>
    </div>
  );
}
