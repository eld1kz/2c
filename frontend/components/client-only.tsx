"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { useHydrated } from "@/lib/use-hydrated";

/** Renders data-fetching views after hydration (the server renders the fallback). See useHydrated. */
export function ClientOnly({ children }: { children: React.ReactNode }) {
  return useHydrated() ? children : <Skeleton className="h-64" />;
}
