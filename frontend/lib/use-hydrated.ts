import { useSyncExternalStore } from "react";

const noop = () => () => {};

/** False during SSR and hydration, true after. Pages fetch on the client only, so they render
 *  after hydration; otherwise a query that resolves mid-hydration makes the HTML mismatch. */
export function useHydrated(): boolean {
  return useSyncExternalStore(noop, () => true, () => false);
}
