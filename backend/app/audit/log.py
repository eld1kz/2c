"""Hash-chained, append-only audit log (SPEC §8).

hash = sha256(prev_hash + canonical_json({seq, ts, actor, event_type, payload})). The first event
chains from GENESIS_HASH. Appends take a Postgres advisory lock so concurrent writers cannot fork
the chain; the `seq` unique constraint is the backstop. There is no update or delete path.
"""

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import AuditEvent

GENESIS_HASH = "0" * 64
_APPEND_LOCK_KEY = 0x4C57_4155  # arbitrary constant for pg_advisory_xact_lock


def canonical_json(data: Any) -> str:
    """ASCII-only (byte-identical everywhere, lone surrogates escaped) and strict JSON (no NaN/Infinity)."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def json_problem(value: Any) -> str | None:
    """Why `value` cannot be stored and hashed as JSON, or None. Check untrusted input with it first."""
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return "text is not valid Unicode"
        return None
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else "number is not finite"
    if isinstance(value, dict):
        return next((p for k, v in value.items() for p in (json_problem(k), json_problem(v)) if p), None)
    if isinstance(value, (list, tuple)):
        return next((p for v in value if (p := json_problem(v))), None)
    return f"unsupported value type {type(value).__name__}"


def canonical_ts(ts: datetime) -> str:
    """UTC, microsecond precision. Naive values (SQLite drops tzinfo on read) are taken as UTC."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def event_hash(prev_hash: str, seq: int, ts: datetime, actor: str, event_type: str, payload: dict[str, Any]) -> str:
    body = canonical_json({"seq": seq, "ts": canonical_ts(ts), "actor": actor, "event_type": event_type,
                           "payload": payload})
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


def append(session: Session, actor: str, event_type: str, payload: dict[str, Any],
           now: datetime | None = None) -> AuditEvent:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _APPEND_LOCK_KEY})
    last = session.scalar(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1))
    seq = last.seq + 1 if last else 1
    prev_hash = last.hash if last else GENESIS_HASH
    ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = json.loads(canonical_json(payload))  # store exactly what was hashed
    event = AuditEvent(seq=seq, ts=ts, actor=actor, event_type=event_type, payload=payload, prev_hash=prev_hash,
                       hash=event_hash(prev_hash, seq, ts, actor, event_type, payload))
    session.add(event)
    session.flush()
    return event
