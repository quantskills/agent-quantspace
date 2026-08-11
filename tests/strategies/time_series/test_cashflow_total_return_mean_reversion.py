from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.time_series.cashflow_total_return_mean_reversion import (
    CashflowMeanReversionParams,
    cashflow_mean_reversion_signals,
    cashflow_mean_reversion_weights,
)
from strategies.time_series.workflows.run_cashflow_total_return_mean_reversion_is import (
    parameter_grid,
)


def _bars(prices: list[float]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(prices), name="eob")
    return pd.DataFrame({"close": prices}, index=index, dtype=float)


def _short_params(**overrides) -> CashflowMeanReversionParams:
    values = {
        "rsi_lookback": 2,
        "mean_exit_ma": 2,
        "trend_ma": 3,
        "trend_slope_lookback": 2,
        "overbought_lookback": 3,
        "overbought_distance": 0.90,
        "oversold_max_hold": 3,
        "overbought_max_hold": 2,
        **overrides,
    }
    return CashflowMeanReversionParams(**values)


def test_overbought_window_reduces_then_restores_core() -> None:
    bars = _bars([10, 10, 10, 10, 10, 11.4, 11.3, 11.4])
    params = _short_params(overbought_distance=0.13)

    signals = cashflow_mean_reversion_signals(bars, params=params)

    assert signals["target_exposure"].iloc[5:7].eq(0.0).all()
    assert signals["event"].iloc[5] == "defensive_entry"
    assert signals["target_exposure"].iloc[7] == 1.0
    assert signals["event"].iloc[7] == "defensive_exit_time"


def test_oversold_satellite_requires_rising_long_trend_and_exits_at_mean() -> None:
    bars = _bars([10, 10.5, 11, 12, 14, 13.5, 13, 13.8])
    params = _short_params(oversold_rsi=35.0)

    signals = cashflow_mean_reversion_signals(bars, params=params)

    assert signals["event"].iloc[6] == "oversold_entry"
    assert signals["target_exposure"].iloc[6] == 1.5
    assert signals["event"].iloc[7] == "oversold_exit_mean"
    assert signals["target_exposure"].iloc[7] == 1.0


def test_rule_has_no_future_dependency() -> None:
    prefix = 100.0 + np.sin(np.arange(180) / 5.0) * 10.0 + np.arange(180) * 0.1
    params = CashflowMeanReversionParams()
    left = cashflow_mean_reversion_weights(
        _bars([*prefix, 110.0, 111.0]), params=params
    ).iloc[:180]
    right = cashflow_mean_reversion_weights(
        _bars([*prefix, 1000.0, 1.0]), params=params
    ).iloc[:180]

    pd.testing.assert_frame_equal(left, right)


def test_satellite_stop_keeps_core_and_reenters_after_recovery() -> None:
    bars = _bars([10, 10.5, 11, 12, 14, 13.5, 12.5, 11.8, 12.2])
    params = _short_params(
        trend_ma=5,
        oversold_stop=0.05,
        oversold_max_hold=5,
        recovery_cooldown=1,
        recovery_threshold=0.03,
    )

    signals = cashflow_mean_reversion_signals(bars, params=params)

    assert signals["event"].iloc[6] == "oversold_entry"
    assert signals["event"].iloc[7] == "oversold_exit_stop"
    assert signals["target_exposure"].iloc[7] == 1.0
    assert signals["event"].iloc[8] == "oversold_reentry_recovery"
    assert signals["target_exposure"].iloc[8] == 1.5


def test_parameter_grid_is_bounded_and_contains_recommended_center() -> None:
    configs = parameter_grid()
    params = [value for _, value in configs]

    assert len(configs) == 1944
    assert max(value.oversold_exposure for value in params) == 1.5
    assert {value.overbought_distance for value in params} == {0.12, 0.13, 0.14}
    assert {value.oversold_stop for value in params} == {0.05, 0.07, 0.10}
    assert CashflowMeanReversionParams() in params


def test_parameters_reject_unbounded_leverage() -> None:
    with pytest.raises(ValueError, match="oversold_exposure"):
        CashflowMeanReversionParams(oversold_exposure=2.0)
