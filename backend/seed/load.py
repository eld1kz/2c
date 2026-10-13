"""Load golden data, demo users and the default Policy into the database.

Bank transactions go through the real ingestion pipeline (parse → link → match → categorize),
then recurring series are detected. Run after `alembic upgrade head`: `python -m seed.load`
"""

import json
import sys
from datetime import date
from pathlib import Path

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    Account,
    Business,
    CategoryRule,
    Counterparty,
    Invoice,
    InvoiceLine,
    Policy,
    Role,
    RuleKind,
    RuleSource,
    User,
)
from app.engine.categorize import DEFAULT_KEYWORD_RULES, Classifier, NullClassifier
from app.engine.recurring import detect_recurring
from app.ingestion.pipeline import ingest_csv
from seed.generate_golden import GOLDEN_DIR, Q2_FILE, Q3_FILE

DEMO_PASSWORD = "emberoak-demo"  # demo-only; see docs/threat-model.md residual risks
DEMO_USERS = [
    ("owner@emberoak.demo", "Demo Owner", Role.owner),
    ("accountant@emberoak.demo", "Demo Accountant", Role.accountant),
    ("viewer@emberoak.demo", "Demo Viewer", Role.viewer),
]
DEFAULT_POLICY = {
    "max_single_payment": 500_000,
    "currency": "USD",
    "reminder_cooldown_days": 7,
    "require_owner_for": ["schedule_payment", "submit_loan_application"],
    "payee_allowlist_mode": "strict",
}


class AlreadyLoaded(Exception):
    pass


def _read(golden_dir: Path, name: str) -> object:
    return json.loads((golden_dir / name).read_text(encoding="utf-8"))


def _add_rules(session: Session, business_id: int, name_rules: list[dict]) -> None:
    for priority, (pattern, direction, category) in enumerate(DEFAULT_KEYWORD_RULES, start=100):
        session.add(CategoryRule(business_id=business_id, kind=RuleKind.keyword, pattern=pattern,
                                 direction=direction, category=category, source=RuleSource.seed, priority=priority))
    for priority, rule in enumerate(name_rules, start=200):
        session.add(CategoryRule(business_id=business_id, source=RuleSource.seed, priority=priority, **rule))


def load(session: Session, golden_dir: Path = GOLDEN_DIR, classifier: Classifier | None = None) -> Business:
    data = _read(golden_dir, "business.json")
    if session.scalar(select(Business).where(Business.name == data["business"]["name"])):
        raise AlreadyLoaded(data["business"]["name"])

    business = Business(**data["business"])
    session.add(business)
    session.flush()

    accounts = [Account(business_id=business.id, **acc) for acc in data["accounts"]]
    session.add_all(accounts)

    by_name: dict[str, Counterparty] = {}
    for cp in _read(golden_dir, "counterparties.json"):
        by_name[cp["name"]] = Counterparty(business_id=business.id, stats={}, **cp)
    session.add_all(by_name.values())
    session.flush()

    for inv in _read(golden_dir, "invoices.json"):
        invoice = Invoice(
            business_id=business.id,
            direction=inv["direction"],
            counterparty_id=by_name[inv["counterparty"]].id,
            number=inv["number"],
            issue_date=date.fromisoformat(inv["issue_date"]),
            due_date=date.fromisoformat(inv["due_date"]),
            total=inv["total"],
            currency=inv["currency"],
            status=inv["status"],
            notes=inv["notes"],
        )
        session.add(invoice)
        session.flush()
        session.add_all(InvoiceLine(invoice_id=invoice.id, **line) for line in inv["lines"])

    password_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
    for email, name, role in DEMO_USERS:
        session.add(User(business_id=business.id, email=email, name=name, role=role, password_hash=password_hash))

    session.add(Policy(business_id=business.id, **DEFAULT_POLICY))
    _add_rules(session, business.id, _read(golden_dir, "rules.json"))
    session.flush()

    checking = accounts[0]
    for name in (Q2_FILE, Q3_FILE):
        ingest_csv(session, checking, name, (golden_dir / name).read_bytes(), classifier or NullClassifier())
    detect_recurring(session, business.id, get_settings().demo_today)
    return business


def main() -> None:
    from app.db.session import SessionLocal
    from app.engine.llm_classifier import classifier_from_settings

    with SessionLocal() as session:
        try:
            business = load(session, classifier=classifier_from_settings(get_settings()))
        except AlreadyLoaded as e:
            sys.exit(f"{e} is already loaded. Reset with: alembic downgrade base && alembic upgrade head")
        session.commit()
        print(f"Loaded business id={business.id}")


if __name__ == "__main__":
    main()
