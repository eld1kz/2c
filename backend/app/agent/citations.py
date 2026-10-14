"""Evidence citations (SPEC §7, T7): every figure the agent states must cite a record it looked at.

`EvidenceIndex` collects, per conversation, every reference that appeared in a tool result and the
money amounts and percentages each one carries. `validate` checks the agent's final text:
- each [[type:id]] is well formed, of a known type, exists (DB records: in this business) and was
  seen in a tool result in this conversation;
- each sentence stating money or a percentage cites something, and one of its citations carries
  that exact figure;
- it does not claim an action was sent/paid/executed unless a tool result said `executed`.
Text inside "untrusted_text" wrappers is never indexed, so a figure in a document cannot back a claim.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.services.ledger import REF_TYPES

COMPUTED_TYPES = ("forecast_week", "whatif", "financing")
KNOWN_TYPES = (*REF_TYPES, *COMPUTED_TYPES)
UNTRUSTED_KEY = "untrusted_text"

CITATION = re.compile(r"\[\[([^\[\]]{0,80})\]\]")
REF = re.compile(r"^([a-z_]+):([A-Za-z0-9_]+)$")
MONEY = re.compile(r"(?<![\w.,])[−-]?\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?(?!\d|[.,]\d)")
PERCENT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?%")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
LEADING_CITATIONS = re.compile(r"^\s*((?:\[\[[^\[\]]{0,80}\]\]\s*)+)")
CLAIM = re.compile(
    r"\b(?:i|we)(?:'ve| have)?\s+(?:sent|paid|scheduled|transferred|submitted|executed|emailed)\b"
    r"|\b(?:has|have|was|were|is|are)\s+(?:been\s+)?(?:sent|paid|scheduled|transferred|submitted|executed)\b",
    re.IGNORECASE)
HEDGE = re.compile(r"\b(?:not|no|nothing|never|until|once|after|when|if|unless|awaiting|pending|will|would)\b|n't",
                   re.IGNORECASE)
UNVERIFIED_NOTICE = "⚠ Some figures in this answer could not be verified against your records."

Figure = tuple[str, str]  # ("money", "480000") or ("pct", "18")


def money_cents(whole: str, cents: str | None) -> int:
    return int(whole.replace(",", "")) * 100 + int(cents or 0)


def figures_in(text: str) -> list[tuple[Figure, str]]:
    """(figure, as written) for every money amount and percentage in `text`."""
    found = [(("money", str(money_cents(m.group(1), m.group(2)))), m.group(0)) for m in MONEY.finditer(text)]
    return found + [(("pct", str(float(m.group(1)))), m.group(0)) for m in PERCENT.finditer(text)]


@dataclass
class EvidenceIndex:
    seen: set[str] = field(default_factory=set)
    values: dict[str, set[Figure]] = field(default_factory=dict)
    computed: set[str] = field(default_factory=set)
    labels: dict[str, str] = field(default_factory=dict)

    def add_computed(self, ref: str, label: str) -> None:
        self.computed.add(ref)
        self.labels[ref] = label

    def add_result(self, data: Any) -> None:
        self._walk(data, ())

    def _walk(self, node: Any, owners: tuple[str, ...]) -> set[Figure]:
        """Index `node`; returns the figures found in it so ancestors can carry them too."""
        figures: set[Figure] = set()
        if isinstance(node, dict):
            if UNTRUSTED_KEY in node:
                return figures
            own = node.get("ref")
            refs = owners
            if isinstance(own, str) and REF.match(own):
                refs = (*owners, own)
            linked = [r for key in ("evidence_ids", "source_ids") for r in node.get(key) or [] if isinstance(r, str)]
            for key, value in node.items():
                if key.endswith("_cents"):
                    for v in value if isinstance(value, list) else [value]:
                        if isinstance(v, int) and not isinstance(v, bool):
                            figures.add(("money", str(abs(v))))
                else:
                    figures |= self._walk(value, refs)
            for r in (*refs[len(owners):], *linked):
                self.values.setdefault(r, set()).update(figures)
            if isinstance(own, str) and isinstance(node.get("label"), str):
                self.labels.setdefault(own, node["label"])
        elif isinstance(node, list):
            for item in node:
                figures |= self._walk(item, owners)
        elif isinstance(node, str):
            match = REF.match(node)
            if match and match.group(1) in KNOWN_TYPES:
                self.seen.add(node)
            figures |= {f for f, _ in figures_in(node)}
        return figures


@dataclass(frozen=True)
class Citation:
    ref: str
    valid: bool
    label: str
    reason: str | None = None


@dataclass(frozen=True)
class Problem:
    kind: str  # malformed | unknown_type | not_found | not_retrieved | uncited_figure | unsupported_figure | claimed_execution
    detail: str


@dataclass(frozen=True)
class CheckResult:
    citations: tuple[Citation, ...]
    problems: tuple[Problem, ...]

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def warnings(self) -> list[str]:
        return [p.detail for p in self.problems]

    def feedback(self) -> str:
        lines = "\n".join(f"- {p.detail}" for p in self.problems)
        return ("[Automatic check by Ledgerwise, not the user] Your last answer failed the evidence check:\n"
                f"{lines}\nRewrite the whole answer. Use only figures that appear in tool results, cite each "
                "one in the same sentence with a [[type:id]] reference taken from those results, and do not "
                "say that anything was sent, paid, scheduled or executed unless a tool result says executed.")


def sentences(text: str) -> list[str]:
    """Split into sentences; citations written just after a full stop belong to the sentence before."""
    out: list[str] = []
    for part in SENTENCE_END.split(text):
        lead = LEADING_CITATIONS.match(part)
        if lead and out:
            out[-1] += " " + lead.group(1).strip()
            part = part[lead.end():]
        if part.strip():
            out.append(part.strip())
    return out


def _check_ref(raw: str, index: EvidenceIndex, exists: Callable[[str], bool]) -> Citation:
    match = REF.match(raw.strip())
    if match is None:
        return Citation(raw, False, raw, "malformed")
    kind, ref = match.group(1), raw.strip()
    if kind not in KNOWN_TYPES:
        return Citation(ref, False, ref, "unknown_type")
    if kind in COMPUTED_TYPES:
        if ref not in index.computed:
            return Citation(ref, False, ref, "not_found")
    elif not exists(ref):
        return Citation(ref, False, ref, "not_found")
    if ref not in index.seen and ref not in index.computed:
        return Citation(ref, False, ref, "not_retrieved")
    return Citation(ref, True, index.labels.get(ref, ref))


REASON_TEXT = {
    "malformed": "is not a valid [[type:id]] reference",
    "unknown_type": "has an unknown type",
    "not_found": "does not exist",
    "not_retrieved": "was not returned by any tool in this conversation",
}


def validate(text: str, index: EvidenceIndex, exists: Callable[[str], bool], executed: bool = False) -> CheckResult:
    citations: dict[str, Citation] = {}
    problems: list[Problem] = []
    for raw in CITATION.findall(text):
        if raw not in citations:
            citations[raw] = c = _check_ref(raw, index, exists)
            if not c.valid:
                problems.append(Problem(c.reason or "invalid", f"[[{raw}]] {REASON_TEXT.get(c.reason or '', 'is invalid')}"))
    for sentence in sentences(text):
        cited = [citations[r] for r in CITATION.findall(sentence) if citations[r].valid]
        plain = CITATION.sub(" ", sentence)
        for figure, written in figures_in(plain):
            if not CITATION.search(sentence):
                problems.append(Problem("uncited_figure", f"'{written}' has no citation in its sentence"))
            elif cited and not any(figure in index.values.get(c.ref, set()) for c in cited):
                refs = ", ".join(f"[[{c.ref}]]" for c in cited)
                problems.append(Problem("unsupported_figure", f"'{written}' does not appear in {refs}"))
        if not executed and CLAIM.search(plain) and not HEDGE.search(plain):
            problems.append(Problem("claimed_execution",
                                    f"'{sentence[:80]}' claims an action happened, but no tool result says executed"))
    return CheckResult(tuple(citations.values()), tuple(problems))
