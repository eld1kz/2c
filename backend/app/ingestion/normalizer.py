"""Description normalization, invoice-reference extraction and counterparty matching (SPEC §6.1).

`normalize` reduces a raw bank description to `[A-Z0-9 ]` tokens with card numbers, terminal
IDs, dates, phones and invoice refs removed. The result is safe to show an LLM as data (T1, T8).
"""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

FUZZY_THRESHOLD = 90
FUZZY_MARGIN = 5  # best must beat the runner-up by this much, else ambiguous

INVOICE_REF = re.compile(r"\b([A-Z]{2,4})[\s-]?(\d{3,6})\b")
_NOISE = [
    re.compile(p)
    for p in (
        r"\bCARD \d{4}\b",
        r"\bTID \d+\b",
        r"\bPPD ID:\s*\d+\b",
        r"\b\d{3}-\d{3}-\d{4}\b",
        r"\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}\b",
        r"\b\d{4}\b",
        r"\.(?:IO|COM|NET)\b",
        r"^\s*(?:ACH DEBIT|ACH CREDIT|MOBILE XFER|POS PURCHASE)\b",
    )
]
ABBREVIATIONS = {
    "GRP": "GROUP", "UTIL": "UTILITIES", "PKG": "PACKAGING", "ACCTG": "ACCOUNTING",
    "EQUIP": "EQUIPMENT", "FIN": "FINANCE", "IMP": "IMPORTS", "ST": "STREET",
}


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def invoice_key(number: str) -> str:
    """Canonical lookup key: `INV-1024`, `INV1024` and `INV 1024` all become `INV1024`."""
    return re.sub(r"[^A-Z0-9]", "", number.upper())


def extract_invoice_refs(raw: str) -> list[str]:
    return [m.group(1) + m.group(2) for m in INVOICE_REF.finditer(_fold(raw))]


def normalize(raw: str) -> str:
    s = INVOICE_REF.sub(" ", _fold(raw))
    for pattern in _NOISE:
        s = pattern.sub(" ", s)
    s = re.sub(r"(?<=[A-Z])-(?=[A-Z])", "", s)  # CO-WORK -> COWORK
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    tokens: list[str] = []
    for token in s.split():
        token = ABBREVIATIONS.get(token, token)
        if token not in tokens:
            tokens.append(token)
    return " ".join(tokens)


@dataclass(frozen=True)
class Match:
    counterparty_id: int
    how: str  # "exact" | "fuzzy"


def match_counterparty(name: str, counterparties: dict[int, str]) -> Match | None:
    """Exact on normalized_name, then token_set_ratio ≥ 90 with a clear margin. Never creates one."""
    if not name:
        return None
    for cp_id, cp_name in counterparties.items():
        if cp_name == name:
            return Match(cp_id, "exact")
    scored = sorted(((fuzz.token_set_ratio(name, cp_name), cp_id) for cp_id, cp_name in counterparties.items()),
                    reverse=True)
    if not scored or scored[0][0] < FUZZY_THRESHOLD:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < FUZZY_MARGIN:
        return None
    return Match(scored[0][1], "fuzzy")
