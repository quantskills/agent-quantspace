from __future__ import annotations

import pytest

from strategies.cross_sectional.exits import (
    big_loss_filter,
    consecutive_loss_filter,
    drawdown_from_high_filter,
    gap_down_filter,
)
from tests.fixtures.market_data import make_ohlcv


def test_exit_filters_return_multiindex_risk_series() -> None:
    panel = make_ohlcv([100.0, 99.0, 95.0, 94.0, 93.0], symbol="AAA")

    gap = gap_down_filter(panel, gap_threshold=0.01, drop_threshold=0.02)
    losses = consecutive_loss_filter(panel, n_days=2)
    drawdown = drawdown_from_high_filter(panel, lookback=3)
    big_loss = big_loss_filter(panel, threshold=0.02)

    assert gap.index.names == ["symbol", "eob"]
    assert gap.iloc[2] == 1.0
    assert losses.iloc[-1] >= 3
    assert drawdown.iloc[-1] > 0.0
    assert big_loss.iloc[2] == pytest.approx(0.0404040404)
