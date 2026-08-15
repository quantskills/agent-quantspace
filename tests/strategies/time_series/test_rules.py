from __future__ import annotations

import pandas as pd
import pytest

from skills.compute.indicators import ma_cross
from strategies.time_series.rules import (
    ma_golden_death_cross_signal,
    ma_golden_death_cross_weights,
    ma_reversion_atr_stop_signal,
    ma_reversion_atr_stop_weights,
)


def _bars(prices: list[float]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(prices), name="eob")
    close = pd.Series(prices, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000.0,
        },
        index=index,
    )


def test_ma_reversion_atr_stop_weights_exit_on_trailing_stop() -> None:
    weights = ma_reversion_atr_stop_weights(
        _bars([10.0, 9.0, 8.0, 11.0, 12.0, 8.0]),
        symbol="CFFEX.IF99",
        ma_lookback=3,
        atr_lookback=2,
        atr_multiplier=1.0,
    )

    assert weights.columns.tolist() == ["CFFEX.IF99"]
    assert weights["CFFEX.IF99"].tolist() == [0.0, 0.0, 1.0, 1.0, 1.0, 0.0]


def test_ma_reversion_atr_stop_signal_stays_flat_during_warmup() -> None:
    signal = ma_reversion_atr_stop_signal(
        _bars([10.0, 9.0, 8.0, 7.0]),
        ma_lookback=3,
        atr_lookback=3,
        atr_multiplier=1.0,
    )

    assert signal.iloc[:2].tolist() == [0.0, 0.0]


def test_ma_reversion_atr_stop_signal_rejects_invalid_parameters() -> None:
    bars = _bars([10.0, 9.0, 8.0, 7.0])
    with pytest.raises(ValueError, match="ma_lookback"):
        ma_reversion_atr_stop_signal(bars, ma_lookback=1)
    with pytest.raises(ValueError, match="atr_lookback"):
        ma_reversion_atr_stop_signal(bars, atr_lookback=1)
    with pytest.raises(ValueError, match="atr_multiplier"):
        ma_reversion_atr_stop_signal(bars, atr_multiplier=0.0)


def test_ma_golden_death_cross_signal_matches_positive_ma_spread() -> None:
    bars = _bars([10.0, 10.0, 11.0, 12.0, 13.0, 12.0, 10.0, 8.0, 7.0, 9.0, 11.0, 13.0])
    signal = ma_golden_death_cross_signal(bars, short=2, long=4)
    spread = ma_cross(bars, short=2, long=4)
    expected = (spread > 0).astype(float).where(spread.notna(), 0.0)

    assert signal.tolist() == expected.tolist()
    assert signal.iloc[:3].tolist() == [0.0, 0.0, 0.0]
    assert signal.max() == 1.0


def test_ma_golden_death_cross_goes_long_after_golden_and_flat_after_death() -> None:
    prices = [10.0] * 6 + [14.0, 16.0, 18.0, 20.0, 22.0] + [8.0, 6.0, 4.0, 2.0]
    weights = ma_golden_death_cross_weights(
        _bars(prices),
        symbol="SHSE.510300",
        short=2,
        long=4,
    )
    series = weights["SHSE.510300"]

    assert weights.columns.tolist() == ["SHSE.510300"]
    assert series.iloc[:3].tolist() == [0.0, 0.0, 0.0]
    assert series.max() == 1.0
    assert series.eq(1.0).any()
    assert series.iloc[-1] == 0.0


def test_ma_golden_death_cross_signal_rejects_invalid_parameters() -> None:
    bars = _bars([10.0, 9.0, 8.0, 7.0])
    with pytest.raises(ValueError, match="short"):
        ma_golden_death_cross_signal(bars, short=0, long=4)
    with pytest.raises(ValueError, match="long"):
        ma_golden_death_cross_signal(bars, short=4, long=4)
