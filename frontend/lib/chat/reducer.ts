import type { ChatEvent, Citation, ProposedAction } from "./events";

// One question and its answer. Streamed text is only ever `provisional`: it is shown as a draft and
// dropped on `reset`, `done`, `error` or a broken stream. The only final answer is `done.message`.

export type TrailItem =
  | { kind: "tool"; name: string; tier: string | null; ok: boolean }
  | { kind: "action"; action: ProposedAction }
  | { kind: "reset"; problems: string[] };

export type Turn = {
  id: string;
  question: string;
  status: "streaming" | "done" | "error";
  provisional: string;
  trail: TrailItem[];
  answer: { message: string; citations: Citation[]; warnings: string[] } | null;
  error: string | null;
  actionIds: number[];
};

export type Notice =
  | { kind: "budget"; message: string; retryAfter: number | null }
  | { kind: "rate"; message: string; retryAfter: number | null }
  | { kind: "full"; message: string }
  | { kind: "unavailable"; message: string };

export type ChatState = { conversationId: string | null; turns: Turn[]; notice: Notice | null };

export type ChatAction =
  | { type: "start"; id: string; question: string }
  | { type: "event"; id: string; event: ChatEvent }
  | { type: "ended"; id: string }
  | { type: "refused"; id: string; status: number; message: string; retryAfter: number | null }
  | { type: "failed"; id: string; message: string }
  | { type: "new-conversation" }
  | { type: "dismiss-notice" };

export const initialChat: ChatState = { conversationId: null, turns: [], notice: null };

export const INTERRUPTED = "The answer was interrupted before it was checked, so it isn't shown. Ask again.";

function update(state: ChatState, id: string, fn: (turn: Turn) => Turn): ChatState {
  return { ...state, turns: state.turns.map((t) => (t.id === id ? fn(t) : t)) };
}

function onEvent(turn: Turn, event: ChatEvent): Turn {
  if (turn.status !== "streaming") return turn; // nothing changes a finished turn
  switch (event.event) {
    case "turn":
      return turn;
    case "text":
      return { ...turn, provisional: turn.provisional + event.data.delta };
    case "tool":
      return { ...turn, trail: [...turn.trail, { kind: "tool", ...event.data }] };
    case "action":
      return { ...turn, trail: [...turn.trail, { kind: "action", action: event.data }] };
    case "reset":
      return { ...turn, provisional: "", trail: [...turn.trail, { kind: "reset", problems: event.data.problems }] };
    case "done":
      return {
        ...turn,
        status: "done",
        provisional: "",
        answer: { message: event.data.message, citations: event.data.citations, warnings: event.data.warnings },
        actionIds: event.data.action_ids,
      };
    case "error":
      return { ...turn, status: "error", provisional: "", error: event.data.message, actionIds: event.data.action_ids };
  }
}

function noticeFor(status: number, message: string, retryAfter: number | null): Notice {
  if (status === 503 && /budget/i.test(message)) return { kind: "budget", message, retryAfter };
  if (status === 429) return { kind: "rate", message, retryAfter };
  if (status === 409) return { kind: "full", message };
  if (status === 404) return { kind: "unavailable", message: "That conversation has ended (it expired or the demo was reset). Ask again to start a new one." };
  return { kind: "unavailable", message };
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "start":
      return {
        ...state,
        notice: null,
        turns: [
          ...state.turns,
          { id: action.id, question: action.question, status: "streaming", provisional: "", trail: [], answer: null, error: null, actionIds: [] },
        ],
      };
    case "event": {
      const next = update(state, action.id, (t) => onEvent(t, action.event));
      return action.event.event === "turn" ? { ...next, conversationId: action.event.data.conversation_id } : next;
    }
    case "ended": // stream closed without `done` or `error`
      return update(state, action.id, (t) => (t.status === "streaming" ? { ...t, status: "error", provisional: "", error: INTERRUPTED } : t));
    case "refused": // the request was refused before streaming (budget, rate limit, full conversation…)
      return {
        ...state,
        conversationId: action.status === 404 || action.status === 409 ? null : state.conversationId,
        turns: state.turns.filter((t) => t.id !== action.id),
        notice: noticeFor(action.status, action.message, action.retryAfter),
      };
    case "failed":
      return update(state, action.id, (t) => (t.status === "streaming" ? { ...t, status: "error", provisional: "", error: action.message } : t));
    case "new-conversation":
      return initialChat;
    case "dismiss-notice":
      return { ...state, notice: null };
  }
}
