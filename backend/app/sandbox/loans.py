"""Sandbox lender: records loan applications. Called only by services/action_service.py."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Action, LoanStatus, SandboxLoanApplication
from app.policy.tiers import SubmitLoanApplicationParams


def submit_application(session: Session, action: Action, params: SubmitLoanApplicationParams, currency: str,
                       now: datetime) -> SandboxLoanApplication:
    application = SandboxLoanApplication(
        business_id=action.business_id,
        action_id=action.id,
        option_id=params.option_id,
        amount=params.amount,
        currency=currency,
        status=LoanStatus.submitted,
        created_at=now,
    )
    session.add(application)
    session.flush()
    return application
