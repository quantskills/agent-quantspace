from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_public_skill_directories_are_exact() -> None:
    expected = {
        "analyze",
        "compute",
        "construct",
        "ingest",
        "model",
        "report",
        "research",
        "store",
    }
    actual = {
        path.name
        for path in (ROOT / "skills").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    assert actual == expected


def test_public_strategy_directories_are_exact() -> None:
    expected = {"cross_sectional", "time_series"}
    actual = {
        path.name
        for path in (ROOT / "strategies").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    assert actual == expected


def test_excluded_paths_are_absent() -> None:
    excluded = [
        "skills/" + "g" + "m",
        "strategies/" + "ganfeng" + "_T",
        "strategies/" + "andy" + "_gaoren",
        "skills/ingest/" + "g" + "m" + "_remote.py",
        "skills/ingest/fmp.py",
        "skills/store/" + "g" + "m" + "_cache_reader.py",
        "skills/store/" + "g" + "m" + "_trade_constraints.py",
        "skills/" + "signal",
        "skills/" + "tracker",
        "skills/compute/custom" + "_bar.py",
        "docs/strategy_ideas",
    ]
    for relative in excluded:
        assert not (ROOT / relative).exists(), relative
