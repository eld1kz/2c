"""Trust & guardrails (GET /trust): what the AI may and may not do, the limits the gate enforces, and
what the audit log shows the guardrails did. Read-only, no model.

Boundaries are computed from the same tables and functions the gate and RBAC use (`TOOL_TIERS`,
`can_propose`, `can_approve`), not written out by hand, so this page can't drift from the code.
Activity counts only events whose payload names the caller's business, as `GET /audit` does.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.runner import MAX_ITERATIONS
from app.agent.tools import MAX_PROPOSALS_PER_TURN
from app.audit.verify import VerifyResult, verify_chain
from app.auth.rbac import can_approve, can_propose
from app.db.models import AuditEvent, Policy, Role, Tier
from app.policy.tiers import TOOL_TIERS

RECENT_DENIALS = 5
COUNTED = ("action_proposed", "action_approved", "action_rejected", "action_executed", "action_denied",
           "agent_tool_called", "agent_citation_failed")


@dataclass(frozen=True)
class Trust:
    boundaries: list[dict[str, Any]]
    policy: Policy
    agent_limits: dict[str, int]
    activity: dict[str, int]
    recent_denials: list[dict[str, Any]]
    chain: VerifyResult


def boundaries(policy: Policy) -> list[dict[str, Any]]:
    out = []
    for tool, tier in TOOL_TIERS.items():
        out.append({
            "tool": tool, "tier": tier.value,
            "agent_effect": {Tier.READ: "reads", Tier.SUGGEST: "drafts or simulates",
                             Tier.EXECUTE: "proposes only; a person must approve"}[tier],
            "propose": [r.value for r in Role if can_propose(r, tier, tool)],
            "approve": [r.value for r in Role if can_approve(r, tool, policy)] if tier == Tier.EXECUTE else [],
        })
    return out


def trust(session: Session, business_id: int) -> Trust:
    policy = session.get(Policy, business_id)
    if policy is None:
        raise ValueError(f"no policy for business {business_id}")
    counts: Counter[str] = Counter()
    denials: list[dict[str, Any]] = []
    for e in session.scalars(select(AuditEvent).order_by(AuditEvent.seq)):
        if e.payload.get("business_id") != business_id:
            continue
        if e.event_type in COUNTED:
            counts[e.event_type] += 1
        if e.event_type.endswith("_forbidden"):
            counts["role_refused"] += 1
        if e.event_type == "action_denied":
            denials.append({"seq": e.seq, "ts": e.ts, "tool": e.payload.get("tool"),
                            "reason": str(e.payload.get("reason") or "")[:200]})
    return Trust(
        boundaries=boundaries(policy), policy=policy,
        agent_limits={"max_model_calls_per_turn": MAX_ITERATIONS, "max_proposals_per_turn": MAX_PROPOSALS_PER_TURN},
        activity={k: counts.get(k, 0) for k in (*COUNTED, "role_refused")},
        recent_denials=denials[-RECENT_DENIALS:][::-1],
        chain=verify_chain(session),
    )
