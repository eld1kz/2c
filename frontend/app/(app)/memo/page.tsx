import { ClientOnly } from "@/components/client-only";
import { MemoView } from "@/components/memo/memo-view";

export const metadata = { title: "CFO memo · Ledgerwise" };

export default function MemoPage() {
  return (
    <ClientOnly>
      <MemoView />
    </ClientOnly>
  );
}
