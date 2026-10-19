"""One-command Plaid sandbox check: `cd backend && python -m scripts.plaid_check`.

Calls Plaid's sandbox live with PLAID_CLIENT_ID / PLAID_SECRET from `.env`, prints what came back,
then runs the real ingestion pipeline on the golden data in an in-memory SQLite database (a dry run:
your Postgres is never touched, no API server needed, no model called). Exit code 0 = PASS.
"""

import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Account, Base, Counterparty, Transaction
from app.engine.categorize import NullClassifier
from app.ingestion.pipeline import IngestResult, ingest_rows
from app.ingestion.plaid_feed import PlaidError, PlaidSandboxClient, fetch_feed, load_feed
from seed.load import load


def _money(cents: int) -> str:
    return f"{'-' if cents < 0 else '+'}${abs(cents) // 100:,}.{abs(cents) % 100:02d}"


def dry_run(client: PlaidSandboxClient) -> tuple[IngestResult, IngestResult, bool]:
    """Fetch the feed and ingest it twice into golden data in memory. Returns (first, second, no_new_payees)."""
    item_id, rows = fetch_feed(client, load_feed())
    print(f"Plaid sandbox item {item_id}: {len(rows)} transactions")
    for r in rows:
        print(f"  {r.date}  {_money(r.amount):>12}  {r.description}")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load(session, classifier=NullClassifier())
        payees = session.scalar(select(func.count(Counterparty.id)))
        account = session.scalars(select(Account).order_by(Account.id)).first()
        assert account is not None
        source = f"plaid-sandbox:{item_id}"
        first = ingest_rows(session, account, source, rows, NullClassifier())
        for t in session.scalars(select(Transaction).where(Transaction.source_file == source)):
            where = "review queue" if t.needs_review else str(t.category)
            print(f"  new: {t.date}  {_money(t.amount):>12}  {where:<16} {t.raw_description}")
        second = ingest_rows(session, account, source, rows, NullClassifier())
        return first, second, session.scalar(select(func.count(Counterparty.id))) == payees


def main(argv: list[str] | None = None, client: PlaidSandboxClient | None = None) -> int:
    if client is None:
        settings = get_settings()
        if not settings.plaid_client_id or not settings.plaid_secret:
            print("FAIL: set PLAID_CLIENT_ID and PLAID_SECRET (Sandbox) in backend/.env")
            return 2
        client = PlaidSandboxClient(settings.plaid_client_id, settings.plaid_secret)
    try:
        first, second, no_new_payees = dry_run(client)
    except PlaidError as e:
        print(f"FAIL: Plaid sandbox error {e.code}")
        return 1
    print(f"first sync:  {vars(first)}")
    print(f"second sync: {vars(second)}")
    checks = {
        "new rows inserted": first.inserted > 0,
        "rows already in the golden statement skipped": first.skipped_duplicates > 0,
        "second sync inserts nothing": second.inserted == 0,
        "feed text created no counterparty": no_new_payees,
    }
    for name, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = all(checks.values())
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
