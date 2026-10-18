"""Tool → permission tier (SPEC §7) and the parameter schemas of EXECUTE tools.

EXECUTE parameters are strict and closed (`extra="forbid"`): `schedule_payment` cannot carry a
payee name, beneficiary or bank/account field, so nothing from a document can introduce one; the two
email tools take a record id and a draft id only, never an address, subject or body.
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
    "draft_price_request": Tier.SUGGEST,
    "send_reminder": Tier.EXECUTE,
    "send_terms_request": Tier.EXECUTE,
    "send_price_request": Tier.EXECUTE,
    "schedule_payment": Tier.EXECUTE,
    "submit_loan_application": Tier.EXECUTE,
}


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SendReminderParams(_Closed):
    invoice_id: StrictInt
    draft_id: StrictInt


class SendTermsRequestParams(_Closed):
    counterparty_id: StrictInt  # the supplier; the email goes to its stored contact_email
    draft_id: StrictInt  # a draft_terms_request for that supplier (fixed template)


class SendPriceRequestParams(_Closed):
    counterparty_id: StrictInt  # the supplier; the email goes to its stored contact_email
    draft_id: StrictInt  # a draft_price_request for that supplier (fixed template)


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
    "send_terms_request": SendTermsRequestParams,
    "send_price_request": SendPriceRequestParams,
    "schedule_payment": SchedulePaymentParams,
    "submit_loan_application": SubmitLoanApplicationParams,
}


def tier_of(tool: str) -> Tier | None:
    return TOOL_TIERS.get(tool)
