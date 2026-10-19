"""Team (SPEC §6.9): GET /team, the fixed roster that breaks down the payroll series (services/team.py).

Any signed-in role, read-only, no model. Viewers get names, roles and initials only: the API leaves
every pay figure out for them, so hiding it is not left to the UI.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_session
from app.api.schemas import EvidenceRef, TeamMemberOut, TeamOut
from app.config import Settings, get_settings
from app.db.models import Role, User
from app.engine.snapshot import load_snapshot
from app.services import ledger
from app.services.team import team

router = APIRouter(tags=["team"])


def pay_visible(user: User) -> bool:
    return user.role != Role.viewer


@router.get("/team", response_model=TeamOut)
def get_team(user: User = Depends(current_user), session: Session = Depends(get_session),
             settings: Settings = Depends(get_settings)) -> TeamOut:
    t = team(load_snapshot(session, user.business_id, settings.demo_today))
    show = pay_visible(user)
    payroll = None
    if t.payroll is not None:
        ref = f"recurring_series:{t.payroll.id}"
        payroll = EvidenceRef(ref=ref, label=ledger.labels(session, user.business_id, [ref]).get(ref))
    return TeamOut(
        people=[TeamMemberOut(name=m.name, role=m.role, initials=m.initials, weekly_pay_cents=m.weekly_pay if show else None)
                for m in t.members],
        weekly_total_cents=t.weekly_total if show else None, payroll=payroll, matches_payroll=t.matches_payroll,
        pay_visible=show)
