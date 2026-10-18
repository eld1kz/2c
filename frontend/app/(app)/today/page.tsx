import { ClientOnly } from "@/components/client-only";
import { TodayView } from "@/components/today/today-view";

export const metadata = { title: "Today · Ledgerwise" };

export default function TodayPage() {
  return (
    <ClientOnly>
      <TodayView />
    </ClientOnly>
  );
}
