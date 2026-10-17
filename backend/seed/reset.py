"""Reset the demo business to its golden state from the command line: `python -m seed.reset`.

Same as the owner's "Reset demo data" button (services/demo_reset.py): audit events are kept and a
`demo_reset` event is appended (actor `cli:demo_reset`, or `scheduler:demo_reset` with `--scheduled`,
which the deployed instance's cron runs every 3 hours: deploy/cron/ledgerwise).
"""

import argparse
import json
import sys

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Business
from app.services.demo_reset import reset_demo
from seed.generate_golden import GOLDEN_DIR


def main(argv: list[str] | None = None) -> None:
    from app.audit.verify import verify_chain
    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(prog="python -m seed.reset")
    parser.add_argument("--scheduled", action="store_true", help="audit the reset as the scheduler's")
    actor = "scheduler:demo_reset" if parser.parse_args(argv).scheduled else "cli:demo_reset"
    name = json.loads((GOLDEN_DIR / "business.json").read_text(encoding="utf-8"))["business"]["name"]
    with SessionLocal() as session:
        business = session.scalar(select(Business).where(Business.name == name))
        if business is None:
            sys.exit(f"{name} is not loaded. Load it first: python -m seed.load")
        removed = reset_demo(session, business.id, actor, get_settings().demo_today)
        session.commit()
        chain = verify_chain(session)
    print(f"Reset {name} (id={business.id}); removed: {removed}")
    print(f"Audit chain: {'intact' if chain.ok else f'BROKEN at seq {chain.broken_at_seq}'} ({chain.checked} events)")


if __name__ == "__main__":
    main()
