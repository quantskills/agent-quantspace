from __future__ import annotations

import numpy as np
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
    assert "orb_relvol" in registry
    assert callable(registry["trend_score"])


def test_discover_indicators_excludes_removed_formulas() -> None:
    registry = indicators.discover_indicators()
    removed = {
        "momentum_acceleration",
        "momentum_weighted",
        "high_vol_odds",
        "ma_vol",
        "ma_vol_ratio",
        "stand_orb_relvol",
        "orb",
        "er_enhanced",
        "er_adaptive",
        "er_directional",
        "rsrs",
        "rsrs_v1",
        "rsrs_v2",
        "rsrs_v3",
        "rsrs_norm",
        "bollinger_reversal",
        "mean_reversion",
        "price_drawdown",
        "atr_stop",
        "volatility_regime",
        "volatility_inv",
        "fund_premium_rate",
    }

    assert removed.isdisjoint(registry)


def test_trend_score_is_annualized_log_slope_times_r_squared() -> None:
    daily_log_slope = 0.001
    close = np.exp(daily_log_slope * np.arange(30))
    bars = make_ohlcv(close.tolist())

    score = indicators.trend_score(bars, period=25)

    assert score.iloc[:24].isna().all()
    assert score.iloc[-1] == pytest.approx(daily_log_slope * 252.0)


def test_trend_score_is_invariant_to_price_scale() -> None:
    close = np.exp(0.001 * np.arange(30))
    bars = make_ohlcv(close.tolist())
    scaled_bars = make_ohlcv((close * 100.0).tolist())

    score = indicators.trend_score(bars, period=25)
    scaled_score = indicators.trend_score(scaled_bars, period=25)

    assert scaled_score.iloc[-1] == pytest.approx(score.iloc[-1])


def test_trend_score_validates_period() -> None:
    bars = make_ohlcv([10.0, 11.0, 12.0])

    with pytest.raises(ValueError, match="greater than 1"):
        indicators.trend_score(bars, period=1)
