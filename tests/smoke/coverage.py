"""Which catalog commands the smoke tests drive, derived from the smoke sources themselves."""

from __future__ import annotations

import ast
from pathlib import Path

HERE = Path(__file__).parent

# Root commands handled by the runner rather than a Skill adapter.
ROOT_COMMANDS = frozenset({"catalog", "schema", "docs.render", "version"})

# Non-network commands with no suitable real local input; never fed synthetic data.
SKIPPED = {
    "store.query": "needs the optional duckdb dependency, which is not installed locally",
    "compute.adjust": "needs adj_factor events; the local data root has no data/adj_factor",
    "compute.resample": (
        "needs A-share one-minute bars; the local 1m directory holds only futures symbols"
    ),
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
