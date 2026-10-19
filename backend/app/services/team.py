"""Team roster (SPEC §6.9): a fixed, labelled breakdown of the payroll series for display and what-if
prompts; not a staff data model.

The roster is fixed seed data (`seed/golden/team.json`, fictional people); nothing is stored and the
engine still sees payroll as one recurring series. Its weekly pay sums exactly to the payroll series
(tests/test_team.py); `matches_payroll` says whether that still holds for the current books. Pay is
for the owner and accountant only: for a viewer the API leaves every pay figure out.
"""

import json
from dataclasses import dataclass
from functools import lru_cache

from app.db.models import Cadence, Category
from app.engine.snapshot import SeriesFacts, Snapshot
from seed.generate_golden import GOLDEN_DIR

ROSTER_FILE = GOLDEN_DIR / "team.json"


@dataclass(frozen=True)
class Member:
    name: str
    role: str
    weekly_pay: int  # cents

    @property
    def initials(self) -> str:
        return "".join(part[0] for part in self.name.split()[:2]).upper()


@dataclass(frozen=True)
class Team:
    members: tuple[Member, ...]
    payroll: SeriesFacts | None  # the recurring payroll series the roster breaks down

    @property
    def weekly_total(self) -> int:
        return sum(m.weekly_pay for m in self.members)

    @property
    def matches_payroll(self) -> bool:
        return (self.payroll is not None and self.payroll.cadence == Cadence.weekly
                and self.weekly_total == abs(self.payroll.amount))


@lru_cache(maxsize=1)
def _roster() -> tuple[str, tuple[Member, ...]]:
    data = json.loads(ROSTER_FILE.read_text(encoding="utf-8"))
    return data["payroll_counterparty"], tuple(Member(p["name"], p["role"], p["weekly_pay_cents"]) for p in data["people"])


def team(snap: Snapshot) -> Team:
    counterparty, members = _roster()
    payroll = next((s for s in snap.series if s.category == Category.payroll
                    and snap.counterparties[s.counterparty_id].name == counterparty), None)
    return Team(members, payroll)
