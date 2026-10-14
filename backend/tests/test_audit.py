"""Hash-chained audit log + verify (SPEC §8, A5) and the append-only DB trigger (T6)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from app.audit.log import GENESIS_HASH, append, canonical_json, canonical_ts, event_hash
from app.audit.verify import verify_chain
from app.db.models import AuditEvent, Base

BACKEND = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)  # no migration triggers: lets tests tamper like a privileged DBA
    with Session(engine) as s:
        yield s


def _chain(session: Session, n: int = 5) -> list[AuditEvent]:
    return [append(session, "user:1", "action_proposed", {"action_id": i, "amount": 1000 * i, "note": "café"},
                   now=T0 + timedelta(seconds=i)) for i in range(1, n + 1)]


def test_chain_links_and_verifies(session: Session) -> None:
    events = _chain(session)
    assert [e.seq for e in events] == [1, 2, 3, 4, 5]
    assert events[0].prev_hash == GENESIS_HASH
    assert all(b.prev_hash == a.hash for a, b in zip(events, events[1:]))
    session.commit()
    assert verify_chain(session).ok and verify_chain(session).checked == 5


def test_hash_is_sha256_of_prev_plus_canonical_json() -> None:
    import hashlib

    body = canonical_json({"seq": 1, "ts": canonical_ts(T0), "actor": "a", "event_type": "e", "payload": {"b": 1, "a": 2}})
    assert body == '{"actor":"a","event_type":"e","payload":{"a":2,"b":1},"seq":1,"ts":"2026-10-01T09:00:00.000000Z"}'
    assert event_hash(GENESIS_HASH, 1, T0, "a", "e", {"a": 2, "b": 1}) == hashlib.sha256((GENESIS_HASH + body).encode()).hexdigest()
    assert canonical_ts(T0.replace(tzinfo=None)) == canonical_ts(T0)  # SQLite returns naive UTC


def test_empty_chain_verifies(session: Session) -> None:
    assert verify_chain(session).ok


@pytest.mark.parametrize("sql,reason", [
    ("UPDATE audit_events SET payload = '{\"action_id\": 3, \"amount\": 1, \"note\": \"café\"}' WHERE seq = 3",
     "event content does not match its hash"),
    ("UPDATE audit_events SET actor = 'user:2' WHERE seq = 3", "event content does not match its hash"),
    ("UPDATE audit_events SET prev_hash = '" + "f" * 64 + "' WHERE seq = 3", "prev_hash does not match the previous event"),
    ("DELETE FROM audit_events WHERE seq = 3", "event missing (sequence gap)"),
])
def test_a5_tampered_row_breaks_chain_at_that_seq(session: Session, sql: str, reason: str) -> None:
    _chain(session)
    session.commit()
    session.connection().execute(text(sql))  # raw SQL bypasses the ORM append-only guard
    session.commit()
    session.expire_all()
    result = verify_chain(session)
    assert (result.ok, result.broken_at_seq, result.reason, result.checked) == (False, 3, reason, 2)


def test_recomputed_hash_after_tamper_still_breaks_next_link(session: Session) -> None:
    events = _chain(session)
    session.commit()
    forged = event_hash(events[1].hash, 3, events[2].ts, "user:2", events[2].event_type, events[2].payload)
    session.connection().execute(text("UPDATE audit_events SET actor = 'user:2', hash = :h WHERE seq = 3"), {"h": forged})
    session.commit()
    session.expire_all()
    assert verify_chain(session).broken_at_seq == 4


def test_migration_trigger_blocks_update_and_delete(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'audit.db'}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/db/migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    with Session(create_engine(url)) as s:
        append(s, "system", "test", {})
        s.commit()
        for sql in ("UPDATE audit_events SET actor = 'x'", "DELETE FROM audit_events"):
            with pytest.raises(DatabaseError, match="append-only"):
                s.connection().execute(text(sql))
            s.rollback()
        assert s.scalar(select(AuditEvent.actor)) == "system"
