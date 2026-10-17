"""Demo reset only: clear a business's sandbox records (payments, emails, loan applications).

The one place outside the executors that removes Sandbox* rows (see services/demo_reset.py). Never
called by ActionService or any agent path.
"""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import SandboxEmail, SandboxLoanApplication, SandboxPayment


def clear(session: Session, business_id: int) -> dict[str, int]:
    counts = {}
    for model in (SandboxPayment, SandboxEmail, SandboxLoanApplication):
        counts[model.__tablename__] = session.execute(delete(model).where(model.business_id == business_id)).rowcount
    return counts
