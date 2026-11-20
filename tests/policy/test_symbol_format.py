"""Stores and code use PandaData codes; only the migration module knows the legacy format."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY = re.compile(r"\b(?:SHSE|SZSE|SHFE|DCE|CZCE|CFFEX|INE|GFEX|HKEX|NASDAQ)\.[A-Za-z0-9_]+\b")
# The migration command and its tests must name legacy symbols to rename them.
ALLOWED = {
    "skills/store/legacy_symbols.py",
    "skills/store/SKILL.md",
    "skills/store/references/python-api.md",
    "skills/store/cli.py",
    "tests/skills/store/test_legacy_symbols.py",
    "tests/smoke/test_qs_smoke.py",
    "tests/policy/test_symbol_format.py",
    "README.md",
    "README.en.md",
    "AGENTS.md",
}
SUFFIXES = (".py", ".md", ".toml", ".json", ".yaml", ".yml", ".txt", ".html")


def test_legacy_symbols_appear_only_in_the_migration_path() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    violations = []
    for name in tracked:
        if name in ALLOWED or not name.endswith(SUFFIXES):
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if LEGACY.search(line):
                violations.append(f"{name}:{number}: {line.strip()[:100]}")
    assert violations == []
