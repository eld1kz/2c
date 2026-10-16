"""Evidence citations (SPEC §7, T7): every figure the agent states must cite a record it looked at.

`EvidenceIndex` collects, per conversation, every reference that appeared in a tool result and the
money amounts and percentages each one carries. `validate` checks the agent's final text:
- each [[type:id]] is well formed, of a known type, exists (DB records: in this business) and was
  seen in a tool result in this conversation;
- each sentence stating money or a percentage cites something (in the sentence, or else anywhere
  in the same line / bullet), and one of those citations carries that exact figure;
- a figure that only appears in a cited record's untrusted text (e.g. the amount an invoice note
  asks for) is accepted only when it is attributed to the document ("the note asks for") in the
  same line, or in the line introducing the list it is in;
- it does not claim an action was sent/paid/executed unless a tool result said `executed`.
Figures inside "untrusted_text" wrappers are kept apart (`quoted`), so a figure in a document can be
quoted as what the document says but never backs a statement of fact.
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
SENTENCE_END = re.compile(r"(?<=[.!?])[*_)\"'”’]*\s+|\n+")  # a full stop may be followed by **, ) or quotes
LEADING_CITATIONS = re.compile(r"^\s*((?:\[\[[^\[\]]{0,80}\]\]\s*)+)")
CLAIM = re.compile(  # "I sent …", "the payment has been scheduled"; not "QuickShip has paid on time"
    r"\b(?:i|we)(?:'ve| have)?\s+(?:just\s+|already\s+)?(?:sent|paid|scheduled|transferred|submitted|executed|emailed)\b"
    r"|\b(?:payments?|reminders?|emails?|applications?|transfers?|requests?|actions?|it|they)\s+"
    r"(?:has|have|was|were|is|are)\s+(?:now\s+|already\s+)?(?:been\s+)?"
    r"(?:sent|paid|scheduled|transferred|submitted|executed)\b",
    re.IGNORECASE)
BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s")
HEADING = re.compile(r"^\s*(?:#{1,6}\s+.*|\*\*[^*]+\*\*:?)\s*$")  # a markdown heading or a bold-only line
ATTRIBUTION = re.compile(
    r"\b(?:notes?|says?|said|asks?|asked|asking|claims?|claimed|requests?|requested|tells?|told|instructs?|"
    r"instructions?|states?|stated|wants?|demands?|wrote|written|mentions?|according to|quotes?|quoted)\b",
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
    quoted: dict[str, set[Figure]] = field(default_factory=dict)  # figures only in untrusted text
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
                quoted = {f for f, _ in figures_in(str(node[UNTRUSTED_KEY]))}
                for r in owners:
                    self.quoted.setdefault(r, set()).update(quoted)
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


def blocks(text: str) -> list[list[str]]:
    """Lines (paragraphs, bullets) split into sentences. Citations written just after a full stop, or
    on a line of their own, belong to the sentence before."""
    out: list[list[str]] = []
    for line in text.split("\n"):
        current: list[str] = []
        for part in SENTENCE_END.split(line):
            lead = LEADING_CITATIONS.match(part)
            target = current or (out[-1] if out else None)
            if lead and target:
                target[-1] += " " + lead.group(1).strip()
                part = part[lead.end():]
            if part.strip():
                current.append(part.strip())
        if current:
            out.append(current)
    return out


def sentences(text: str) -> list[str]:
    return [s for block in blocks(text) for s in block]


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
    all_blocks = blocks(text)
    intro = ""  # the line introducing the current bulleted list
    for n, block in enumerate(all_blocks):
        line = " ".join(block)
        if not BULLET.match(line):
            intro = line if line.rstrip().endswith(":") else ""
        attributed = bool(ATTRIBUTION.search(CITATION.sub(" ", f"{intro} {line}")))
        block_refs = [r for s in block for r in CITATION.findall(s)]
        if not block_refs and n + 1 < len(all_blocks) and HEADING.match(" ".join(block)):
            block_refs = [r for s in all_blocks[n + 1] for r in CITATION.findall(s)]  # a heading: its section
        for sentence in block:
            refs = CITATION.findall(sentence) or block_refs  # a citation at the end of the line covers it
            cited = [citations[r] for r in refs if citations[r].valid]
            plain = CITATION.sub(" ", sentence)
            for figure, written in figures_in(plain):
                if not refs:
                    problems.append(Problem("uncited_figure", f"'{written}' has no citation in its sentence or line"))
                elif cited and not any(figure in index.values.get(c.ref, set()) for c in cited):
                    names = ", ".join(f"[[{c.ref}]]" for c in cited)
                    if any(figure in index.quoted.get(c.ref, set()) for c in cited):
                        if not attributed:
                            problems.append(Problem("unsupported_figure", (
                                f"'{written}' appears only in document text of {names}; say it is what the "
                                "document says, not a fact")))
                    else:
                        problems.append(Problem("unsupported_figure", f"'{written}' does not appear in {names}"))
            if not executed and CLAIM.search(plain) and not HEDGE.search(plain):
                problems.append(Problem("claimed_execution",
                                        f"'{sentence[:80]}' claims an action happened, but no tool result says executed"))
    return CheckResult(tuple(citations.values()), tuple(problems))
