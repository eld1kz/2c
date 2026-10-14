"""POST /auth/login → bearer token. Successes and failures are audited (no plaintext email on failure)."""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import LoginIn, TokenOut
from app.audit import log as audit
from app.auth.jwt import issue_token, verify_password
from app.config import Settings, get_settings
from app.db.models import User
from app.services.action_service import utc_now

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> TokenOut:
    email = body.email.strip().lower()
    user = session.scalar(select(User).where(User.email == email))
    now = utc_now()
    if not verify_password(user, body.password):
        audit.append(session, "anonymous", "login_failed",
                     {"email_sha256": hashlib.sha256(email.encode()).hexdigest()}, now=now)
        session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    token, expires = issue_token(user, settings.jwt_secret, now)
    audit.append(session, f"user:{user.id}", "login_succeeded", {"business_id": user.business_id}, now=now)
    return TokenOut(access_token=token, role=user.role.value, expires_at=expires)
