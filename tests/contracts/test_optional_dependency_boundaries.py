from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_strategy_package_import_does_not_touch_optional_heavy_dependencies() -> None:
    code = """
import builtins

blocked = {"jinja2", "matplotlib", "pycaret", "sklearn", "streamlit", "xgboost"}
real_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name.split(".", 1)[0] in blocked:
        raise AssertionError(f"optional dependency imported: {name}")
    return real_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import skills.strategy
import strategies.cross_sectional
import strategies.time_series
"""
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
