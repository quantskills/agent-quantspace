from __future__ import annotations

import numpy as np
import pandas as pd
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


@pytest.mark.parametrize(("ma_period", "momentum_day"), [(60, 20), (5, 12), (10, 10)])
def test_bias_momentum_value_does_not_depend_on_series_length(ma_period, momentum_day):
    """A date's value must be the same whether or not later rows exist."""
    rng = np.random.default_rng(3)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 200))))
    full = indicators.bias_momentum(
        pd.DataFrame({"close": close}), ma_period=ma_period, momentum_day=momentum_day
    )
    first_valid = ma_period + momentum_day - 2
    assert full.iloc[:first_valid].isna().all() and full.iloc[first_valid:].notna().all()
    for length in (first_valid, first_valid + 1, first_valid + 2, 150):
        prefix = indicators.bias_momentum(
            pd.DataFrame({"close": close.iloc[:length]}),
            ma_period=ma_period,
            momentum_day=momentum_day,
        )
        pd.testing.assert_series_equal(prefix, full.iloc[:length])


def test_williams_r_trend_filter_matches_the_window_definition():
    """The vectorised trend term equals (last - first) / first over each full window."""
    rng = np.random.default_rng(5)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300))))
    close.iloc[[40, 41, 120]] = np.nan
    bars = pd.DataFrame({"high": close * 1.01, "low": close * 0.99, "close": close})
    period, window = 14, 60

    trend = close.rolling(window=period).apply(
        lambda x: (x.iloc[-1] - x.iloc[0]) / x.iloc[0] if x.iloc[0] != 0 else 0, raw=False
    )
    highest, lowest = bars["high"].rolling(period).max(), bars["low"].rolling(period).min()
    raw = ((highest - close) / (highest - lowest)).replace([np.inf, -np.inf], np.nan).fillna(0.5)
    combined = (raw * -100 + 50) * (1 - abs(np.tanh(trend * 20)) * 0.5)
    mean = combined.rolling(window, min_periods=period).mean()
    std = combined.rolling(window, min_periods=period).std()
    expected = ((combined - mean) / std.where(std > 1e-6, 1e-6)).clip(-3, 3)

    actual = indicators.williams_r(bars, period=period, standardize_window=window)
    pd.testing.assert_series_equal(actual, expected, check_names=False, check_exact=True)
