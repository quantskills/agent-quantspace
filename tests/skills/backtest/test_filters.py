from __future__ import annotations

import pandas as pd

from skills.backtest.filters import (
    apply_index_trend_scale,
    apply_market_breadth_scale,
    calculate_index_trend,
    calculate_market_breadth,
)


def test_market_breadth_scale_reduces_exposure_below_threshold() -> None:
    idx = pd.date_range("2024-01-01", periods=4)
    weights = pd.DataFrame({"A": 0.5, "B": 0.5}, index=idx)
    close = pd.DataFrame({"A": [10, 9, 8, 7], "B": [10, 9, 8, 7]}, index=idx)

    scaled = apply_market_breadth_scale(weights, close, breadth_threshold=0.8, scale_below=0.25, ma_period=2)

    assert calculate_market_breadth(close, ma_period=2).iloc[-1] < 0.8
    assert scaled.iloc[-1].sum() == 0.25


def test_index_trend_scale_applies_downtrend_scale() -> None:
    idx = pd.date_range("2024-01-01", periods=4)
    weights = pd.DataFrame({"A": 1.0}, index=idx)
    index_close = pd.Series([10, 9, 8, 7], index=idx)

    scaled = apply_index_trend_scale(weights, index_close, scale_downtrend=0.4, ma_period=2)

    assert calculate_index_trend(index_close, ma_period=2).iloc[-1] == 0.0
    assert scaled.iloc[-1, 0] == 0.4
