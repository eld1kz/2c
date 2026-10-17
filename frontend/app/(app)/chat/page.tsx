import { Suspense } from "react";

import { ChatView } from "@/components/chat/chat-view";
import { ClientOnly } from "@/components/client-only";

export const metadata = { title: "Ask the CFO · Ledgerwise" };

export default function ChatPage() {
  return (
    <ClientOnly>
      <Suspense>
        <ChatView />
      </Suspense>
    </ClientOnly>
  );
}
