"""POST /whatif: the 13-week forecast before and after a scenario, for the what-if page (SPEC §6.5).

Owner and accountant only: simulations are SUGGEST tier, and viewers get READ (SPEC §8); a refusal
is audited. The engine computes everything; nothing is written. Scenario inputs are checked like the
agent's (services/scenarios.py) and come back as `assumptions`, each amount marked as taken from the
records or typed in ("supplied"), so the UI never presents an input as a verified figure.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_session
from app.api.routes_dashboard import gap_out
from app.api.schemas import AssumptionOut, EvidenceRef, WhatIfIn, WhatIfOut, WhatIfWeekOut
from app.audit import log as audit
from app.auth.rbac import can_propose
from app.config import Settings, get_settings
from app.db.models import Tier, User
from app.engine.forecast import project
from app.engine.snapshot import Snapshot, load_snapshot
from app.engine.whatif import (
    AddRecurring,
    CollectReceivable,
    DelayReceivable,
    OneOff,
    RemoveSeries,
    Scenario,
    ScenarioError,
    run_what_if,
)
from app.services import ledger
from app.services.action_service import actor_for, utc_now
from app.services.scenarios import check_targets, to_scenarios

router = APIRouter(tags=["whatif"])


def require_simulation_role(session: Session, user: User, tool: str) -> None:
    if not can_propose(user.role, Tier.SUGGEST, tool):
        audit.append(session, actor_for(user).label, "simulation_forbidden",
                     {"business_id": user.business_id, "role": user.role.value, "tool": tool}, now=utc_now())
        session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"role {user.role.value} may not run simulations")


def simulate(session: Session, user: User, body: WhatIfIn, settings: Settings) -> tuple[Snapshot, list[Scenario]]:
    """The caller's snapshot and the checked scenarios (422 on a bad target or value)."""
    snap = load_snapshot(session, user.business_id, settings.demo_today)
    scenarios = to_scenarios(body.scenarios, settings.demo_today)
    try:
        check_targets(session, user.business_id, snap.currency, settings.demo_today, scenarios)
    except ScenarioError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    return snap, scenarios


def _receivable(snap: Snapshot, ref: Callable[[str, int], EvidenceRef], invoice_id: int) -> dict[str, Any]:
    inv = snap.invoice_by_id.get(invoice_id)
    return {"invoice": ref("invoice", invoice_id), "amount_source": "records",
            "counterparty_name": snap.counterparties[inv.counterparty_id].name if inv else None,
            "amount_cents": inv.outstanding if inv else None}


def _assumption(session: Session, snap: Snapshot, s: Scenario) -> AssumptionOut:
    def ref(kind: str, id_: int) -> EvidenceRef:
        r = f"{kind}:{id_}"
        return EvidenceRef(ref=r, label=ledger.labels(session, snap.business_id, [r]).get(r))

    match s:
        case CollectReceivable(invoice_id, on):
            return AssumptionOut(type="collect_receivable", on=max(on, snap.as_of), **_receivable(snap, ref, invoice_id))
        case DelayReceivable(invoice_id, days):
            return AssumptionOut(type="delay_receivable", days=days, **_receivable(snap, ref, invoice_id))
        case RemoveSeries(series_id):
            series = next((x for x in snap.series if x.id == series_id), None)
            return AssumptionOut(type="remove_series", series=ref("recurring_series", series_id),
                                 counterparty_name=snap.counterparties[series.counterparty_id].name if series else None,
                                 amount_cents=series.amount if series else None, amount_source="records",
                                 cadence=series.cadence.value if series else None)
        case OneOff(amount, on):
            return AssumptionOut(type="one_off", on=on, amount_cents=amount, amount_source="supplied")
        case AddRecurring(amount, cadence, start):
            return AssumptionOut(type="add_recurring", on=start, cadence=cadence.value, amount_cents=amount,
                                 amount_source="supplied")
    raise ValueError(f"unsupported scenario {s!r}")  # pragma: no cover


@router.post("/whatif", response_model=WhatIfOut)
def whatif(body: WhatIfIn, user: User = Depends(current_user), session: Session = Depends(get_session),
           settings: Settings = Depends(get_settings)) -> WhatIfOut:
    require_simulation_role(session, user, "run_what_if")
    snap, scenarios = simulate(session, user, body, settings)
    base = project(snap)
    try:
        result = run_what_if(base, scenarios)
    except ScenarioError as e:  # e.g. the invoice is not an open receivable in this forecast
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    weeks = [WhatIfWeekOut(week=b.week, label=f"Week {b.week} ({b.start:%b} {b.start.day})", start=b.start,
                           end=b.start + timedelta(days=6), base_closing_cents=b.closing, scenario_closing_cents=s.closing,
                           change_cents=d, base_below_buffer=b.below_buffer, scenario_below_buffer=s.below_buffer)
             for b, s, d in zip(base.weeks, result.scenario.weeks, result.closing_delta)]
    return WhatIfOut(as_of=base.as_of, currency=base.currency, min_cash_buffer_cents=base.min_cash_buffer,
                     assumptions=[_assumption(session, snap, s) for s in scenarios], weeks=weeks,
                     base_gap=gap_out(base), scenario_gap=gap_out(result.scenario))
