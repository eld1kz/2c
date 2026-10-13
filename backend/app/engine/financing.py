"""Financing option ranking for a cash gap (SPEC §6.7). Sandbox catalog, simulated terms.

Takes any Gap — from the base forecast or from a what-if scenario — plus that forecast, and
returns every option with its effective cost in cents and how much of the gap it can cover.
Options that cover the whole gap rank first, then by cost.

What each option can cover, from the forecast's own lines:
- receivable options (factoring, early-pay discount): open receivables expected on/after the gap
  starts (earlier ones are already in the cash), excluding at-risk ones (probability 0);
- supplier terms extension: invoice-backed payables to suppliers with a good payment history,
  due between the gap start and the end of its lowest week, that +30 days pushes past that week.
Receivables/payables already moved by a what-if scenario are not offered again.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from app.db.models import CounterpartyKind, ForecastLineKind
from app.engine.forecast import Forecast, Gap, Line
from app.engine.snapshot import Snapshot

NOT_FINANCIAL_ADVICE = "Simulated sandbox offers for illustration only. Not financial advice."
DAYS_PER_YEAR = 365
BP = 10_000  # basis points per 1

OVERDRAFT_APR_BP = 1_800
OVERDRAFT_LIMIT = 1_500_000
LOAN_APR_BP = 1_200
LOAN_MIN_DAYS = 91
LOAN_MAX = 5_000_000
FACTORING_ADVANCE_PCT = 85
FACTORING_FEE_BP_PER_30_DAYS = 250
EARLY_PAY_DISCOUNT_BP = 200
TERMS_EXTENSION_DAYS = 30
GOOD_SUPPLIER_ON_TIME_RATE = 0.9
GOOD_SUPPLIER_MIN_INVOICES = 3


@dataclass(frozen=True)
class FinancingOption:
    option_id: str
    name: str
    cost: int  # cents for this gap
    max_amount: int  # cents this option can provide for this gap
    covers_gap: bool
    pros: tuple[str, ...]
    cons: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class FinancingRanking:
    gap: Gap
    currency: str
    options: tuple[FinancingOption, ...]
    disclaimer: str = NOT_FINANCIAL_ADVICE


def _touched_by_scenario(forecast: Forecast) -> set[str]:
    return {s for ln in forecast.lines if ln.kind == ForecastLineKind.scenario for s in ln.source_ids}


def _receivables_after_gap_start(gap: Gap, forecast: Forecast, touched: set[str]) -> list[Line]:
    return [
        ln for ln in forecast.lines
        if ln.kind == ForecastLineKind.ar_expected and ln.probability_bp > 0 and ln.on >= gap.start
        and not touched.intersection(ln.source_ids)
    ]


def _deferrable_payables(gap: Gap, forecast: Forecast, snap: Snapshot, touched: set[str]) -> list[Line]:
    def good(cp_id: int | None) -> bool:
        cp = snap.counterparties.get(cp_id) if cp_id is not None else None
        return (cp is not None and cp.kind in (CounterpartyKind.supplier, CounterpartyKind.both)
                and cp.stats.get("invoices_count", 0) >= GOOD_SUPPLIER_MIN_INVOICES
                and cp.stats.get("on_time_rate", 0) >= GOOD_SUPPLIER_ON_TIME_RATE)

    return [
        ln for ln in forecast.lines
        if ln.kind in (ForecastLineKind.ap_due, ForecastLineKind.recurring) and ln.face < 0
        and ln.source_ids[0].startswith("invoice:") and good(ln.counterparty_id)
        and gap.start <= ln.on <= gap.low_week_end < ln.on + timedelta(days=TERMS_EXTENSION_DAYS)
        and not touched.intersection(ln.source_ids)
    ]


def _option(option_id: str, name: str, cost: int, max_amount: int, gap: Gap, pros: tuple[str, ...],
            cons: tuple[str, ...], evidence: Sequence[Line] = ()) -> FinancingOption:
    ids = tuple(dict.fromkeys(s for ln in evidence for s in ln.source_ids))
    return FinancingOption(option_id, name, cost, max_amount, max_amount >= gap.amount, pros, cons, ids)


def rank_financing(gap: Gap, forecast: Forecast, snap: Snapshot) -> FinancingRanking:
    amount, days = gap.amount, gap.days
    touched = _touched_by_scenario(forecast)
    receivables = _receivables_after_gap_start(gap, forecast, touched)
    receivable_face = sum(ln.face for ln in receivables)
    payables = _deferrable_payables(gap, forecast, snap, touched)
    advance_cap = receivable_face * FACTORING_ADVANCE_PCT // 100
    advanced = min(amount, advance_cap)
    factored_face = -(-advanced * 100 // FACTORING_ADVANCE_PCT)
    periods = -(-days // 30)

    options = [
        _option("overdraft", "Sandbox bank overdraft (18% APR)",
                amount * OVERDRAFT_APR_BP * days // (BP * DAYS_PER_YEAR), OVERDRAFT_LIMIT, gap,
                ("Pay interest only on days used", "Available immediately"),
                ("Highest APR in the catalog", "Lender can reduce the limit")),
        _option("short_term_loan", "Sandbox short-term loan (12% APR, 91-day minimum)",
                amount * LOAN_APR_BP * max(days, LOAN_MIN_DAYS) // (BP * DAYS_PER_YEAR), LOAN_MAX, gap,
                ("Lower APR than overdraft", "Fixed schedule"),
                ("Interest for at least 91 days", "Needs an application and approval")),
        _option("invoice_factoring", "Sandbox invoice factoring (85% advance, 2.5% per 30 days)",
                factored_face * FACTORING_FEE_BP_PER_30_DAYS * periods // BP, advance_cap, gap,
                ("Cash against invoices already issued",),
                ("Only invoices expected after the gap starts help", "Customer may learn of the factor"),
                receivables),
        _option("supplier_terms_extension", f"Ask suppliers for +{TERMS_EXTENSION_DAYS} days on payment terms",
                0, -sum(ln.face for ln in payables), gap,
                ("No cost", "Suppliers with a clean payment record"),
                ("Supplier must agree", "Pushes the payments into a later week"),
                payables),
        _option("accelerate_receivables", "Offer customers a 2% early-payment discount",
                min(amount, receivable_face) * EARLY_PAY_DISCOUNT_BP // BP, receivable_face, gap,
                ("No debt", "Improves collections"),
                ("Customer must take the offer", "Discount is permanent revenue loss"),
                receivables),
    ]
    options.sort(key=lambda o: (not o.covers_gap, o.cost, o.option_id))
    return FinancingRanking(gap, forecast.currency, tuple(options))
