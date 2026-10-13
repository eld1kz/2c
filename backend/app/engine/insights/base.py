"""Shared types for insight detectors (SPEC §6.6). Every insight has a cents impact + evidence ids."""

from dataclasses import dataclass

from app.db.models import InsightType, Severity

ONCE = "once"
PER_YEAR = "year"
HIGH_ANNUAL_IMPACT = 500_000  # ≥ $5,000/yr
MED_ANNUAL_IMPACT = 100_000  # ≥ $1,000/yr


@dataclass(frozen=True)
class InsightSpec:
    type: InsightType
    severity: Severity
    title: str
    impact_amount: int  # cents, > 0
    impact_period: str
    evidence_ids: tuple[str, ...]  # most specific record first; it also identifies the insight

    @property
    def key(self) -> str:
        return insight_key(self.type, self.evidence_ids)


def insight_key(type_: str, evidence_ids: tuple[str, ...] | list[str]) -> str:
    return f"{type_}:{evidence_ids[0] if evidence_ids else ''}"


def annual_severity(impact: int) -> Severity:
    if impact >= HIGH_ANNUAL_IMPACT:
        return Severity.high
    return Severity.med if impact >= MED_ANNUAL_IMPACT else Severity.low


def money(cents: int, currency: str) -> str:
    sign = "−" if cents < 0 else ""
    body = f"{abs(cents) // 100:,}.{abs(cents) % 100:02d}"
    return f"{sign}${body}" if currency == "USD" else f"{sign}{currency} {body}"
