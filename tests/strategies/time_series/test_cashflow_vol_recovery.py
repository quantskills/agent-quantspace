from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.time_series.cashflow_vol_recovery import (
    VolRecoveryParams,
    cashflow_vol_recovery_weights,
    volatility_exposure,
)
from strategies.time_series.workflows.run_cashflow_vol_recovery_is import stage1_configs


def _bars(prices: list[float]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(prices), name="eob")
    return pd.DataFrame({"close": prices}, index=index, dtype=float)


def test_target_vol_exposure_reduces_when_realized_volatility_rises() -> None:
    calm = np.linspace(100.0, 110.0, 50)
    volatile = np.array([110.0, 120.0, 105.0, 125.0, 100.0, 130.0] * 5)
    close = pd.Series(np.concatenate([calm, volatile]))
    params = VolRecoveryParams(family="target_vol", volatility_lookback=10)

    exposure = volatility_exposure(close, params)

    assert exposure.iloc[30:45].mean() > exposure.iloc[-10:].mean()
    assert exposure.dropna().between(0.0, 1.0).all()


def test_loss_stop_waits_for_recovery_before_reentry() -> None:
    prices = [
        *np.linspace(10.0, 20.0, 30),
        21.0,
        22.0,
        20.0,
        19.5,
        19.8,
        20.1,
        20.6,
        21.0,
        21.5,
    ]
    params = VolRecoveryParams(
        family="target_vol",
        trend_ma=10,
        breakout_lookback=5,
        fast_ma=3,
        slow_ma=5,
        trend_slope_lookback=3,
        volatility_lookback=5,
        regime_lookback=10,
        loss_stop=0.08,
        recovery_threshold=0.04,
        cooldown_bars=3,
        reduce_trigger=0.03,
    )

    weights = cashflow_vol_recovery_weights(_bars(prices), params=params).iloc[:, 0]

    assert weights.iloc[30:32].gt(0.0).all()
    assert weights.iloc[33:37].eq(0.0).all()
    assert weights.iloc[-1] > 0.0


def test_vol_recovery_has_no_future_dependency() -> None:
    prefix = np.linspace(10.0, 30.0, 80)
    first = _bars([*prefix, 31.0, 32.0])
    second = _bars([*prefix, 1000.0, 1.0])
    params = VolRecoveryParams(
        trend_ma=20,
        breakout_lookback=10,
        fast_ma=5,
        slow_ma=10,
        trend_slope_lookback=5,
        volatility_lookback=10,
        regime_lookback=20,
    )

    left = cashflow_vol_recovery_weights(first, params=params).iloc[:80]
    right = cashflow_vol_recovery_weights(second, params=params).iloc[:80]

    pd.testing.assert_frame_equal(left, right)


def test_stage1_search_covers_three_sizing_families() -> None:
    configs = stage1_configs()
    params = [value for _, value in configs]

    assert len(configs) == 594
    assert {value.family for value in params} == {"target_vol", "vol_band", "hybrid"}
    assert {value.trend_ma for value in params} == {100, 120, 160}
    assert {value.breakout_lookback for value in params} == {20, 40, 55}


def test_nonhybrid_loss_stop_can_equal_unused_reduce_trigger() -> None:
    params = VolRecoveryParams(family="target_vol", loss_stop=0.04, reduce_trigger=0.04)

    assert params.loss_stop == params.reduce_trigger
