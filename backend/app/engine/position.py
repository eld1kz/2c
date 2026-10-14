"""Cash position now (SPEC §7 get_cash_position): cash at DEMO_TODAY against the minimum buffer."""

from dataclasses import dataclass

from app.engine.snapshot import Snapshot


@dataclass(frozen=True)
class CashPosition:
    as_of_cash: int  # cents, sum of account balances at the start of `as_of`
    currency: str
    min_cash_buffer: int
    headroom: int  # cash − buffer; negative when already below the buffer
    account_ids: tuple[int, ...]


def cash_position(snap: Snapshot) -> CashPosition:
    return CashPosition(snap.cash, snap.currency, snap.min_cash_buffer, snap.cash - snap.min_cash_buffer,
                        snap.account_ids)
