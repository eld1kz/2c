from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, Counterparty, Invoice, Policy, User
from seed.generate_golden import generate
from seed.load import load


def test_load_into_sqlite(tmp_path: Path) -> None:
    generate(tmp_path)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        business = load(s, tmp_path)
        s.commit()

        roles = {u.email: u.role for u in s.scalars(select(User))}
        assert roles == {
            "owner@emberoak.demo": "owner",
            "accountant@emberoak.demo": "accountant",
            "viewer@emberoak.demo": "viewer",
        }

        policy = s.get(Policy, business.id)
        assert policy.max_single_payment == 500_000
        assert policy.reminder_cooldown_days == 7

        inv = s.scalar(select(Invoice).where(Invoice.number == "INV-1042"))
        assert s.get(Counterparty, inv.counterparty_id).name == "Harbor Lane Café"
