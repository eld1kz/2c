"""Transaction categorization (SPEC §6.2): rules first, LLM fallback, low confidence → review.

Rules always win; only rows no rule covers are ever shown to the classifier.
"""

from dataclasses import dataclass
from typing import Protocol, Sequence

from app.db.models import Category, CategoryRule, CategorySource, RuleDirection, RuleKind

REVIEW_THRESHOLD = 0.7
RULE_CONFIDENCE = 1.0

# Generic keyword rules every business gets (seeded into category_rules), matched as whole
# tokens of the normalized description.
DEFAULT_KEYWORD_RULES: list[tuple[str, RuleDirection, Category]] = [
    ("SETTLEMENT", RuleDirection.inflow, Category.revenue_retail),
    ("FEE", RuleDirection.outflow, Category.fees),
    ("FEES", RuleDirection.outflow, Category.fees),
    ("PAYROLL", RuleDirection.outflow, Category.payroll),
    ("RENT", RuleDirection.outflow, Category.rent),
    ("UTILITIES", RuleDirection.outflow, Category.utilities),
    ("LEASE", RuleDirection.outflow, Category.equipment),
    ("PACKAGING", RuleDirection.outflow, Category.cogs_packaging),
    ("GREEN COFFEE", RuleDirection.outflow, Category.cogs_beans),
    ("LOGISTICS", RuleDirection.outflow, Category.logistics),
    ("SUBSCRIPTION", RuleDirection.outflow, Category.software),
]


def direction_of(amount: int) -> RuleDirection:
    return RuleDirection.inflow if amount > 0 else RuleDirection.outflow


@dataclass(frozen=True)
class RowFacts:
    normalized: str
    amount: int
    counterparty_name: str | None  # matched counterparty's normalized_name
    linked_receivable: bool


@dataclass(frozen=True)
class Categorization:
    category: Category | None
    source: CategorySource | None
    confidence: float | None
    needs_review: bool


@dataclass(frozen=True)
class ClassifyItem:
    index: int  # batch-local, never a DB id
    description: str  # normalized text only
    direction: str  # "in" | "out"


@dataclass(frozen=True)
class ClassifyResult:
    index: int
    category: str
    confidence: float


class Classifier(Protocol):
    def classify(self, items: list[ClassifyItem]) -> list[ClassifyResult]: ...


class NullClassifier:
    """No LLM configured: every uncovered row goes to the review queue."""

    def classify(self, items: list[ClassifyItem]) -> list[ClassifyResult]:
        return []


UNCATEGORIZED = Categorization(category=None, source=None, confidence=None, needs_review=True)


def match_rule(rules: Sequence[CategoryRule], row: RowFacts) -> Category | None:
    direction = direction_of(row.amount)
    if row.linked_receivable and direction is RuleDirection.inflow:
        return Category.revenue_wholesale
    padded = f" {row.normalized} "
    for rule in sorted(rules, key=lambda r: (r.priority, r.id or 0)):
        if rule.direction not in (RuleDirection.any, direction):
            continue
        if rule.kind == RuleKind.keyword and f" {rule.pattern} " in padded:
            return rule.category
        if rule.kind == RuleKind.name and rule.pattern == row.counterparty_name:
            return rule.category
    return None


def _from_llm(result: ClassifyResult | None) -> Categorization:
    if result is None or result.category not in Category.__members__:
        return UNCATEGORIZED
    if not 0.0 <= result.confidence <= 1.0:
        return UNCATEGORIZED
    return Categorization(
        category=Category(result.category),
        source=CategorySource.llm,
        confidence=result.confidence,
        needs_review=result.confidence < REVIEW_THRESHOLD,
    )


def categorize(rows: Sequence[RowFacts], rules: Sequence[CategoryRule], classifier: Classifier) -> list[Categorization]:
    out: list[Categorization | None] = []
    pending: list[ClassifyItem] = []
    for i, row in enumerate(rows):
        category = match_rule(rules, row)
        if category is None:
            out.append(None)
            pending.append(ClassifyItem(index=i, description=row.normalized, direction=direction_of(row.amount).value))
        else:
            out.append(Categorization(category, CategorySource.rule, RULE_CONFIDENCE, needs_review=False))

    if pending:
        try:
            results = classifier.classify(pending)
        except Exception:  # an LLM failure never fails an import; rows go to review
            results = []
        wanted = {item.index for item in pending}
        by_index: dict[int, ClassifyResult] = {}
        for r in results:
            if r.index in wanted and r.index not in by_index:
                by_index[r.index] = r
        for item in pending:
            out[item.index] = _from_llm(by_index.get(item.index))
    return [c if c is not None else UNCATEGORIZED for c in out]
