from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _imported_modules(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append((node.lineno, node.module))
    return modules


def test_skills_do_not_import_strategy_workspaces() -> None:
    violations: list[str] = []
    for path in sorted((ROOT / "skills").rglob("*.py")):
        for line, module in _imported_modules(path):
            if module == "strategies" or module.startswith("strategies."):
                violations.append(f"{path.relative_to(ROOT)}:{line}: {module}")
    assert violations == []


def test_tracking_scope_is_not_present() -> None:
    assert not (ROOT / "skills/tracking").exists()
    assert not (ROOT / "var/qs_tracking").exists()


def test_research_storage_boundaries_do_not_reintroduce_legacy_universe_registry_terms() -> None:
    paths = [
        ROOT / "skills/store/data_manager.py",
        ROOT / "skills/research/factor_screening.py",
        ROOT / "skills/research/param_sensitivity.py",
        ROOT / "skills/analyze/tearsheet.py",
        ROOT / "skills/ml/ml_engine.py",
        ROOT / "skills/report/templates/factor_report.html",
        ROOT / "skills/strategy/cross_sectional/risk_controls.py",
    ]
    forbidden = "p" + "ool"
    violations = [
        str(path.relative_to(ROOT))
        for path in paths
        if forbidden in path.read_text(encoding="utf-8").lower()
    ]

    assert violations == []


def test_runtime_entrypoints_do_not_inject_sys_path() -> None:
    entrypoints = [
        *sorted((ROOT / "scripts").glob("*.py")),
        *sorted((ROOT / "strategies").glob("*/workflows/*.py")),
    ]
    violations = [
        str(path.relative_to(ROOT))
        for path in entrypoints
        if "sys.path" in path.read_text(encoding="utf-8")
    ]
    assert violations == []


def test_release_tree_excludes_private_runtime_state() -> None:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    forbidden_suffixes = (".db", ".sqlite", ".sqlite3", "-wal", "-shm")
    binary_suffixes = {".gif", ".jpeg", ".jpg", ".parquet", ".png", ".pyc"}
    violations: list[str] = []

    for relative in listed:
        path = ROOT / relative
        if not path.is_file():
            continue
        if path.name.lower().endswith(forbidden_suffixes):
            violations.append(f"runtime database: {relative}")
            continue
        if path.suffix.lower() in binary_suffixes:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "/" + "Users/" in text:
            violations.append(f"absolute user path: {relative}")
        if "strategies/" + "etf_cs" in text:
            violations.append(f"private reference strategy: {relative}")

    assert violations == []
