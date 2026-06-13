from __future__ import annotations

from strategies.time_series.features import make_price_volume_features
from tests.fixtures.market_data import make_ohlcv


def test_make_price_volume_features_adds_diff_and_ohlcv_derivatives() -> None:
    bars = make_ohlcv([100.0 + i for i in range(220)])

    features = make_price_volume_features(bars, diff_lookback=2)

    assert "logdiff_open_open1_shift0" in features.columns
    assert "return_20" in features.columns
    assert "ma_gap_160" in features.columns
    assert "high_low_range" in features.columns
    assert not features.isna().any().any()
