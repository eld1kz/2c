"""Categorizer: rules first, classifier fallback, confidence < 0.7 → review, failures → review."""

import pytest

from app.db.models import Category, CategoryRule, CategorySource, RuleDirection, RuleKind
from app.engine.categorize import (
    DEFAULT_KEYWORD_RULES,
    ClassifyItem,
    ClassifyResult,
    RowFacts,
    categorize,
)
from tests.fakes import FakeClassifier

RULES = [
    CategoryRule(kind=RuleKind.keyword, pattern=p, direction=d, category=c, priority=i)
    for i, (p, d, c) in enumerate(DEFAULT_KEYWORD_RULES)
] + [CategoryRule(kind=RuleKind.name, pattern="DESIGNLY PRO", direction=RuleDirection.outflow,
                  category=Category.software, priority=200)]


def _row(normalized: str, amount: int = -100, cp: str | None = None, receivable: bool = False) -> RowFacts:
    return RowFacts(normalized=normalized, amount=amount, counterparty_name=cp, linked_receivable=receivable)


@pytest.mark.parametrize("row, category", [
    (_row("PAYSTREAM PAYROLL NET PAY"), Category.payroll),
    (_row("POS SETTLEMENT CLOUDPOS", amount=500), Category.revenue_retail),
    (_row("MONTHLY SERVICE FEE"), Category.fees),
    (_row("DESIGNLY PRO", cp="DESIGNLY PRO"), Category.software),
    (_row("COPPERLEAF BAKERY REF", amount=500, receivable=True), Category.revenue_wholesale),
])
def test_rule_hits(row: RowFacts, category: Category) -> None:
    (c,) = categorize([row], RULES, FakeClassifier(category="marketing"))
    assert (c.category, c.source, c.confidence, c.needs_review) == (category, CategorySource.rule, 1.0, False)


def test_keyword_needs_whole_token_and_direction() -> None:
    fake = FakeClassifier(category="other", confidence=0.95)
    rows = [_row("RENTAL CAR"), _row("PAYROLL REFUND", amount=100)]
    assert [c.source for c in categorize(rows, RULES, fake)] == [CategorySource.llm, CategorySource.llm]


@pytest.mark.parametrize("confidence, review", [(0.69, True), (0.7, False), (0.95, False)])
def test_review_threshold(confidence: float, review: bool) -> None:
    (c,) = categorize([_row("QUILLBOOK ACCOUNTING")], RULES, FakeClassifier(confidence=confidence))
    assert (c.category, c.source, c.needs_review) == (Category.software, CategorySource.llm, review)


class _Scripted:
    def __init__(self, results: list[ClassifyResult]) -> None:
        self.results = results

    def classify(self, items: list[ClassifyItem]) -> list[ClassifyResult]:
        return self.results


class _Broken:
    def classify(self, items: list[ClassifyItem]) -> list[ClassifyResult]:
        raise TimeoutError("LLM down")


@pytest.mark.parametrize("classifier", [
    _Scripted([ClassifyResult(0, "crypto", 0.99)]),  # not in the fixed list
    _Scripted([ClassifyResult(0, "software", 1.5)]),  # confidence out of range
    _Scripted([ClassifyResult(7, "software", 0.99)]),  # index not in the batch
    _Scripted([]),  # missing
    _Broken(),
], ids=["bad-category", "bad-confidence", "foreign-index", "missing", "exception"])
def test_bad_llm_output_goes_to_review(classifier: object) -> None:
    (c,) = categorize([_row("QUILLBOOK ACCOUNTING")], RULES, classifier)
    assert (c.category, c.source, c.confidence, c.needs_review) == (None, None, None, True)


def test_first_answer_per_index_wins() -> None:
    scripted = _Scripted([ClassifyResult(0, "software", 0.9), ClassifyResult(0, "marketing", 0.99)])
    (c,) = categorize([_row("QUILLBOOK ACCOUNTING")], RULES, scripted)
    assert c.category == Category.software


def test_classifier_sees_only_normalized_text_and_direction() -> None:
    fake = FakeClassifier()
    categorize([_row("PAYSTREAM PAYROLL NET PAY"), _row("QUILLBOOK ACCOUNTING")], RULES, fake)
    assert fake.calls == [[ClassifyItem(index=1, description="QUILLBOOK ACCOUNTING", direction="out")]]
