"""Tool → permission tier (SPEC §7) and the parameter schemas of EXECUTE tools.

EXECUTE parameters are strict and closed (`extra="forbid"`): `schedule_payment` cannot carry a
payee name, beneficiary or bank/account field, so nothing from a document can introduce one.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.db.models import Tier

TOOL_TIERS: dict[str, Tier] = {
    "get_cash_position": Tier.READ,
    "get_ledger": Tier.READ,
    "get_forecast": Tier.READ,
    "get_insights": Tier.READ,
    "explain_record": Tier.READ,
    "run_what_if": Tier.SUGGEST,
    "rank_financing": Tier.SUGGEST,
    "draft_reminder": Tier.SUGGEST,
    "draft_terms_request": Tier.SUGGEST,
    "draft_cfo_memo": Tier.SUGGEST,
    "send_reminder": Tier.EXECUTE,
    "schedule_payment": Tier.EXECUTE,
    "submit_loan_application": Tier.EXECUTE,
}


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SendReminderParams(_Closed):
    invoice_id: StrictInt
    draft_id: StrictInt


class SchedulePaymentParams(_Closed):
    payee_counterparty_id: StrictInt
    invoice_id: StrictInt
    amount: StrictInt = Field(gt=0)  # cents
    date: date


class SubmitLoanApplicationParams(_Closed):
    option_id: StrictStr
    amount: StrictInt = Field(gt=0)  # cents


EXECUTE_PARAMS: dict[str, type[_Closed]] = {
    "send_reminder": SendReminderParams,
    "schedule_payment": SchedulePaymentParams,
    "submit_loan_application": SubmitLoanApplicationParams,
}


def tier_of(tool: str) -> Tier | None:
    return TOOL_TIERS.get(tool)
