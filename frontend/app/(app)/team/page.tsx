import { ClientOnly } from "@/components/client-only";
import { TeamView } from "@/components/team/team-view";

export const metadata = { title: "Team · Ledgerwise" };

export default function TeamPage() {
  return (
    <ClientOnly>
      <TeamView />
    </ClientOnly>
  );
}
