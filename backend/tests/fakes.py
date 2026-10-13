from app.engine.categorize import ClassifyItem, ClassifyResult


class FakeClassifier:
    """Stands in for the LLM: answers one category/confidence for every item and records calls."""

    def __init__(self, category: str = "software", confidence: float = 0.92) -> None:
        self.category = category
        self.confidence = confidence
        self.calls: list[list[ClassifyItem]] = []

    def classify(self, items: list[ClassifyItem]) -> list[ClassifyResult]:
        self.calls.append(items)
        return [ClassifyResult(i.index, self.category, self.confidence) for i in items]

    @property
    def descriptions(self) -> list[str]:
        return [i.description for call in self.calls for i in call]
