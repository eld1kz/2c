"""CLAUDE.md rule 2: only ActionService (via app/sandbox/*) may touch Sandbox* tables or executors."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
SANDBOX_MODELS = {"SandboxPayment", "SandboxEmail", "SandboxLoanApplication"}
EXECUTORS = {"app.sandbox.bank", "app.sandbox.outbox", "app.sandbox.loans"}
# Reading sandbox rows for limits/cooldowns is allowed; constructing/writing them is not.
READERS = {"app/policy/limits.py", "app/policy/gate.py"}
OWNERS = {"app/services/action_service.py", "app/db/models.py"}


def _modules() -> dict[str, ast.Module]:
    return {p.relative_to(APP.parent).as_posix(): ast.parse(p.read_text(encoding="utf-8")) for p in APP.rglob("*.py")}


def test_sandbox_executors_imported_only_by_action_service() -> None:
    offenders = []
    for path, tree in _modules().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = {f"{node.module}.{a.name}" for a in node.names} | {node.module}
                if names & EXECUTORS and path != "app/services/action_service.py":
                    offenders.append(path)
            elif isinstance(node, ast.Import) and {a.name for a in node.names} & EXECUTORS:
                offenders.append(path)
    assert offenders == []


def test_sandbox_models_only_written_in_sandbox_package() -> None:
    offenders = []
    for path, tree in _modules().items():
        if path.startswith("app/sandbox/") or path in OWNERS:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in SANDBOX_MODELS:
                offenders.append(f"{path}: constructs {node.func.id}")
            if isinstance(node, ast.ImportFrom) and {a.name for a in node.names} & SANDBOX_MODELS and path not in READERS:
                offenders.append(f"{path}: imports sandbox model")
    assert offenders == []
