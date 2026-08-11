from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.time_series.cashflow_trend import (
    CashflowTrendParams,
    cashflow_trend_weights,
    close_atr_proxy,
)
from strategies.time_series.workflows.run_cashflow_trend_grid import sensitivity_configs


def _bars(close: list[float]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(close), name="eob")
    return pd.DataFrame({"close": close}, index=index, dtype=float)


def test_close_atr_proxy_is_close_only_and_wilder_smoothed() -> None:
    close = pd.Series([10.0, 11.0, 13.0, 12.0, 14.0])
    result = close_atr_proxy(close, lookback=2)

    assert result.iloc[:2].isna().all()
    assert result.iloc[-1] == pytest.approx(1.625)


def test_cashflow_trend_enters_breakout_and_exits_regime_loss() -> None:
    prices = [10, 10, 10, 10, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 12]
    params = CashflowTrendParams(
        trend_ma=4,
        breakout_lookback=3,
        fast_ma=2,
        slow_ma=3,
        atr_lookback=2,
        initial_stop_atr=3.0,
        trailing_stop_atr=3.0,
        exit_lookback=3,
        target_volatility=0.10,
        trend_slope_lookback=2,
        volatility_lookback=3,
    )

    weights = cashflow_trend_weights(_bars(prices), params=params)

    assert weights.iloc[:5, 0].eq(0.0).all()
    assert weights.iloc[7:15, 0].gt(0.0).all()
    assert weights.iloc[-1, 0] == 0.0
    assert weights.iloc[:, 0].between(0.0, 1.0).all()


def test_cashflow_trend_has_no_future_data_dependency() -> None:
    prefix = np.linspace(10.0, 30.0, 80)
    first = _bars([*prefix, 31.0, 32.0])
    second = _bars([*prefix, 1000.0, 1.0])
    params = CashflowTrendParams(
        trend_ma=20,
        breakout_lookback=10,
        fast_ma=5,
        slow_ma=10,
        atr_lookback=5,
        exit_lookback=10,
        trend_slope_lookback=5,
        volatility_lookback=10,
    )

    left = cashflow_trend_weights(first, params=params).iloc[:80]
    right = cashflow_trend_weights(second, params=params).iloc[:80]

    pd.testing.assert_frame_equal(left, right)


def test_sensitivity_grid_covers_recommended_values_without_cartesian_search() -> None:
    cases = sensitivity_configs()
    params = [item for _, item in cases]

    assert len(cases) == 13
    assert {item.trend_ma for item in params} == {100, 120, 160}
    assert {item.breakout_lookback for item in params} == {20, 40, 55}
    assert {item.trailing_stop_atr for item in params} == {2.5, 3.0, 3.5}
    assert {item.exit_lookback for item in params} == {10, 20, 30}
    assert {item.target_volatility for item in params} == {0.10, 0.12}
