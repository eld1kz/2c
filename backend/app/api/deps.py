"""FastAPI dependencies: DB session, current user, action service, classifier."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.jwt import InvalidToken, read_token
from app.config import Settings, get_settings
from app.db.models import User
from app.engine.categorize import Classifier
from app.services.action_service import ActionError, ActionService

_bearer = HTTPBearer(auto_error=False)


def get_session() -> Iterator[Session]:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated",
                                 headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        user = session.get(User, read_token(credentials.credentials, settings.jwt_secret))
    except InvalidToken:
        raise unauthorized from None
    if user is None:
        raise unauthorized
    return user


def action_service(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> ActionService:
    return ActionService(session, settings.demo_today)


def get_classifier(settings: Settings = Depends(get_settings)) -> Classifier:
    from app.engine.llm_classifier import classifier_from_settings

    return classifier_from_settings(settings)


@contextmanager
def refusals_keep_audit(session: Session) -> Iterator[None]:
    """Turn a domain refusal into an HTTP error but still commit the AuditEvent that recorded it."""
    try:
        yield
    except ActionError as e:
        session.commit()
        raise HTTPException(e.status_code, e.detail) from e
