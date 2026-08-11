from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.time_series.cashflow_donchian_atr import DonchianAtrParams, donchian_atr_weights
from strategies.time_series.workflows.run_cashflow_donchian_atr_is import core_configs


def _bars(prices: list[float]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(prices), name="eob")
    return pd.DataFrame({"close": prices}, index=index, dtype=float)


def test_donchian_breakout_enters_and_atr_stop_exits() -> None:
    prices = [10, 10, 10, 10, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 14]
    params = DonchianAtrParams(
        entry_lookback=4,
        exit_lookback=2,
        atr_lookback=2,
        atr_multiplier=2.0,
    )

    weights = donchian_atr_weights(_bars(prices), params=params).iloc[:, 0]

    assert weights.iloc[:5].eq(0.0).all()
    assert weights.iloc[5:15].eq(1.0).all()
    assert weights.iloc[-1] == 0.0


def test_donchian_rule_has_no_future_dependency() -> None:
    prefix = np.linspace(10.0, 30.0, 80)
    params = DonchianAtrParams(
        entry_lookback=20,
        exit_lookback=10,
        atr_lookback=5,
        atr_multiplier=3.0,
    )
    left = donchian_atr_weights(_bars([*prefix, 31.0, 32.0]), params=params).iloc[:80]
    right = donchian_atr_weights(_bars([*prefix, 1000.0, 1.0]), params=params).iloc[:80]

    pd.testing.assert_frame_equal(left, right)


def test_core_grid_covers_channel_and_atr_ranges() -> None:
    configs = core_configs()
    params = [value for _, value in configs]

    assert len(configs) == 360
    assert {value.entry_lookback for value in params} == {20, 40, 55, 80, 120}
    assert {value.atr_lookback for value in params} == {14, 20, 30, 40}
    assert {value.atr_multiplier for value in params} == {2.0, 2.5, 3.0, 3.5, 4.0}
