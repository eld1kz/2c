"""POST /auth/login → bearer token.

Every attempt is audited. Failed attempts are keyed by an HMAC of the email (not reversible without
the server secret); 5 failures for one email within 15 minutes lock that email out with 429 until
the window has passed, whatever password is tried.
"""

import hashlib
import hmac
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import LoginIn, TokenOut
from app.audit import log as audit
from app.auth.jwt import issue_token, verify_password
from app.config import Settings, get_settings
from app.db.models import AuditEvent, User
from app.services.action_service import utc_now

router = APIRouter(prefix="/auth", tags=["auth"])
LOCKOUT_FAILURES = 5
LOCKOUT_WINDOW = timedelta(minutes=15)


def email_key(email: str, secret: str) -> str:
    return hmac.new(secret.encode(), email.encode(), hashlib.sha256).hexdigest()


def _recent_failures(session: Session, key: str, since: datetime) -> int:
    events = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "login_failed", AuditEvent.ts >= since))
    return sum(1 for e in events if e.payload.get("email_key") == key)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> TokenOut:
    email = body.email.strip().lower()
    key = email_key(email, settings.jwt_secret)
    now = utc_now()
    if _recent_failures(session, key, now - LOCKOUT_WINDOW) >= LOCKOUT_FAILURES:
        audit.append(session, "anonymous", "login_locked", {"email_key": key}, now=now)
        session.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed attempts; try again later",
                            headers={"Retry-After": str(int(LOCKOUT_WINDOW.total_seconds()))})
    user = session.scalar(select(User).where(User.email == email))
    if not verify_password(user, body.password):
        audit.append(session, "anonymous", "login_failed", {"email_key": key}, now=now)
        session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    token, expires = issue_token(user, settings.jwt_secret, now)
    audit.append(session, f"user:{user.id}", "login_succeeded", {"business_id": user.business_id}, now=now)
    return TokenOut(access_token=token, role=user.role.value, expires_at=expires)
