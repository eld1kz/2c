// Plain-language names for audit event types (backend/app/**: audit.append / ActionService._audit).

export const EVENT: Record<string, string> = {
  login_succeeded: "Signed in",
  login_failed: "Sign-in failed",
  login_locked: "Sign-in locked after failed attempts",
  action_proposed: "Action proposed",
  action_propose_replayed: "Same proposal sent again",
  action_denied: "Action refused by policy",
  action_input_rejected: "Proposal rejected: invalid input",
  idempotency_conflict: "Proposal key reused with different details",
  action_approved: "Action approved",
  action_rejected: "Action rejected",
  action_executed: "Action carried out in the sandbox",
  action_failed: "Action failed",
  action_not_found: "Unknown action requested",
  execute_replayed: "Repeat approval: original result returned",
  approval_forbidden: "Approval refused: not allowed for this role",
  approval_invalid_state: "Approval refused: already decided",
  rejection_forbidden: "Rejection refused: not allowed for this role",
  rejection_invalid_state: "Rejection refused: already decided",
  execute_forbidden: "Execution refused: not allowed",
  execute_invalid_state: "Execution refused: not approved",
  draft_created: "Draft written",
  draft_denied: "Draft refused",
  agent_turn_started: "Question to the assistant",
  agent_turn_finished: "Assistant answered",
  agent_tool_called: "Assistant used a tool",
  agent_citation_failed: "Answer had unverified figures",
  agent_error: "Assistant error",
  agent_budget_exhausted: "Assistant stopped: AI budget used up",
  chat_rate_limited: "Chat refused: too many questions",
  chat_refused: "Chat refused",
  chat_budget_exhausted: "Chat refused: AI budget used up",
  chat_refusals_suppressed: "Further chat refusals not logged this minute",
  upload_ingested: "Bank statement imported",
  upload_rejected: "Bank statement rejected",
  upload_forbidden: "Upload refused: not allowed for this role",
  transaction_recategorized: "Transaction category changed",
};

export function eventLabel(type: string): string {
  return EVENT[type] ?? type.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export type EventTone = "good" | "risk" | "plain";

export function eventTone(type: string): EventTone {
  if (/(denied|forbidden|failed|locked|rejected$|refused|rate_limited|exhausted|error|conflict)/.test(type)) return "risk";
  if (/^(action_approved|action_executed|upload_ingested)$/.test(type)) return "good";
  return "plain";
}

export const GROUPS: Record<string, (type: string) => boolean> = {
  All: () => true,
  Actions: (t) => /^(action_|approval_|rejection_|execute_|draft_|idempotency)/.test(t),
  Assistant: (t) => /^(agent_|chat_)/.test(t),
  "Sign-ins": (t) => t.startsWith("login_"),
  Data: (t) => /^(upload_|transaction_)/.test(t),
};

/** "user:3" → "You" (when it's the viewer), "agent:user:3" → "Assistant, for you". */
export function actorLabel(actor: string, myId: number | undefined): string {
  const mine = myId !== undefined && actor.endsWith(`user:${myId}`);
  if (actor.startsWith("agent:")) return mine ? "Assistant, for you" : `Assistant, for ${actor.slice(6)}`;
  if (actor === "anonymous") return "Not signed in";
  return mine ? "You" : actor;
}
