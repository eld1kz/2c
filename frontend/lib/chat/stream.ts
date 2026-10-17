import { ApiError, detailOf } from "@/lib/api/client";

import type { ChatEvent } from "./events";
import { createSseParser } from "./sse";

/** POST /chat and feed each server-sent event to `onEvent`. Throws ApiError if the turn is refused. */
export async function streamChat(
  body: { message: string; conversation_id: string | null },
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/backend/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body.conversation_id ? body : { message: body.message }),
    signal,
  });
  if (!response.ok || !response.body) {
    const retry = response.headers.get("retry-after");
    const error = await response.json().catch(() => undefined);
    throw new ApiError(response.status, detailOf(error), retry ? Number(retry) : null);
  }
  const feed = createSseParser(onEvent);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    feed(value);
  }
}
