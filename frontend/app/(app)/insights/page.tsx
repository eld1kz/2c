import { ClientOnly } from "@/components/client-only";
import { InsightsView } from "@/components/insights/insights-view";

export const metadata = { title: "Findings · Ledgerwise" };

export default function Page() {
  return (
    <ClientOnly>
      <InsightsView />
    </ClientOnly>
  );
}
