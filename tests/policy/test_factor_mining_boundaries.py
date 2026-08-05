"""Phase 02/03 boundary policy for factor_mining adapters."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FM_ROOT = ROOT / "skills/factor_mining"
ADAPTERS_ROOT = FM_ROOT / "adapters"
ANALYZE_ADAPTER = ADAPTERS_ROOT / "analyze.py"

FORBIDDEN_ROLE_ENUM_NAMES = {
    "RoleId",
    "AgentRole",
    "FactorMiningRole",
    "LogicalRole",
}

# Always forbidden inside factor_mining (including adapters), except the
# analyze mapping adapter which may import skills.analyze.
CORE_FORBIDDEN_IMPORT_PREFIXES = (
    "strategies",
    "openai",
    "anthropic",
    "google.adk",
    "cursor",
    "skills.backtest",
    "skills.ml",
    "skills.research",
)

ADAPTER_FORBIDDEN_IMPORT_PREFIXES = CORE_FORBIDDEN_IMPORT_PREFIXES + (
    "skills.analyze",
)

# Additional bans for contract/port modules (no compute runtime here).
CONTRACT_FORBIDDEN_IMPORT_PREFIXES = CORE_FORBIDDEN_IMPORT_PREFIXES + (
    "skills.analyze",
    "numpy",
    "pandas",
    "skills.compute",
    "skills.store",
)

FORBIDDEN_CALL_NAMES = {
    "pearsonr",
    "corrcoef",
    "IC_stat",
    "group_stat",
    "VectorBacktester",
}

FORBIDDEN_AGENT_RUNTIME_CALL_NAMES = {
    "spawn_agent",
    "spawn_subagent",
    "create_thread",
    "fork_thread",
    "send_message_to_thread",
}


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _call_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _is_adapter(path: Path) -> bool:
    try:
        path.relative_to(ADAPTERS_ROOT)
        return True
    except ValueError:
        return False


def _is_analyze_adapter(path: Path) -> bool:
    return path.resolve() == ANALYZE_ADAPTER.resolve()


def test_factor_mining_python_has_no_role_enum_or_platform_sdk() -> None:
    py_files = sorted(FM_ROOT.rglob("*.py"))
    assert py_files
    for path in py_files:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in FORBIDDEN_ROLE_ENUM_NAMES:
                raise AssertionError(f"role enum copy found: {path.name}:{node.name}")
            if isinstance(node, ast.ClassDef) and node.name.endswith("Role"):
                bases = {
                    base.id
                    for base in node.bases
                    if isinstance(base, (ast.Name,))
                }
                if bases & {"Enum", "str"} and "role" in node.name.lower():
                    raise AssertionError(f"suspicious role enum: {path}:{node.name}")
        if _is_analyze_adapter(path):
            forbidden = CORE_FORBIDDEN_IMPORT_PREFIXES
        elif _is_adapter(path):
            forbidden = ADAPTER_FORBIDDEN_IMPORT_PREFIXES
        else:
            forbidden = CONTRACT_FORBIDDEN_IMPORT_PREFIXES
        for module in _imported_modules(path):
            assert not any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in forbidden
            ), f"{path}: forbidden import {module}"
        assert not re.search(r"\bif\s+platform\s*(==|in)\b", source)
        assert "product_whitelist" not in source
        assert "PLATFORM_WHITELIST" not in source


def test_factor_mining_python_has_no_agent_runtime_or_recursive_dispatch() -> None:
    """Phase 05 is a host protocol, never an in-skill platform dispatcher."""
    for path in sorted(FM_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            assert name not in FORBIDDEN_AGENT_RUNTIME_CALL_NAMES, (
                f"{path}: agent runtime call {name} is forbidden"
            )


def test_factor_mining_has_no_deterministic_research_algorithms() -> None:
    for path in sorted(FM_ROOT.rglob("*.py")):
        calls = _call_names(path)
        banned = calls & FORBIDDEN_CALL_NAMES
        assert not banned, f"{path} contains research algorithm calls: {sorted(banned)}"
        source = path.read_text(encoding="utf-8")
        assert "def ic_" not in source.lower()
        if not _is_analyze_adapter(path):
            assert "from skills.analyze" not in source
        assert "VectorBacktester" not in source
        assert "eval(" not in source
        assert "exec(" not in source
        if _is_adapter(path):
            assert "strategies" not in source or "must not point into strategies" in source


def test_factor_mining_skill_is_role_authority_not_python() -> None:
    skill = (FM_ROOT / "SKILL.md").read_text(encoding="utf-8")
    role_ids = re.findall(r"^role_id:\s*([^\s]+)\s*$", skill, flags=re.MULTILINE)
    assert len(role_ids) == 8
    assert len(set(role_ids)) == 8
    py_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(FM_ROOT.rglob("*.py"))
    )
    for role_id in role_ids:
        assert role_id not in py_text


def test_factor_mining_adapters_import_boundaries() -> None:
    assert ADAPTERS_ROOT.is_dir()
    for path in sorted(ADAPTERS_ROOT.rglob("*.py")):
        for module in _imported_modules(path):
            assert not module.startswith("skills.backtest")
            assert not module.startswith("strategies")
            if _is_analyze_adapter(path):
                continue
            assert not module.startswith("skills.analyze")


def test_analyze_must_not_import_factor_mining_or_strategies() -> None:
    analyze_root = ROOT / "skills/analyze"
    phase03 = {
        "contracts.py",
        "facade.py",
        "validation.py",
        "spec_checks.py",
        "causality.py",
        "factor_evaluation.py",
        "factor_robustness.py",
        "factor_incremental.py",
    }
    for path in sorted(analyze_root.rglob("*.py")):
        for module in _imported_modules(path):
            assert not module.startswith("skills.factor_mining"), path
            assert not module.startswith("strategies"), path
            assert not module.startswith("skills.report"), path
            if path.name in phase03:
                assert not module.startswith("skills.store"), path
