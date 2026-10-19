"""Evidence export (SPEC §11.6): every sandbox operation and the whole audit chain as JSONL, verifiable
from the file alone; the anchored head hash catches a rewritten or truncated chain that `/audit/verify`
alone would accept."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from app.audit.log import event_hash
from app.audit.verify import verify_chain
from app.db.models import Action, AuditEvent, SandboxEmail
from app.sandbox import evidence_export as ev
from tests.test_api import _login, client, db  # noqa: F401 - fixtures
from tests.test_demo_reset import _propose_reminder

NOW = datetime(2026, 10, 20, 9, 30, tzinfo=timezone.utc)


def _with_sent_reminder(client: TestClient, db: sessionmaker) -> None:  # noqa: F811
    action = _propose_reminder(client, db, "evidence-p1")
    assert client.post(f"/actions/{action['id']}/approve", headers=_login(client, "owner")).json()["status"] == "executed"


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_export_holds_every_sandbox_operation_action_and_audit_event(client: TestClient, db: sessionmaker,  # noqa: F811
                                                                     tmp_path: Path) -> None:
    _with_sent_reminder(client, db)
    with db() as s:
        anchor = ev.export(s, tmp_path, NOW)
        events = list(s.scalars(select(AuditEvent).order_by(AuditEvent.seq)))
        n_actions, n_emails = s.scalar(select(func.count(Action.id))), s.scalar(select(func.count(SandboxEmail.id)))
    lines = _lines(tmp_path / anchor["export_file"])
    kinds = [item["kind"] for item in lines]
    assert kinds[0] == "meta" and kinds[-1] == "head" and lines[0]["chain_verified_in_db"] is True
    assert kinds.count("sandbox_email") == n_emails == 1 and kinds.count("action") == n_actions
    exported = [item["row"] for item in lines if item["kind"] == "audit_event"]
    assert [e["seq"] for e in exported] == [e.seq for e in events]
    assert [e["hash"] for e in exported] == [e.hash for e in events]
    email = next(item["row"] for item in lines if item["kind"] == "sandbox_email")
    assert email["status"] == "sent" and email["action_id"] in {i["row"]["id"] for i in lines if i["kind"] == "action"}
    assert anchor == json.loads((tmp_path / ev.ANCHOR_NAME).read_text(encoding="utf-8"))
    assert (anchor["head_seq"], anchor["head_hash"], anchor["events"]) == (events[-1].seq, events[-1].hash, len(events))
    assert anchor["export_sha256"] == hashlib.sha256((tmp_path / anchor["export_file"]).read_bytes()).hexdigest()


def test_the_export_verifies_from_the_file_alone(client: TestClient, db: sessionmaker, tmp_path: Path) -> None:  # noqa: F811
    _with_sent_reminder(client, db)
    with db() as s:
        anchor = ev.export(s, tmp_path, NOW)
    path = tmp_path / anchor["export_file"]
    assert ev.check_file(path, anchor).ok
    assert ev.main(["--check-file", str(path), "--anchor", str(tmp_path / ev.ANCHOR_NAME)]) == 0


def test_an_edited_export_file_fails_the_check(client: TestClient, db: sessionmaker, tmp_path: Path) -> None:  # noqa: F811
    _with_sent_reminder(client, db)
    with db() as s:
        anchor = ev.export(s, tmp_path, NOW)
    path = tmp_path / anchor["export_file"]
    lines = _lines(path)
    target = next(i for i in lines if i["kind"] == "audit_event" and i["row"]["seq"] == 3)
    target["row"]["actor"] = "user:999"
    path.write_text("".join(json.dumps(i) + "\n" for i in lines), encoding="utf-8")
    result = ev.check_file(path)
    assert not result.ok and result.reason == "chain broken at seq 3"
    assert not ev.check_file(path, anchor).ok


def test_the_export_writes_nothing(client: TestClient, db: sessionmaker, tmp_path: Path) -> None:  # noqa: F811
    _with_sent_reminder(client, db)
    with db() as s:
        before = s.scalar(select(func.count(AuditEvent.id)))
        ev.export(s, tmp_path, NOW)
        s.commit()
    with db() as s:
        assert s.scalar(select(func.count(AuditEvent.id))) == before


def _rewrite_from(session, seq: int) -> None:  # noqa: ANN001 - a privileged DBA without the trigger
    """Edit event `seq` and recompute every later hash, so the chain verifies again."""
    conn = session.connection()
    conn.execute(text("UPDATE audit_events SET actor = 'user:999' WHERE seq = :seq"), {"seq": seq})
    prev = session.scalar(select(AuditEvent.hash).where(AuditEvent.seq == seq - 1))
    for row in conn.execute(text("SELECT seq FROM audit_events WHERE seq >= :seq ORDER BY seq"), {"seq": seq}).all():
        session.expire_all()
        e = session.scalar(select(AuditEvent).where(AuditEvent.seq == row.seq))
        h = event_hash(prev, e.seq, e.ts, e.actor, e.event_type, e.payload)
        conn.execute(text("UPDATE audit_events SET prev_hash = :p, hash = :h WHERE seq = :seq"),
                     {"p": prev, "h": h, "seq": e.seq})
        prev = h
    session.expire_all()


def test_the_anchor_catches_a_rewritten_chain_that_verify_accepts(client: TestClient, db: sessionmaker,  # noqa: F811
                                                                  tmp_path: Path) -> None:
    _with_sent_reminder(client, db)
    with db() as s:
        anchor = ev.export(s, tmp_path, NOW)
        assert ev.verify_anchor(s, anchor).ok
        _rewrite_from(s, 3)
        assert verify_chain(s).ok  # the in-DB check alone is fooled
        result = ev.verify_anchor(s, anchor)
    assert not result.ok and "rewritten" in result.reason


def test_the_anchor_catches_deleted_newest_events(client: TestClient, db: sessionmaker, tmp_path: Path) -> None:  # noqa: F811
    _with_sent_reminder(client, db)
    with db() as s:
        anchor = ev.export(s, tmp_path, NOW)
        s.connection().execute(text("DELETE FROM audit_events WHERE seq > :seq"), {"seq": anchor["head_seq"] - 2})
        s.expire_all()
        assert verify_chain(s).ok
        result = ev.verify_anchor(s, anchor)
    assert not result.ok and "truncated" in result.reason


def test_events_appended_after_the_anchor_still_verify(client: TestClient, db: sessionmaker, tmp_path: Path) -> None:  # noqa: F811
    with db() as s:
        anchor = ev.export(s, tmp_path, NOW)
    _with_sent_reminder(client, db)
    with db() as s:
        assert ev.verify_anchor(s, anchor).ok
