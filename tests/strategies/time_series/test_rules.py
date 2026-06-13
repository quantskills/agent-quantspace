from __future__ import annotations

import pandas as pd
import pytest

from strategies.time_series.rules import (
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
