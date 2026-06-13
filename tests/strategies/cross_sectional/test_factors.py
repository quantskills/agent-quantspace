from __future__ import annotations

import pytest

from strategies.cross_sectional.factors import (
    mean_reversion_score,
    momentum_score,
    trend_score,
    volatility_score,
)
from tests.fixtures.market_data import make_ohlcv


def test_cross_sectional_factor_scores_are_aligned() -> None:
    bars = make_ohlcv([10.0, 11.0, 12.0, 11.0, 10.0, 9.0])

    momentum = momentum_score(bars, lookback=2)
    low_vol = volatility_score(bars, lookback=3)
    trend = trend_score(bars, lookback=3)
    reversion = mean_reversion_score(bars, lookback=3)

    assert momentum.index.equals(bars.index)
    assert momentum.iloc[-1] == pytest.approx(9.0 / 11.0 - 1.0)
    assert low_vol.iloc[-1] <= 0.0
    assert trend.iloc[-1] < 0.0
    assert reversion.iloc[-1] > 0.0


def test_cross_sectional_factors_validate_lookbacks() -> None:
    bars = make_ohlcv([10.0, 11.0, 12.0])

    with pytest.raises(ValueError, match="positive"):
        momentum_score(bars, lookback=0)
    with pytest.raises(ValueError, match="greater than 1"):
        volatility_score(bars, lookback=1)
