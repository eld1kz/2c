"""Sandbox outbox: records outbound emails. Called only by services/action_service.py.

The recipient is the counterparty's stored contact_email, never an address from a draft or document.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Action, Counterparty, EmailStatus, SandboxEmail


def send_email(session: Session, action: Action, recipient: Counterparty, subject: str, body: str,
               now: datetime) -> SandboxEmail:
    email = SandboxEmail(
        business_id=action.business_id,
        action_id=action.id,
        to_address=recipient.contact_email,
        subject=subject,
        body=body,
        status=EmailStatus.sent,
        created_at=now,
        sent_at=now,
    )
    session.add(email)
    session.flush()
    return email
