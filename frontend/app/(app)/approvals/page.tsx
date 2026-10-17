import { ApprovalsView } from "@/components/approvals/approvals-view";
import { ClientOnly } from "@/components/client-only";

export const metadata = { title: "Approvals · Ledgerwise" };

export default function ApprovalsPage() {
  return (
    <ClientOnly>
      <ApprovalsView />
    </ClientOnly>
  );
}
