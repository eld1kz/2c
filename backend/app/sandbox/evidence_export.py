"""Execution evidence (SPEC §11.6): `python -m app.sandbox.evidence_export`.

Writes a JSONL file with every sandbox operation (payments, outbox emails, loan applications), every
Action and the whole audit chain, plus `anchor.json` with the chain head (seq + hash) and the file's
sha256. Committing the anchor to git puts the head hash outside the database: a DB owner who drops the
append-only trigger, rewrites events and recomputes every later hash, or deletes the newest events,
still passes `/audit/verify`, but no longer matches the anchor (`--verify-anchor`). `--check-file`
recomputes the chain from the export alone, so a reviewer needs no database.

Read-only: nothing here writes to the database.

    python -m app.sandbox.evidence_export [--out-dir DIR]     export + anchor (default: <repo>/evidence)
    python -m app.sandbox.evidence_export --check-file FILE [--anchor anchor.json]
    python -m app.sandbox.evidence_export --verify-anchor anchor.json
"""

import argparse
import enum
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.audit.log import GENESIS_HASH, canonical_ts, event_hash
from app.audit.verify import verify_chain
from app.db.models import Action, AuditEvent, SandboxEmail, SandboxLoanApplication, SandboxPayment

FORMAT = "ledgerwise-evidence/1"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[3] / "evidence"
ANCHOR_NAME = "anchor.json"
RECORDS = (("sandbox_payment", SandboxPayment), ("sandbox_email", SandboxEmail),
           ("sandbox_loan_application", SandboxLoanApplication), ("action", Action))


@dataclass(frozen=True)
class Check:
    ok: bool
    events: int
    reason: str | None = None


def _value(value: Any) -> Any:
    if isinstance(value, datetime):
        return canonical_ts(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    return value


def _row(obj: Any) -> dict[str, Any]:
    return {c.key: _value(getattr(obj, c.key)) for c in inspect(type(obj)).column_attrs}


def _line(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"


def export(session: Session, out_dir: Path, now: datetime) -> dict[str, Any]:
    """Write the export and anchor.json into `out_dir`; return the anchor."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"ledgerwise-evidence-{stamp}.jsonl"
    records = [(kind, list(session.scalars(select(model).order_by(model.id)))) for kind, model in RECORDS]
    events = list(session.scalars(select(AuditEvent).order_by(AuditEvent.seq)))
    chain = verify_chain(session)
    head = events[-1] if events else None
    meta = {"kind": "meta", "format": FORMAT, "exported_at": canonical_ts(now),
            "counts": {kind: len(rows) for kind, rows in records} | {"audit_event": len(events)},
            "chain_verified_in_db": chain.ok, "chain_broken_at_seq": chain.broken_at_seq}
    with path.open("w", encoding="utf-8") as f:
        f.write(_line(meta))
        for kind, rows in records:
            for obj in rows:
                f.write(_line({"kind": kind, "row": _row(obj)}))
        for e in events:
            f.write(_line({"kind": "audit_event", "row": {k: v for k, v in _row(e).items() if k != "id"}}))
        f.write(_line({"kind": "head", "seq": head.seq if head else 0, "hash": head.hash if head else GENESIS_HASH,
                       "events": len(events)}))
    anchor = {"format": FORMAT, "exported_at": meta["exported_at"], "head_seq": head.seq if head else 0,
              "head_hash": head.hash if head else GENESIS_HASH, "events": len(events), "export_file": path.name,
              "export_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "chain_verified_in_db": chain.ok}
    (out_dir / ANCHOR_NAME).write_text(json.dumps(anchor, indent=2) + "\n", encoding="utf-8")
    return anchor


def check_file(path: Path, anchor: dict[str, Any] | None = None) -> Check:
    """Recompute the audit chain from the export alone (and compare it with `anchor`, if given)."""
    prev_hash, expected_seq, head = GENESIS_HASH, 1, None
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item["kind"] == "head":
            head = item
        elif item["kind"] == "audit_event":
            e = item["row"]
            if e["seq"] != expected_seq:
                return Check(False, expected_seq - 1, f"event missing before seq {e['seq']}")
            if e["prev_hash"] != prev_hash or e["hash"] != event_hash(
                    prev_hash, e["seq"], datetime.fromisoformat(e["ts"]), e["actor"], e["event_type"], e["payload"]):
                return Check(False, expected_seq - 1, f"chain broken at seq {e['seq']}")
            prev_hash, expected_seq = e["hash"], expected_seq + 1
    events = expected_seq - 1
    if head is None or (head["seq"], head["hash"], head["events"]) != (events, prev_hash, events):
        return Check(False, events, "head line does not match the chain")
    if anchor is not None:
        if hashlib.sha256(path.read_bytes()).hexdigest() != anchor["export_sha256"]:
            return Check(False, events, "file does not match the anchor's sha256")
        if (anchor["head_seq"], anchor["head_hash"]) != (events, prev_hash):
            return Check(False, events, "chain head does not match the anchor")
    return Check(True, events)


def verify_anchor(session: Session, anchor: dict[str, Any]) -> Check:
    """The live chain must verify and still contain the anchored head unchanged (no rewrite, no truncation)."""
    chain = verify_chain(session)
    if not chain.ok:
        return Check(False, chain.checked, f"chain broken at seq {chain.broken_at_seq}: {chain.reason}")
    if anchor["head_seq"] == 0:
        return Check(True, chain.checked)
    event = session.scalar(select(AuditEvent).where(AuditEvent.seq == anchor["head_seq"]))
    if event is None:
        return Check(False, chain.checked, f"anchored seq {anchor['head_seq']} is missing (chain truncated)")
    if event.hash != anchor["head_hash"]:
        return Check(False, chain.checked, f"anchored seq {anchor['head_seq']} has a different hash (chain rewritten)")
    return Check(True, chain.checked)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.sandbox.evidence_export")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check-file", type=Path, help="recompute the chain from an export file")
    group.add_argument("--verify-anchor", type=Path, help="check the live database against an anchor.json")
    parser.add_argument("--anchor", type=Path, help="with --check-file: also compare with this anchor.json")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    if args.check_file:
        anchor = json.loads(args.anchor.read_text(encoding="utf-8")) if args.anchor else None
        result = check_file(args.check_file, anchor)
        print(f"{'OK' if result.ok else 'FAILED'}: {result.events} events" + (f"; {result.reason}" if result.reason else ""))
        return 0 if result.ok else 1

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        if args.verify_anchor:
            result = verify_anchor(session, json.loads(args.verify_anchor.read_text(encoding="utf-8")))
            print(f"{'OK' if result.ok else 'FAILED'}: {result.events} events in the database"
                  + (f"; {result.reason}" if result.reason else ""))
            return 0 if result.ok else 1
        anchor = export(session, args.out_dir, datetime.now(timezone.utc))
        session.rollback()  # read-only
    print(f"Wrote {args.out_dir / anchor['export_file']} and {ANCHOR_NAME}: {anchor['events']} audit events, "
          f"head seq {anchor['head_seq']} {anchor['head_hash']}")
    if not anchor["chain_verified_in_db"]:
        print("WARNING: the audit chain in the database does not verify (see /audit/verify)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
