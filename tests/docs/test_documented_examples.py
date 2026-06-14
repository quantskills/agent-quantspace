from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_documentation_mentions_current_backtest_api() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "README.md",
            ROOT / "README-zh.md",
            ROOT / "strategies/README.md",
            ROOT / "scripts/README.md",
        ]
    )

    assert "VectorBacktester" in docs
    assert "TimeSeriesBacktester" not in docs
    assert "SignalBacktestExecutor" not in docs
    assert "strategy_examples" in docs


def test_agents_document_enforces_reuse_and_test_layout() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "reuse existing `skills/` and `strategies/`" in text
    assert "Do not add root-level `tests/test_*.py`" in text
    assert "`scripts/` as thin orchestration" in text
