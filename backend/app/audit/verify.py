"""Recompute the audit hash chain and report the first broken link (SPEC §8, A5)."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.log import GENESIS_HASH, event_hash
from app.db.models import AuditEvent


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    checked: int
    broken_at_seq: int | None = None
    reason: str | None = None


def verify_chain(session: Session) -> VerifyResult:
    prev_hash, expected_seq, checked = GENESIS_HASH, 1, 0
    for event in session.scalars(select(AuditEvent).order_by(AuditEvent.seq)):
        if event.seq != expected_seq:
            return VerifyResult(False, checked, expected_seq, "event missing (sequence gap)")
        if event.prev_hash != prev_hash:
            return VerifyResult(False, checked, event.seq, "prev_hash does not match the previous event")
        if event_hash(prev_hash, event.seq, event.ts, event.actor, event.event_type, event.payload) != event.hash:
            return VerifyResult(False, checked, event.seq, "event content does not match its hash")
        prev_hash, expected_seq, checked = event.hash, expected_seq + 1, checked + 1
    return VerifyResult(True, checked)
