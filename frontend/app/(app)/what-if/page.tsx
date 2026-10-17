import { Suspense } from "react";

import { ClientOnly } from "@/components/client-only";
import { WhatIfView } from "@/components/whatif/whatif-view";

export const metadata = { title: "What-if · Ledgerwise" };

export default function WhatIfPage() {
  return (
    <ClientOnly>
      <Suspense>
        <WhatIfView />
      </Suspense>
    </ClientOnly>
  );
}
