from pathlib import Path

import bcrypt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Account, Base, CategoryRule, Counterparty, Invoice, Policy, RecurringSeries, Transaction, User
from seed.generate_golden import INJECTED_NOTE, TARGET_CASH_AT_DEMO_TODAY, build, generate
from seed.load import DEMO_PASSWORD, load


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

        # A1: untrusted notes are stored verbatim, not sanitised or dropped.
        qs = s.scalar(select(Invoice).where(Invoice.number == "QS-2291"))
        assert qs.notes == INJECTED_NOTE

        # Opening balance + all bank rows lands exactly on the planted cash at DEMO_TODAY.
        account = s.scalar(select(Account))
        rows, _ = build()
        assert account.opening_balance + sum(r.amount for r in rows) == TARGET_CASH_AT_DEMO_TODAY

        # Bank rows arrive through the ingestion pipeline, then recurring detection runs.
        txs = list(s.scalars(select(Transaction)))
        assert len(txs) == len(rows)
        assert account.opening_balance + sum(t.amount for t in txs) == TARGET_CASH_AT_DEMO_TODAY
        assert {r.kind for r in s.scalars(select(CategoryRule))} == {"keyword", "name"}
        assert s.scalars(select(RecurringSeries)).first() is not None

        for user in s.scalars(select(User)):
            assert bcrypt.checkpw(DEMO_PASSWORD.encode(), user.password_hash.encode())
