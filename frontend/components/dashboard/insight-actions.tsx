import { AskLink } from "@/components/chat/ask-link";
import { WhatIfLinks } from "@/components/whatif/whatif-links";
import type { Schemas } from "@/lib/api/client";
import { askAbout } from "@/lib/labels";

/** "Ask the CFO", plus the what-if shortcuts on the cash-gap card. */
export function InsightActions({ insight }: { insight: Schemas["InsightOut"] }) {
  return (
    <div className="flex flex-wrap justify-end gap-2">
      {insight.type === "CASH_GAP" && <WhatIfLinks />}
      <AskLink question={askAbout(insight)} />
    </div>
  );
}
