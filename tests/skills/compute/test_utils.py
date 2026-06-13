from __future__ import annotations

import pandas as pd
import pytest

from skills.compute.utils import calculate_atr, rolling_zscore, round_away_from_zero, safe_divide


def test_safe_divide_replaces_zero_denominator_with_fill_value() -> None:
    result = safe_divide(pd.Series([1.0, 2.0]), pd.Series([1.0, 0.0]), fill_value=-1.0)

    assert result.tolist() == [1.0, -1.0]


def test_rolling_zscore_centers_recent_window() -> None:
    series = pd.Series([1.0, 2.0, 3.0])

    result = rolling_zscore(series, window=3, min_periods=3)

    assert result.iloc[-1] == pytest.approx(1.0)


def test_calculate_atr_uses_true_range() -> None:
    high = pd.Series([11.0, 12.0, 13.0])
    low = pd.Series([9.0, 10.0, 11.0])
    close = pd.Series([10.0, 11.0, 12.0])

    atr = calculate_atr(high, low, close, period=2)

    assert atr.iloc[0] == 2.0
    assert atr.iloc[-1] == pytest.approx(2.0)


def test_round_away_from_zero_handles_series_and_scalars() -> None:
    assert round_away_from_zero(1.2341, decimals=3) == 1.235
    assert round_away_from_zero(-1.2341, decimals=3) == -1.235
