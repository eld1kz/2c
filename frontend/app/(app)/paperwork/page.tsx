import { Suspense } from "react";

import { ClientOnly } from "@/components/client-only";
import { PaperworkView } from "@/components/paperwork/paperwork-view";

export const metadata = { title: "Paperwork · Ledgerwise" };

export default function PaperworkPage() {
  return (
    <ClientOnly>
      <Suspense>
        <PaperworkView />
      </Suspense>
    </ClientOnly>
  );
}
