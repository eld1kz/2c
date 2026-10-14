"""POST /upload: bank CSV → ingestion pipeline → engine refresh. Owner/accountant only; audited (T11)."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_classifier, get_session
from app.api.schemas import UploadOut
from app.audit import log as audit
from app.config import Settings, get_settings
from app.db.models import Account, Role, User
from app.engine.categorize import Classifier
from app.engine.refresh import refresh_engine
from app.ingestion.csv_parser import MAX_BYTES, CsvError
from app.ingestion.pipeline import ingest_csv
from app.services.action_service import utc_now

router = APIRouter(tags=["upload"])
UPLOAD_ROLES = (Role.owner, Role.accountant)


@router.post("/upload", response_model=UploadOut)
def upload(file: UploadFile, account_id: int | None = None, user: User = Depends(current_user),
           session: Session = Depends(get_session), settings: Settings = Depends(get_settings),
           classifier: Classifier = Depends(get_classifier)) -> UploadOut:
    actor = f"user:{user.id}"
    filename = (file.filename or "upload.csv")[:255]
    if user.role not in UPLOAD_ROLES:
        audit.append(session, actor, "upload_forbidden", {"business_id": user.business_id, "role": user.role.value},
                     now=utc_now())
        session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"role {user.role.value} may not upload")
    query = select(Account).where(Account.business_id == user.business_id).order_by(Account.id)
    if account_id is not None:
        query = query.where(Account.id == account_id)
    account = session.scalar(query)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    data = file.file.read(MAX_BYTES + 1)  # never read more than the limit allows
    try:
        result = ingest_csv(session, account, filename, data, classifier)
    except CsvError as e:
        session.rollback()
        audit.append(session, actor, "upload_rejected", {"business_id": user.business_id, "reason": str(e)},
                     now=utc_now())
        session.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    refresh_engine(session, user.business_id, settings.demo_today)
    out = UploadOut(**vars(result))
    audit.append(session, actor, "upload_ingested", {"business_id": user.business_id, "account_id": account.id,
                                                     **out.model_dump()}, now=utc_now())
    return out
