from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_root_level_test_modules_except_conftest() -> None:
    root_test_files = sorted(path.name for path in (ROOT / "tests").glob("test_*.py"))
    assert root_test_files == []


def test_required_test_directories_exist() -> None:
    expected = {
        "contracts",
        "docs",
        "fixtures",
        "integration",
        "policy",
        "regression",
        "scripts",
        "skills",
        "strategies",
    }
    actual = {path.name for path in (ROOT / "tests").iterdir() if path.is_dir()}
    assert expected.issubset(actual)


def test_source_package_tests_have_matching_directories() -> None:
    expected = [
        "tests/skills/analyze",
        "tests/skills/compute",
        "tests/skills/construct",
        "tests/skills/ingest",
        "tests/skills/model",
        "tests/skills/report",
        "tests/skills/research",
        "tests/skills/store",
        "tests/strategies/cross_sectional",
        "tests/strategies/time_series",
    ]
    for relative in expected:
        assert (ROOT / relative).is_dir(), relative
