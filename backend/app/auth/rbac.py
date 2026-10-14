"""Role-based permissions (SPEC §8).

viewer: READ only. accountant: READ + SUGGEST, may propose and approve reminders.
owner: everything, including approvals of tools in Policy.require_owner_for.
"""

from app.db.models import Policy, Role, Tier

REMINDER_TOOL = "send_reminder"


def can_propose(role: Role, tier: Tier, tool: str) -> bool:
    if tier == Tier.READ:
        return True
    if role == Role.viewer:
        return False
    if tier == Tier.SUGGEST or role == Role.owner:
        return True
    return tool == REMINDER_TOOL


def can_approve(role: Role, tool: str, policy: Policy) -> bool:
    if role == Role.owner:
        return True
    return role == Role.accountant and tool == REMINDER_TOOL and tool not in policy.require_owner_for
