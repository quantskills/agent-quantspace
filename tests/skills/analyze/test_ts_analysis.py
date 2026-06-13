from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from skills.analyze.ts_analysis import (
    TimeSeriesAnalyzer,
    analysis_results_to_df,
    ensure_dir_and_get_path,
    half_life_of_mean_reversion,
)


def test_analysis_results_to_df_flattens_kde_metrics() -> None:
    frame = analysis_results_to_df(
        {
            "price_length": 100,
            "kde": {
                1: {"peak_height": 0.4, "skew_feature": "symmetric"},
                2: {"peak_height": 0.5, "skew_feature": "right_skew"},
            },
        }
    )

    assert list(frame.index) == [1, 2]
    assert frame.loc[2, "kde_skew_feature"] == "right_skew"
    assert frame["price_length"].eq(100).all()


def test_time_series_analyzer_result_dataframe_classifies_cached_results() -> None:
    analyzer = TimeSeriesAnalyzer(pd.Series(np.linspace(100.0, 120.0, 80)))
    analyzer.results[40] = {
        "hurst": 0.62,
        "adf": {"pvalue": 0.2},
        "kpss": {"pvalue": 0.01, "warning": None},
        "min_lag": 5,
        "window_max_lag": 12,
    }

    result = analyzer.get_results_dataframe()

    assert result.loc[0, "trend_score"] == 5
    assert "strong trend" in result.loc[0, "trend_type"]


def test_half_life_identifies_mean_reverting_spread() -> None:
    index = pd.date_range("2024-01-01", periods=80)
    spread = pd.Series([(-0.8) ** i for i in range(80)], index=index)

    result = half_life_of_mean_reversion(spread)

    assert result["is_mean_reverting"] is True
    assert result["half_life_bars"] > 0


def test_ensure_dir_and_get_path_adds_suffix(tmp_path) -> None:
    path = ensure_dir_and_get_path(tmp_path / "nested" / "chart.png", "_kde.csv")

    assert path.endswith("chart_kde.csv")
    assert (tmp_path / "nested").is_dir()


def test_half_life_requires_enough_observations() -> None:
    with pytest.raises(ValueError, match="at least 10"):
        half_life_of_mean_reversion(pd.Series([1.0, 0.5, 0.25]))
