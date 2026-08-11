"""Time-series feature helpers for public strategy examples."""

from __future__ import annotations

import numpy as np
import pandas as pd

from skills.compute.features import make_logdiff_features

# Public time-series recipe keeps the original lag/shift grid (lags 1..5,
# shifts 0..diff_lookback-1) rather than the reference notebook's full 1440d set.


def make_price_volume_features(bars: pd.DataFrame, diff_lookback: int = 5) -> pd.DataFrame:
    """Build public OHLCV features used by the time-series ML example."""
    if diff_lookback < 1:
        raise ValueError("diff_lookback must be positive.")
    features = make_logdiff_features(
        bars,
        lags=(1, 2, 3, 4, 5),
        shifts=tuple(range(diff_lookback)),
        lookback=diff_lookback,
    )
    close = bars["close"].astype(float)
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)
    open_ = bars["open"].astype(float)
    volume = bars["volume"].astype(float)

    for lookback in [1, 2, 3, 5, 10, 20, 40, 60, 120, 160]:
        features[f"return_{lookback}"] = close.pct_change(lookback, fill_method=None)
    for lookback in [10, 20, 40, 60, 120, 160]:
        moving_average = close.rolling(lookback, min_periods=lookback).mean()
        features[f"ma_gap_{lookback}"] = close / moving_average - 1.0
        features[f"volatility_{lookback}"] = (
            close.pct_change(fill_method=None).rolling(lookback, min_periods=lookback).std()
        )

    features["intraday_return"] = close / open_ - 1.0
    features["high_low_range"] = high / low - 1.0
    features["volume_change_5"] = volume.pct_change(5, fill_method=None)
    return features.replace([np.inf, -np.inf], np.nan).dropna()


__all__ = ["make_price_volume_features"]
