"""Helpers for the opt-in smoke tests: a throwaway data root and the installed ``qs`` script."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# Eight ETFs with daily bars across the whole local history, plus one index for benchmarks.
SYMBOLS = (
    "SHSE.510300",
    "SHSE.510170",
    "SHSE.513030",
    "SHSE.513100",
    "SHSE.513500",
    "SHSE.518880",
    "SZSE.159915",
    "SZSE.159920",
)
INDEX_SYMBOL = "SHSE.000300"
ADJUSTED_SYMBOLS = ("SHSE.510300", "SZSE.159915")
# Recent rows copied per symbol; keeps every command fast while leaving real history.
KEEP_ROWS = 600

# (market frequency directory, symbols) the smoke tests need in the local data root.
REQUIRED = (("1d", (*SYMBOLS, INDEX_SYMBOL)), ("1d_adj", ADJUSTED_SYMBOLS))


@dataclass(frozen=True)
class Work:
    """Scratch directory, throwaway data root and environment shared by every qs call."""

    dir: Path
    data_root: Path
    reports_root: Path
    env: dict


def required_files(root: Path) -> list[Path]:
    return [
        root / "market" / frequency / f"{symbol}.parquet"
        for frequency, symbols in REQUIRED
        for symbol in symbols
    ]


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """(size, mtime_ns) of every file under ``root``, keyed by relative path."""
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def copy_trimmed(source_root: Path, target_root: Path) -> None:
    """Copy the required parquet files, trimmed to their most recent rows."""
    import pandas as pd

    for path in required_files(source_root):
        target = target_root / path.relative_to(source_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        pd.read_parquet(path).tail(KEEP_ROWS).to_parquet(target)


def make_work(base: Path, data_root: Path) -> Work:
    directory, reports = base / "work", base / "reports"
    directory.mkdir()
    env = {
        **os.environ,
        "QUANTSPACE_DATA_ROOT": str(data_root),
        "QUANTSPACE_REPORTS_ROOT": str(reports),
        "MPLBACKEND": "Agg",
    }
    return Work(directory, data_root, reports, env)


def qs(work: Work, *args: str, expect: int = 0) -> dict:
    """Run the installed ``qs`` script in the scratch directory and return its envelope.

    The script writes exactly one JSON line to stdout; the exit code must equal ``expect``
    (0 by default, in which case ``ok`` must be true).
    """
    script = Path(sys.executable).with_name("qs")
    if not script.exists():
        pytest.skip("qs console script is not installed in this environment")
    completed = subprocess.run(
        [str(script), *args],
        cwd=work.dir,
        env=work.env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    label = " ".join(args[:3])
    assert completed.stdout.count("\n") == 1, (label, completed.stdout[:2000])
    envelope = json.loads(completed.stdout)
    assert completed.returncode == expect, (label, envelope, completed.stderr[-2000:])
    if expect == 0:
        assert envelope["ok"], (label, envelope)
    return envelope


def artifact_paths(envelope: dict) -> dict[str, Path]:
    return {item["name"]: Path(item["path"]) for item in envelope["artifacts"]}
