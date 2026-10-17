import { ClientOnly } from "@/components/client-only";
import { UploadView } from "@/components/upload/upload-view";

export const metadata = { title: "Import · Ledgerwise" };

export default function Page() {
  return (
    <ClientOnly>
      <UploadView />
    </ClientOnly>
  );
}
