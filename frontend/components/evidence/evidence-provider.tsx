"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { Sheet } from "@/components/ui/sheet";

import { RecordSheetContent } from "./record-view";
import { WeekSheetContent } from "./week-view";

// Opens any cited record in one side sheet. Records link to other records, so the sheet keeps a
// stack and offers Back.

type Evidence = { open: (ref: string) => void };
const EvidenceContext = createContext<Evidence | null>(null);

export const OPENABLE = new Set(["transaction", "invoice", "counterparty", "recurring_series", "account", "insight", "action", "forecast_week"]);

export function canOpen(ref: string): boolean {
  return OPENABLE.has(ref.split(":")[0]);
}

export function EvidenceProvider({ children }: { children: React.ReactNode }) {
  const [stack, setStack] = useState<string[]>([]);
  const open = useCallback((ref: string) => setStack((s) => (s.at(-1) === ref ? s : [...s, ref])), []);
  const value = useMemo(() => ({ open }), [open]);
  const top = stack.at(-1) ?? null;
  const onBack = stack.length > 1 ? () => setStack((s) => s.slice(0, -1)) : undefined;
  return (
    <EvidenceContext.Provider value={value}>
      {children}
      <Sheet open={top !== null} onOpenChange={(isOpen) => !isOpen && setStack([])}>
        {top?.startsWith("forecast_week:") ? (
          <WeekSheetContent week={Number(top.split(":")[1])} onBack={onBack} />
        ) : top ? (
          <RecordSheetContent recordRef={top} onBack={onBack} />
        ) : null}
      </Sheet>
    </EvidenceContext.Provider>
  );
}

export function useEvidence(): Evidence | null {
  return useContext(EvidenceContext);
}
