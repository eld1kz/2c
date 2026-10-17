"""Read-only lookup of the sandbox record an executed Action produced (for the approvals UI).

Writes stay in bank.py / outbox.py / loans.py, called only by ActionService. Contact addresses are
not returned.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SandboxEmail, SandboxLoanApplication, SandboxPayment


def for_action(session: Session, action_id: int) -> dict[str, Any] | None:
    email = session.scalar(select(SandboxEmail).where(SandboxEmail.action_id == action_id))
    if email is not None:
        return {"kind": "email", "id": email.id, "status": email.status.value, "subject": email.subject,
                "at": email.sent_at or email.created_at}
    payment = session.scalar(select(SandboxPayment).where(SandboxPayment.action_id == action_id))
    if payment is not None:
        return {"kind": "payment", "id": payment.id, "status": payment.status.value, "subject": None,
                "scheduled_date": payment.scheduled_date, "at": payment.executed_at or payment.created_at}
    loan = session.scalar(select(SandboxLoanApplication).where(SandboxLoanApplication.action_id == action_id))
    if loan is not None:
        return {"kind": "loan_application", "id": loan.id, "status": loan.status.value, "subject": None,
                "at": loan.decided_at or loan.created_at}
    return None
