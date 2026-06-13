from __future__ import annotations

import pytest

from skills.compute import indicators
from tests.fixtures.market_data import make_ohlcv


def test_basic_price_indicators_keep_input_index() -> None:
    bars = make_ohlcv([10.0, 11.0, 12.0, 13.0, 14.0])

    roc = indicators.roc(bars, period=2)
    ma = indicators.ma(bars, period=3)
    daily = indicators.daily_return(bars)

    assert roc.index.equals(bars.index)
    assert roc.iloc[-1] == pytest.approx(14.0 / 12.0 - 1.0)
    assert ma.iloc[-1] == pytest.approx((14.0 - 13.0) / 13.0)
    assert daily.iloc[-1] == pytest.approx(14.0 / 13.0 - 1.0)


def test_ma_cross_and_price_above_ma_are_aligned() -> None:
    bars = make_ohlcv([10.0, 10.0, 10.0, 12.0, 14.0, 16.0])

    cross = indicators.ma_cross(bars, short=2, long=4)
    above = indicators.price_above_ma(bars, period=3)

    assert cross.iloc[-1] > 0.0
    assert above.iloc[-1] > 0.0
    assert cross.iloc[:3].isna().all()


def test_discover_indicators_includes_public_callables() -> None:
    registry = indicators.discover_indicators()

    assert "roc" in registry
    assert "ma" in registry
    assert callable(registry["trend_score"])
