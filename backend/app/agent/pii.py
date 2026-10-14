"""PII masking before anything reaches the LLM (SPEC §7, T8).

IBANs, card numbers, bank account numbers, emails and phone numbers in *strings* are replaced by
tokens such as ⟨ACCOUNT_1⟩. Integers (cents, ids) are never touched. One vault per conversation, so
the same value always gets the same token; the vault stays on the server and `unmask` is used only
for text shown to the signed-in user. Execution never needs unmasking: the sandbox uses stored
counterparty details only.
"""

import re
from typing import Any

TOKEN_OPEN, TOKEN_CLOSE = "⟨", "⟩"
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b")),
    ("CARD", re.compile(r"\b\d{4}(?:[ -]\d{4}){2,3}(?:[ -]\d{1,3})?\b")),
    ("ACCOUNT", re.compile(r"\b\d{8,19}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"(?<![\w+])(?:\+\d[\d ().-]{7,}\d|\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b)")),
)
TOKEN = re.compile(f"{TOKEN_OPEN}([A-Z]+_\\d+){TOKEN_CLOSE}")


class PiiVault:
    def __init__(self) -> None:
        self._token_of: dict[str, str] = {}
        self._value_of: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def _token(self, kind: str, value: str) -> str:
        if value not in self._token_of:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            token = f"{TOKEN_OPEN}{kind}_{self._counts[kind]}{TOKEN_CLOSE}"
            self._token_of[value], self._value_of[token] = token, value
        return self._token_of[value]

    def mask_text(self, text: str) -> str:
        for kind, pattern in PATTERNS:
            text = pattern.sub(lambda m, k=kind: self._token(k, m.group(0)), text)
        return text

    def mask(self, value: Any) -> Any:
        """Mask every string inside a JSON-like value; other types pass through unchanged."""
        if isinstance(value, str):
            return self.mask_text(value)
        if isinstance(value, dict):
            return {k: self.mask(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.mask(v) for v in value]
        return value

    def unmask(self, text: str) -> str:
        return TOKEN.sub(lambda m: self._value_of.get(m.group(0), m.group(0)), text)


def strip_token_marks(text: str) -> str:
    """Remove token brackets from untrusted text so it cannot forge a PII token."""
    return text.replace(TOKEN_OPEN, "").replace(TOKEN_CLOSE, "")
