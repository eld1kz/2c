from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Float, Numeric, create_engine, delete, inspect, update
from sqlalchemy.orm import Session

from app.db.models import AppendOnlyViolation, AuditEvent, Base

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_all_spec_tables_exist() -> None:
    assert set(Base.metadata.tables) == {
        "businesses", "users", "accounts", "counterparties", "transactions", "invoices",
        "invoice_lines", "recurring_series", "forecast_runs", "forecast_lines", "insights",
        "actions", "audit_events", "policies", "sandbox_payments", "sandbox_emails",
        "sandbox_loan_applications", "category_rules",
    }


def _event() -> AuditEvent:
    return AuditEvent(seq=1, ts=datetime(2026, 10, 1, tzinfo=timezone.utc), actor="system",
                      event_type="test", payload={}, prev_hash="0" * 64, hash="a" * 64)


def test_audit_event_update_blocked(session: Session) -> None:
    ev = _event()
    session.add(ev)
    session.commit()
    ev.actor = "tampered"
    with pytest.raises(AppendOnlyViolation):
        session.flush()


def test_audit_event_delete_blocked(session: Session) -> None:
    ev = _event()
    session.add(ev)
    session.commit()
    session.delete(ev)
    with pytest.raises(AppendOnlyViolation):
        session.flush()


def test_audit_event_bulk_update_and_delete_blocked(session: Session) -> None:
    session.add(_event())
    session.commit()
    with pytest.raises(AppendOnlyViolation):
        session.execute(update(AuditEvent).values(actor="tampered"))
    with pytest.raises(AppendOnlyViolation):
        session.execute(delete(AuditEvent))


def test_no_float_money_columns() -> None:
    floats = {
        f"{t.name}.{c.name}"
        for t in Base.metadata.tables.values()
        for c in t.columns
        if isinstance(c.type, (Float, Numeric))
    }
    assert floats == {"transactions.confidence", "forecast_lines.probability"}


def test_migration_matches_models(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app/db/migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    tables = set(inspect(create_engine(url)).get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
