import { ClientOnly } from "@/components/client-only";
import { AuditView } from "@/components/audit/audit-view";

export const metadata = { title: "Audit log · Ledgerwise" };

export default function Page() {
  return (
    <ClientOnly>
      <AuditView />
    </ClientOnly>
  );
}
