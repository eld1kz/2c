"""Plaid sandbox bank feed: a fictional statement served back through Plaid's real Transactions API.

Sandbox only: the host is a constant and there is no setting for Plaid's production environment
(SPEC §2: no real bank connections). We create a sandbox Item for Plaid's custom user, loaded with
`seed/golden/plaid_feed.json`, then read it back with /transactions/get. The access token lives only
for the request. Feed text is untrusted and goes through the same pipeline as a CSV (T1).
Money never touches a float: Plaid JSON is parsed with Decimal, and the feed stores integer cents.
"""

import json
import re
import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from app.ingestion.csv_parser import ParsedRow

PLAID_SANDBOX_URL = "https://sandbox.plaid.com"
SANDBOX_INSTITUTION = "ins_109508"  # Plaid's "First Platypus Bank" test institution
FEED_FILE = Path(__file__).resolve().parents[2] / "seed" / "golden" / "plaid_feed.json"
PAGE_SIZE = 500
READY_ATTEMPTS = 10
_AMOUNT_TOKEN = re.compile(r'"__CENTS_(-?\d+)__"')


class PlaidError(Exception):
    """Carries Plaid's error_code only, never a response body."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _cents_literal(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def custom_user_config(feed: dict[str, Any]) -> str:
    """The user_custom password: Plaid's override_accounts JSON, amounts written as exact decimals."""
    account = feed["account"]
    config = {
        "override_accounts": [{
            "type": "depository",
            "subtype": "checking",
            "starting_balance": f"__CENTS_{account['starting_balance_cents']}__",
            "meta": {"name": account["name"]},
            "transactions": [
                {"date_transacted": t["date"], "date_posted": t["date"], "currency": "USD",
                 "description": t["description"], "amount": f"__CENTS_{t['amount_cents']}__"}
                for t in feed["transactions"]
            ],
        }],
    }
    return _AMOUNT_TOKEN.sub(lambda m: _cents_literal(int(m.group(1))), json.dumps(config))


def load_feed(path: Path = FEED_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def feed_window(feed: dict[str, Any]) -> tuple[date, date]:
    dates = [date.fromisoformat(t["date"]) for t in feed["transactions"]]
    return min(dates), max(dates)


def to_cents(amount: Decimal) -> int:
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise PlaidError("AMOUNT_NOT_IN_CENTS")
    return int(cents)


def to_rows(transactions: list[dict[str, Any]]) -> list[ParsedRow]:
    """Plaid transactions → ParsedRows. Plaid amounts are positive for money out, so the sign flips."""
    rows = [
        ParsedRow(
            line_no=i,
            date=date.fromisoformat(t["date"]),
            amount=-to_cents(Decimal(t["amount"])),
            description=str(t.get("original_description") or t.get("name") or "")[:255],
            balance=None,
        )
        for i, t in enumerate(transactions, start=1)
        if not t.get("pending")
    ]
    return sorted(rows, key=lambda r: (r.date, r.line_no))


class PlaidSandboxClient:
    def __init__(self, client_id: str, secret: str, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._auth = {"client_id": client_id, "secret": secret}
        self._http = httpx.Client(base_url=PLAID_SANDBOX_URL, timeout=15.0, transport=transport)
        self._sleep = sleep

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            r = self._http.post(path, json=self._auth | body)
        except httpx.HTTPError as e:
            raise PlaidError("NETWORK_ERROR") from e
        try:
            data = json.loads(r.content, parse_float=Decimal)
        except ValueError as e:
            raise PlaidError("BAD_RESPONSE") from e
        if r.status_code != 200:
            code = data.get("error_code") if isinstance(data, dict) else None
            raise PlaidError(str(code or f"HTTP_{r.status_code}")[:64])
        return data

    def create_item(self, feed: dict[str, Any]) -> str:
        data = self._post("/sandbox/public_token/create", {
            "institution_id": SANDBOX_INSTITUTION,
            "initial_products": ["transactions"],
            "options": {"override_username": "user_custom", "override_password": custom_user_config(feed)},
        })
        return str(data["public_token"])

    def exchange(self, public_token: str) -> tuple[str, str]:
        data = self._post("/item/public_token/exchange", {"public_token": public_token})
        return str(data["access_token"]), str(data["item_id"])

    def transactions(self, access_token: str, start: date, end: date) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while True:
            body = {"access_token": access_token, "start_date": start.isoformat(), "end_date": end.isoformat(),
                    "options": {"count": PAGE_SIZE, "offset": len(out), "include_original_description": True}}
            for attempt in range(READY_ATTEMPTS):
                try:
                    data = self._post("/transactions/get", body)
                    break
                except PlaidError as e:
                    if e.code != "PRODUCT_NOT_READY" or attempt == READY_ATTEMPTS - 1:
                        raise
                    self._sleep(1.0)
            out.extend(data["transactions"])
            if not data["transactions"] or len(out) >= int(data["total_transactions"]):
                return out


def fetch_feed(client: PlaidSandboxClient, feed: dict[str, Any]) -> tuple[str, list[ParsedRow]]:
    """Create a sandbox Item loaded with the feed and read it back. Returns (item_id, rows)."""
    access_token, item_id = client.exchange(client.create_item(feed))
    start, end = feed_window(feed)
    return item_id, to_rows(client.transactions(access_token, start, end))
