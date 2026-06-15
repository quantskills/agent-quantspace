from __future__ import annotations

import pandas as pd
import pytest

from skills.backtest.exit_analysis import (
    _compute_ab_comparison,
    _compute_forward_returns,
    _compute_trigger_mask,
    _compute_trigger_stats,
    summarize_exit_factors,
)


def test_exit_analysis_helpers_measure_filtered_positions() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    base = pd.DataFrame({"AAA": [1.0, 1.0, 0.0, 1.0], "BBB": [0.0, 0.0, 1.0, 0.0]}, index=index)
    variant = pd.DataFrame({"AAA": [1.0, 0.0, 0.0, 0.0], "BBB": [0.0, 0.0, 1.0, 0.0]}, index=index)

    trigger_mask = _compute_trigger_mask(base, variant)
    stats = _compute_trigger_stats(trigger_mask, base, variant)

    assert bool(trigger_mask.loc[index[1], "AAA"]) is True
    assert stats["hit_count"] == 2
    assert stats["hit_rate"] == pytest.approx(0.5)


def test_forward_returns_are_computed_at_trigger_points() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame({"AAA": [100.0, 102.0, 101.0, 105.0]}, index=index)
    trigger = pd.DataFrame({"AAA": [False, True, False, False]}, index=index)

    result = _compute_forward_returns(close, trigger, windows=[1, 2])

    assert result[1]["count"] == 1
    assert result[1]["mean"] == pytest.approx(101.0 / 102.0 - 1.0)
    assert result[2]["count"] == 1


def test_summarize_exit_factors_builds_metric_table() -> None:
    comparison = _compute_ab_comparison(
        {"ann_return": 0.1, "sharpe_ratio": 1.0},
        {"ann_return": 0.12, "sharpe_ratio": 1.3},
    )
    table = summarize_exit_factors(
        [
            {
                "name": "risk",
                "ab_comparison": comparison,
                "trigger_stats": {"hit_rate": 0.25, "exposure_mean": 0.8},
                "event_analysis": {1: {"mean": -0.01, "big_loss_prob_4pct": 0.0}},
            }
        ]
    )

    assert table.loc["risk", "dAnnReturn"] == pytest.approx(0.02)
    assert table.loc["risk", "hit_rate"] == pytest.approx(0.25)
