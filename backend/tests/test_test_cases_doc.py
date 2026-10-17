"""docs/test-cases.md names real tests: every `path::name` (pytest) or `path::"title"` (Playwright) exists."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "test-cases.md"
REF = re.compile(r'`((?:backend|frontend)/[\w./-]+)::("[^"]+"|\w+)`')


def test_every_referenced_test_exists() -> None:
    refs = REF.findall(DOC.read_text(encoding="utf-8"))
    assert len(refs) > 40
    missing = []
    for path, name in refs:
        source = (ROOT / path).read_text(encoding="utf-8") if (ROOT / path).is_file() else ""
        wanted = f"test({name}," if name.startswith('"') else f"def {name}("
        if wanted not in source:
            missing.append(f"{path}::{name}")
    assert missing == []


def test_every_case_is_covered() -> None:
    text = DOC.read_text(encoding="utf-8")
    for case in ("P1", "P2", "P3", "P4", "A1", "A2", "A3", "A4", "A5"):
        assert re.search(rf"^\| {case} \|", text, re.MULTILINE), case
