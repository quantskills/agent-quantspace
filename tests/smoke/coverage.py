"""Which catalog commands the smoke tests drive, derived from the smoke sources themselves."""

from __future__ import annotations

import ast
from pathlib import Path

HERE = Path(__file__).parent

# Root commands handled by the runner rather than a Skill adapter.
ROOT_COMMANDS = frozenset({"catalog", "schema", "docs.render", "version"})

# Non-network commands with no suitable real local input; never fed synthetic data.
SKIPPED = {
    "compute.adjust": "needs adj_factor events; the local data root has no data/adj_factor",
    "compute.resample": (
        "needs A-share one-minute bars; the local 1m directory holds only futures symbols"
    ),
}

# Commands that have a smoke step but need an optional dependency: the step skips with the
# stated reason where the module cannot be imported. command -> (module, reason).
OPTIONAL_DEPENDENCY = {
    "store.query": ("duckdb", "needs the optional duckdb dependency (uv sync --extra query)"),
}


# Course and research reproduction scripts run at their defaults on the full local history.
RESEARCH_SCRIPTS = {
    "lesson06_multifactor": "strategies.cross_sectional.workflows.run_lesson06_multifactor",
    "lesson07_pca_ml": "strategies.cross_sectional.workflows.run_lesson07_etf18_logdiff_pca_ml",
    "lesson07_horizon_sensitivity": (
        "strategies.cross_sectional.workflows.run_lesson07_horizon_sensitivity"
    ),
    "prompt_test_correlation": "strategies.cross_sectional.workflows.run_prompt_test_correlation",
    "ma_cross_report": "strategies.time_series.workflows.run_ma_cross_report",
    "mine_etf18_factors": "scripts.mine_etf18_factors",
    "mine_etf18_factors_governed": "scripts.mine_etf18_factors_governed",
    "evaluate_mined_factors": "scripts.evaluate_mined_factors",
    "mined_factors_corr": "scripts.mined_factors_corr",
    "prompt_test_ic": "scripts.run_prompt_test_ic",
}


def invoked_commands(known: set[str]) -> set[str]:
    """Commands named by literal arguments of ``qs(work, ...)`` calls in the smoke sources."""
    found: set[str] = set()
    for path in sorted(HERE.glob("*.py")):
        if path.name in {"coverage.py", "runner.py", "test_smoke_coverage.py"}:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "qs"
            ):
                continue
            words: list[str] = []
            for argument in node.args[1:]:
                is_word = (
                    isinstance(argument, ast.Constant)
                    and isinstance(argument.value, str)
                    and not argument.value.startswith("-")
                )
                if not is_word:
                    break
                words.append(argument.value)
            for size in range(len(words), 0, -1):
                if ".".join(words[:size]) in known:
                    found.add(".".join(words[:size]))
                    break
    return found
