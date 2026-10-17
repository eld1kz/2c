"""Evidence records for the web UI: one record in detail (`explain`), and display labels for many refs.

Any signed-in role may read; everything is scoped to the caller's business. Third-party text (bank
descriptions, invoice notes and lines, proposers' rationales) is returned wrapped as
{"untrusted_text", "source"} so the UI can mark it as document content (T1).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_session
from app.api.schemas import EvidenceRef, RecordOut
from app.config import Settings, get_settings
from app.db.models import User
from app.services import ledger

router = APIRouter(prefix="/records", tags=["records"])
REF_PATTERN = r"^[a-z_]{1,30}:\d{1,12}$"
MAX_LABELS = 50


def _plain(value: Any) -> Any:
    if isinstance(value, ledger.UntrustedText):
        return {"untrusted_text": value.text, "source": value.source}
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


@router.get("", response_model=list[EvidenceRef])
def record_labels(ref: list[str] = Query(max_length=MAX_LABELS), user: User = Depends(current_user),
                  session: Session = Depends(get_session)) -> list[EvidenceRef]:
    names = ledger.labels(session, user.business_id, ref)
    return [EvidenceRef(ref=r, label=names.get(r)) for r in ref]


@router.get("/{ref}", response_model=RecordOut)
def record(ref: str = Path(pattern=REF_PATTERN), user: User = Depends(current_user),
           session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> RecordOut:
    try:
        data = ledger.explain(session, user.business_id, ref, settings.demo_today)
    except ledger.RecordNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "record not found") from None
    return RecordOut(ref=ref, kind=ref.partition(":")[0], label=ledger.labels(session, user.business_id, [ref]).get(ref),
                     data=_plain(data))
