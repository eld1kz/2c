"""Evidence citations (SPEC §7, T7): every figure the agent states must cite a record it looked at.

`EvidenceIndex` collects, per conversation, every reference that appeared in a tool result and the
money amounts and percentages each one carries. `validate` checks the agent's final text:
- each [[type:id]] is well formed, of a known type, exists (DB records: in this business) and was
  seen in a tool result in this conversation;
- each sentence stating money or a percentage cites something (in the sentence, or else anywhere
  in the same line / bullet), and one of those citations carries that exact figure;
- a figure that only appears in a cited record's untrusted text (e.g. the amount an invoice note
  asks for) is accepted only when it is explicitly framed as a quote: inside quotation marks, or
  after "the note says / the invoice text claims …" in the same sentence;
- it does not claim an action was sent/paid/executed/approved/done unless a tool result in this turn
  said `executed`.
Figures inside "untrusted_text" wrappers are kept apart (`quoted`), so a figure in a document can be
quoted as what the document says but never backs a statement of fact. Values someone supplied
rather than the engine derived (under a `supplied_input` key: what-if scenario inputs, action params
and rationales) and a what-if's per-week `change_cents` (which equals the scenario input) are never
evidence at all.
Money is recognised as $1,234.56, ＄1,234 (text is NFKC-normalised first), USD 1,234 and
1,234 dollars; bare numbers such as day or week counts are not checked.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.services.ledger import REF_TYPES

COMPUTED_TYPES = ("forecast_week", "whatif", "financing")
KNOWN_TYPES = (*REF_TYPES, *COMPUTED_TYPES)
UNTRUSTED_KEY = "untrusted_text"
SUPPLIED_KEY = "supplied_input"  # values the model (or a user) chose: shown, never evidence
NOT_EVIDENCE_KEYS = frozenset({SUPPLIED_KEY, "change_cents", "change_display"})

CITATION = re.compile(r"\[\[([^\[\]]{0,80})\]\]")
REF = re.compile(r"^([a-z_]+):([A-Za-z0-9_]+)$")
_AMOUNT = r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?(?!\d|[.,]\d)"
MONEY = re.compile(r"(?<![\w.,])[−-]?(?:US\$|USD\s?|\$)\s?" + _AMOUNT)  # $1,234.56 / USD 1,234
MONEY_WORD = re.compile(r"(?<![\w.,$])[−-]?" + _AMOUNT + r"\s?(?:dollars?|USD)\b", re.IGNORECASE)  # 1,234 dollars
PERCENT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?%")
SENTENCE_END = re.compile(r"(?<=[.!?])[*_)\"'”’]*\s+|\n+")  # a full stop may be followed by **, ) or quotes
LEADING_CITATIONS = re.compile(r"^\s*((?:\[\[[^\[\]]{0,80}\]\]\s*)+)")
_DONE = (r"(?:sent|paid|scheduled|transferred|submitted|executed|emailed|approved|completed?|done|processed|"
         r"wired|settled|delivered|made|initiated|carried out|taken care of)")
_ACTION = r"(?:payments?|reminders?|emails?|applications?|transfers?|requests?|actions?|wires?|loans?)"
_ADV = r"(?:(?:now|already|just|successfully|also|fully|finally)\s+)*"
CLAIM = re.compile(  # past or perfect tense about an action; a negation must sit right next to the verb
    rf"\b(?:i|we)(?:'ve|'d| have| had)?\s+{_ADV}{_DONE}\b"  # I sent / we've paid / I approved and executed
    rf"|\b(?:{_ACTION}|it|they|this|that|everything)\b(?:\s+(?!not\b|never\b)[\w'-]+){{0,5}}?\s+"
    rf"(?:has|have|had|was|were|is|are|got)\s+{_ADV}(?:been\s+{_ADV})?{_DONE}\b"  # the payment … was sent / is complete
    rf"|(?<!no )(?<!not )\b{_ACTION}\s+(?:sent|went out|executed|approved|completed|done|paid|submitted|delivered|"
    rf"processed|wired)\b"  # "Payment sent to QuickShip", "the reminder went out"
    rf"|\b(?!(?:nothing|none|no|not|neither)\b)[\w-]+\s+(?:has|have)\s+{_ADV}been\s+{_ADV}"
    rf"(?:paid|sent|executed|transferred|wired|approved|submitted|scheduled|settled)\b"  # QuickShip has been paid
    rf"|\b(?:has gone out|it'?s (?:done|complete|sent|paid))\b"
    rf"|^\W*done\b",  # "Done: …"
    re.IGNORECASE)
HEADING = re.compile(r"^\s*(?:#{1,6}\s+.*|\*\*[^*]+\*\*:?)\s*$")  # a markdown heading or a bold-only line
QUOTE_FRAME = re.compile(  # "the note says", "the invoice text claims", "according to the note"
    r"\b(?:the|this|that|its|qs-\d+'s|[\w-]+'s)\s+(?:invoice\s+|supplier'?s?\s+)?"
    r"(?:notes?|memo|invoice text|text|document|description|line description|message|instruction)"
    r"(?:\s+(?:on|in|of|from|for|attached to)\s+(?:the\s+)?[\w-]+)?\s+"  # "the note on QS-2291 says"
    r"(?:says?|said|asks?|asked|claims?|claimed|requests?|requested|states?|stated|demands?|demanded|tells?|told|"
    r"instructs?|instructed|wants?|wanted|reads?)\b|\baccording to the (?:invoice\s+)?(?:notes?|memo|document|text)\b",
    re.IGNORECASE)
QUOTED_SPAN = re.compile(r"\"[^\"]*\"|“[^”]*”")
UNVERIFIED_NOTICE = "⚠ Some figures in this answer could not be verified against your records."

Figure = tuple[str, str]  # ("money", "480000") or ("pct", "18")


def money_cents(whole: str, cents: str | None) -> int:
    return int(whole.replace(",", "")) * 100 + int(cents or 0)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text)  # ＄ → $, fullwidth digits → ASCII


def _figure_matches(text: str) -> list[tuple[Figure, str, int]]:
    """(figure, as written, position) for every money amount and percentage in normalised `text`."""
    found = [(("money", str(money_cents(m.group(1), m.group(2)))), m.group(0), m.start()) for m in MONEY.finditer(text)]
    spans = [range(m.start(), m.end()) for m in MONEY.finditer(text)]
    found += [(("money", str(money_cents(m.group(1), m.group(2)))), m.group(0), m.start())
              for m in MONEY_WORD.finditer(text) if not any(m.start() in r for r in spans)]
    return found + [(("pct", str(float(m.group(1)))), m.group(0), m.start()) for m in PERCENT.finditer(text)]


def figures_in(text: str) -> list[tuple[Figure, str]]:
    return [(f, w) for f, w, _ in _figure_matches(normalize(text))]


def framed_as_quote(sentence: str, position: int) -> bool:
    """Whether the figure at `position` is explicitly quoted: inside quotation marks, or after
    "the note says …" earlier in the same sentence."""
    if any(m.start() < position < m.end() for m in QUOTED_SPAN.finditer(sentence)):
        return True
    return any(m.end() <= position for m in QUOTE_FRAME.finditer(sentence))


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
                if key in NOT_EVIDENCE_KEYS:
                    continue
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
    text = normalize(text)
    citations: dict[str, Citation] = {}
    problems: list[Problem] = []
    for raw in CITATION.findall(text):
        if raw not in citations:
            citations[raw] = c = _check_ref(raw, index, exists)
            if not c.valid:
                problems.append(Problem(c.reason or "invalid", f"[[{raw}]] {REASON_TEXT.get(c.reason or '', 'is invalid')}"))
    all_blocks = blocks(text)
    for n, block in enumerate(all_blocks):
        block_refs = [r for s in block for r in CITATION.findall(s)]
        if not block_refs and n + 1 < len(all_blocks) and HEADING.match(" ".join(block)):
            block_refs = [r for s in all_blocks[n + 1] for r in CITATION.findall(s)]  # a heading: its section
        for sentence in block:
            refs = CITATION.findall(sentence) or block_refs  # a citation at the end of the line covers it
            cited = [citations[r] for r in refs if citations[r].valid]
            plain = CITATION.sub(" ", sentence)
            for figure, written, position in _figure_matches(plain):
                if not refs:
                    problems.append(Problem("uncited_figure", f"'{written}' has no citation in its sentence or line"))
                elif cited and not any(figure in index.values.get(c.ref, set()) for c in cited):
                    names = ", ".join(f"[[{c.ref}]]" for c in cited)
                    if any(figure in index.quoted.get(c.ref, set()) for c in cited):
                        if not framed_as_quote(plain, position):
                            problems.append(Problem("unsupported_figure", (
                                f"'{written}' appears only in document text of {names}; quote it explicitly "
                                "(\"the note says …\" or in quotation marks), never as a fact")))
                    else:
                        problems.append(Problem("unsupported_figure", f"'{written}' does not appear in {names}"))
            if not executed and CLAIM.search(plain):
                problems.append(Problem("claimed_execution",
                                        f"'{sentence[:80]}' claims an action happened, but no tool result says executed"))
    return CheckResult(tuple(citations.values()), tuple(problems))
