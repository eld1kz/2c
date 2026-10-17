"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useReducer, useRef } from "react";

import { ApiError } from "@/lib/api/client";
import { keys } from "@/lib/api/hooks";

import { chatReducer, initialChat } from "./reducer";
import { streamChat } from "./stream";

const DROPPED = "The connection dropped before the answer was checked, so it isn't shown. Ask again.";

export function useChat() {
  const [state, dispatch] = useReducer(chatReducer, initialChat);
  const abort = useRef<AbortController | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => () => abort.current?.abort(), []);

  const send = useCallback(
    async (question: string) => {
      const id = crypto.randomUUID();
      const controller = new AbortController();
      abort.current = controller;
      dispatch({ type: "start", id, question });
      try {
        await streamChat(
          { message: question, conversation_id: state.conversationId },
          (event) => dispatch({ type: "event", id, event }),
          controller.signal,
        );
        dispatch({ type: "ended", id });
      } catch (error) {
        if (controller.signal.aborted) dispatch({ type: "ended", id });
        else if (error instanceof ApiError && error.status === 401) {
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- session expired: full reload to sign in
          window.location.assign("/login?next=/chat");
        }
        else if (error instanceof ApiError) {
          dispatch({ type: "refused", id, status: error.status, message: error.message, retryAfter: error.retryAfter });
        } else dispatch({ type: "failed", id, message: DROPPED });
      } finally {
        void queryClient.invalidateQueries({ queryKey: keys.pending });
        void queryClient.invalidateQueries({ queryKey: keys.budget });
      }
    },
    [state.conversationId, queryClient],
  );

  const reset = useCallback(() => {
    abort.current?.abort();
    dispatch({ type: "new-conversation" });
  }, []);

  const dismissNotice = useCallback(() => dispatch({ type: "dismiss-notice" }), []);

  const streaming = state.turns.some((t) => t.status === "streaming");
  return { state, send, reset, dismissNotice, streaming };
}
