import { ClientOnly } from "@/components/client-only";
import { TrustView } from "@/components/trust/trust-view";

export const metadata = { title: "Trust · Ledgerwise" };

export default function TrustPage() {
  return (
    <ClientOnly>
      <TrustView />
    </ClientOnly>
  );
}
