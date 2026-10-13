"""Fixed detector catalog (SPEC §6.6) and persistence of the resulting Insight rows.

Refreshing keeps insight ids stable: an insight is identified by type + first evidence id. Open
rows are updated in place or removed when no longer detected; dismissed/actioned rows are left
alone and never re-opened.
"""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Insight, InsightStatus
from app.engine.forecast import Forecast
from app.engine.insights import cash_gap, duplicate_subscription, late_payer, price_creep, unusual_expense
from app.engine.insights.base import InsightSpec, insight_key
from app.engine.snapshot import Snapshot

Detector = Callable[[Snapshot, Forecast], list[InsightSpec]]
DETECTORS: tuple[Detector, ...] = (
    late_payer.detect,
    duplicate_subscription.detect,
    price_creep.detect,
    cash_gap.detect,
    unusual_expense.detect,
)


def detect_all(snap: Snapshot, forecast: Forecast) -> list[InsightSpec]:
    return [spec for detector in DETECTORS for spec in detector(snap, forecast)]


def refresh_insights(session: Session, snap: Snapshot, forecast: Forecast) -> list[Insight]:
    """Store current detections; returns the business's open insights."""
    existing = {
        insight_key(row.type, row.evidence_ids): row
        for row in session.scalars(select(Insight).where(Insight.business_id == snap.business_id))
    }
    current: list[Insight] = []
    for spec in detect_all(snap, forecast):
        row = existing.pop(spec.key, None)
        if row is None:
            row = Insight(business_id=snap.business_id, status=InsightStatus.open)
            session.add(row)
        elif row.status != InsightStatus.open:
            continue
        row.type, row.severity, row.title = spec.type, spec.severity, spec.title
        row.impact_amount, row.currency, row.impact_period = spec.impact_amount, snap.currency, spec.impact_period
        row.evidence_ids, row.detected_at = list(spec.evidence_ids), snap.as_of
        current.append(row)
    for row in existing.values():
        if row.status == InsightStatus.open:
            session.delete(row)
    session.flush()
    return current
