import { ClientOnly } from "@/components/client-only";
import { DashboardView } from "@/components/dashboard/dashboard-view";

export const metadata = { title: "Overview · Ledgerwise" };

export default function DashboardPage() {
  return (
    <ClientOnly>
      <DashboardView />
    </ClientOnly>
  );
}
