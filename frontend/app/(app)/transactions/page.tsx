import { Suspense } from "react";

import { ClientOnly } from "@/components/client-only";
import { TransactionsView } from "@/components/transactions/transactions-view";

export const metadata = { title: "Transactions · Ledgerwise" };

export default function Page() {
  return (
    <ClientOnly>
      <Suspense>
        <TransactionsView />
      </Suspense>
    </ClientOnly>
  );
}
