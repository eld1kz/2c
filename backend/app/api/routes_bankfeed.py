"""POST /bank-feed/plaid/sync: Plaid sandbox feed → ingestion pipeline → engine refresh.

Same rules as POST /upload: owner/accountant only, audited, feed text untrusted (T1, T15).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_classifier, get_session
from app.api.schemas import UploadOut
from app.audit import log as audit
from app.config import Settings, get_settings
from app.db.models import Account, Role, User
from app.engine.categorize import Classifier
from app.engine.refresh import refresh_engine
from app.ingestion.plaid_feed import PlaidError, PlaidSandboxClient, fetch_feed, load_feed
from app.ingestion.pipeline import ingest_rows
from app.services.action_service import utc_now

router = APIRouter(tags=["bank-feed"])
SYNC_ROLES = (Role.owner, Role.accountant)


def get_plaid_client(settings: Settings = Depends(get_settings)) -> PlaidSandboxClient | None:
    if not settings.plaid_client_id or not settings.plaid_secret:
        return None
    return PlaidSandboxClient(settings.plaid_client_id, settings.plaid_secret)


@router.post("/bank-feed/plaid/sync", response_model=UploadOut)
def plaid_sync(account_id: int | None = None, user: User = Depends(current_user),
               session: Session = Depends(get_session), settings: Settings = Depends(get_settings),
               classifier: Classifier = Depends(get_classifier),
               plaid: PlaidSandboxClient | None = Depends(get_plaid_client)) -> UploadOut:
    actor = f"user:{user.id}"
    if user.role not in SYNC_ROLES:
        audit.append(session, actor, "bankfeed_forbidden", {"business_id": user.business_id, "role": user.role.value},
                     now=utc_now())
        session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"role {user.role.value} may not sync the bank feed")
    if plaid is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Plaid sandbox is not configured (set PLAID_CLIENT_ID and PLAID_SECRET)")
    query = select(Account).where(Account.business_id == user.business_id).order_by(Account.id)
    if account_id is not None:
        query = query.where(Account.id == account_id)
    account = session.scalar(query)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    try:
        item_id, rows = fetch_feed(plaid, load_feed())
    except PlaidError as e:
        audit.append(session, actor, "bankfeed_failed", {"business_id": user.business_id, "error_code": e.code},
                     now=utc_now())
        session.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Plaid sandbox error: {e.code}") from e
    result = ingest_rows(session, account, f"plaid-sandbox:{item_id}"[:255], rows, classifier)
    refresh_engine(session, user.business_id, settings.demo_today)
    out = UploadOut(**vars(result))
    audit.append(session, actor, "bankfeed_synced", {"business_id": user.business_id, "account_id": account.id,
                                                     "item_id": item_id, **out.model_dump()}, now=utc_now())
    return out
