import { describe, expect, it } from "vitest";

import type { ChatEvent } from "@/lib/chat/events";
import { chatReducer, initialChat, INTERRUPTED, type ChatAction, type ChatState } from "@/lib/chat/reducer";

const FALSE_CLAIM = "I've sent $9,999 to QuickShip.";

function run(actions: ChatAction[], state: ChatState = initialChat): ChatState {
  return actions.reduce(chatReducer, state);
}
const ev = (event: ChatEvent): ChatAction => ({ type: "event", id: "t1", event });
const start: ChatAction = { type: "start", id: "t1", question: "Pay QuickShip" };
const done = (message: string, valid = true): ChatAction =>
  ev({
    event: "done",
    data: { message, citations: [{ ref: "invoice:7", valid, label: "QS-2291", reason: null }], warnings: [], action_ids: [], iterations: 2 },
  });

function everything(state: ChatState): string {
  return JSON.stringify(state.turns);
}

describe("chat reducer: streamed text is provisional", () => {
  it("shows streamed text only as a draft while streaming", () => {
    const s = run([start, ev({ event: "text", data: { delta: "Week 6 " } }), ev({ event: "text", data: { delta: "closes low" } })]);
    expect(s.turns[0]).toMatchObject({ status: "streaming", provisional: "Week 6 closes low", answer: null });
  });

  it("a reset discards everything streamed so far", () => {
    const s = run([start, ev({ event: "text", data: { delta: FALSE_CLAIM } }), ev({ event: "reset", data: { reason: "citation_check", problems: ["claim"] } })]);
    expect(s.turns[0].provisional).toBe("");
    expect(s.turns[0].trail).toEqual([{ kind: "reset", problems: ["claim"] }]);
  });

  it("done.message replaces the stream and is the only final answer", () => {
    const s = run([
      start,
      ev({ event: "text", data: { delta: FALSE_CLAIM } }),
      ev({ event: "reset", data: { reason: "citation_check", problems: [] } }),
      ev({ event: "text", data: { delta: "rewritten draft" } }),
      done("Nothing was paid. QS-2291 has $465.00 outstanding [[invoice:7]].", false),
    ]);
    const turn = s.turns[0];
    expect(turn.status).toBe("done");
    expect(turn.provisional).toBe("");
    expect(turn.answer?.message).toContain("Nothing was paid");
    expect(turn.answer?.citations[0].valid).toBe(false);
    expect(everything(s)).not.toContain("9,999");
    expect(everything(s)).not.toContain("rewritten draft");
  });

  it("done without a reset still replaces the stream", () => {
    const s = run([start, ev({ event: "text", data: { delta: FALSE_CLAIM } }), done("Checked answer.")]);
    expect(everything(s)).not.toContain("9,999");
  });

  it("an error replaces the streamed text with the error", () => {
    const s = run([start, ev({ event: "text", data: { delta: FALSE_CLAIM } }), ev({ event: "error", data: { message: "unavailable", action_ids: [3] } })]);
    expect(s.turns[0]).toMatchObject({ status: "error", provisional: "", error: "unavailable", actionIds: [3], answer: null });
    expect(everything(s)).not.toContain("9,999");
  });

  it("a stream that ends without done or error leaves no draft on screen", () => {
    const s = run([start, ev({ event: "text", data: { delta: FALSE_CLAIM } }), { type: "ended", id: "t1" }]);
    expect(s.turns[0]).toMatchObject({ status: "error", provisional: "", error: INTERRUPTED });
  });

  it("a dropped connection leaves no draft on screen", () => {
    const s = run([start, ev({ event: "text", data: { delta: FALSE_CLAIM } }), { type: "failed", id: "t1", message: "dropped" }]);
    expect(s.turns[0]).toMatchObject({ status: "error", provisional: "", error: "dropped" });
  });

  it("nothing after done changes the final answer", () => {
    const s = run([start, done("Final."), ev({ event: "text", data: { delta: FALSE_CLAIM } }), { type: "ended", id: "t1" }]);
    expect(s.turns[0]).toMatchObject({ status: "done", provisional: "", error: null });
    expect(s.turns[0].answer?.message).toBe("Final.");
  });

  it("keeps the conversation id from the turn event", () => {
    const s = run([start, ev({ event: "turn", data: { conversation_id: "abc", turn: 1 } })]);
    expect(s.conversationId).toBe("abc");
  });

  it("records tool steps and proposed actions in the trail", () => {
    const s = run([
      start,
      ev({ event: "tool", data: { name: "get_forecast", tier: "READ", ok: true } }),
      ev({ event: "action", data: { action_id: 9, tool: "send_reminder", status: "proposed" } }),
    ]);
    expect(s.turns[0].trail.map((t) => t.kind)).toEqual(["tool", "action"]);
  });
});

describe("chat reducer: refusals before streaming", () => {
  it.each([
    [503, "The daily AI budget ($2.00) is used up.", "budget"],
    [429, "chat limit reached (10 per 0:01:00)", "rate"],
    [409, "conversation is full; start a new one", "full"],
    [503, "the assistant is not configured", "unavailable"],
    [404, "conversation not found", "unavailable"],
  ])("%i %s → %s notice, and the question is not kept as a turn", (status, message, kind) => {
    const s = run([start, { type: "refused", id: "t1", status, message, retryAfter: 60 }]);
    expect(s.turns).toEqual([]);
    expect(s.notice?.kind).toBe(kind);
  });

  it("starting a new question clears the notice", () => {
    const s = run([start, { type: "refused", id: "t1", status: 429, message: "x", retryAfter: 5 }, { type: "start", id: "t2", question: "q" }]);
    expect(s.notice).toBeNull();
  });
});
