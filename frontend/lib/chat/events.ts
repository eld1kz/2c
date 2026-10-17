// Server-sent events from POST /chat, mirroring `run_turn` in backend/app/agent/runner.py.
// Not in OpenAPI (it's a stream), so typed by hand; keep in sync with the runner.

import type { ScenarioInput } from "@/lib/scenarios";

export type Citation = { ref: string; valid: boolean; label: string; reason: string | null };
export type ProposedAction = { action_id: number; tool: string; status: string };

export type ChatEvent =
  | { event: "turn"; data: { conversation_id: string; turn: number } }
  | { event: "text"; data: { delta: string } }
  | { event: "tool"; data: { name: string; tier: string | null; ok: boolean; scenarios?: ScenarioInput[] } }
  | { event: "action"; data: ProposedAction }
  | { event: "reset"; data: { reason: string; problems: string[] } }
  | {
      event: "done";
      data: { message: string; citations: Citation[]; warnings: string[]; action_ids: number[]; iterations: number };
    }
  | { event: "error"; data: { message: string; action_ids: number[] } };

const KNOWN = new Set(["turn", "text", "tool", "action", "reset", "done", "error"]);

export function toChatEvent(name: string, raw: string): ChatEvent | null {
  if (!KNOWN.has(name)) return null;
  try {
    return { event: name, data: JSON.parse(raw) } as ChatEvent;
  } catch {
    return null;
  }
}
