import { MessageSquareTextIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

/** Opens the chat with a question filled in; the person still chooses to send it. */
export function AskLink({ question, children = "Ask the CFO" }: { question: string; children?: React.ReactNode }) {
  return (
    <Button asChild variant="secondary" size="sm">
      <Link href={`/chat?q=${encodeURIComponent(question)}`}>
        <MessageSquareTextIcon />
        {children}
      </Link>
    </Button>
  );
}
