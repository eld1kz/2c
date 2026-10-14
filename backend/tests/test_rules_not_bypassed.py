"""Guards that fail if categorization rules or CLAUDE.md hard rules are bypassed."""

import ast
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, CategorySource, Transaction
from seed.load import load
from tests.fakes import FakeClassifier

APP = Path(__file__).resolve().parents[1] / "app"
RULE_COVERED = {
    "PAYSTREAM PAYROLL%": "payroll",
    "%MAPLEWOOD PROPERTY GRP RENT": "rent",
    "%DESIGNLY PRO%": "software",
    "%DESIGNLY*TEAM%": "software",
    "%CRESTLINE%": "equipment",
    "POS SETTLEMENT%": "revenue_retail",
}


def test_llm_cannot_override_rules() -> None:
    """A lying classifier answers `marketing` @ 0.99 for everything: rules must still decide."""
    liar = FakeClassifier(category="marketing", confidence=0.99)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        load(s, classifier=liar)
        for pattern, category in RULE_COVERED.items():
            txs = list(s.scalars(select(Transaction).where(Transaction.raw_description.like(pattern))))
            assert txs, pattern
            assert {(t.category, t.category_source) for t in txs} == {(category, CategorySource.rule)}, pattern
        # Only rows no rule covers ever reach the LLM.
        assert liar.descriptions == ["QUILLBOOK ACCOUNTING"] * 6
        assert {t.category for t in s.scalars(select(Transaction)) if t.category_source == CategorySource.llm} \
            == {"marketing"}


def _trees(*parts: str) -> dict[str, ast.AST]:
    files = [f for p in parts for f in sorted((APP / p).rglob("*.py"))]
    return {str(f.relative_to(APP)): ast.parse(f.read_text()) for f in files}


def test_no_float_in_money_paths() -> None:
    for name in ("ingestion/csv_parser.py", "ingestion/pipeline.py", "engine/recurring.py"):
        tree = ast.parse((APP / name).read_text())
        for node in ast.walk(tree):
            assert not (isinstance(node, ast.Name) and node.id in {"float", "Decimal"}), name
            assert not (isinstance(node, ast.Constant) and isinstance(node.value, float)), name


def test_no_wall_clock_in_engine_or_ingestion() -> None:
    for name, tree in _trees("engine", "ingestion").items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                assert (node.value.id, node.attr) not in {
                    ("datetime", "now"), ("datetime", "utcnow"), ("date", "today"), ("time", "time"),
                }, name


def test_engine_and_ingestion_never_touch_sandbox_tables() -> None:
    for name, tree in _trees("engine", "ingestion").items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not any(a.name.startswith("Sandbox") for a in node.names), name


def test_only_the_llm_modules_import_anthropic() -> None:
    importers = {
        name
        for name, tree in _trees(".").items()
        for node in ast.walk(tree)
        if (isinstance(node, ast.Import) and any(a.name == "anthropic" for a in node.names))
        or (isinstance(node, ast.ImportFrom) and node.module == "anthropic")
    }
    assert importers == {"engine/llm_classifier.py", "agent/runner.py"}
