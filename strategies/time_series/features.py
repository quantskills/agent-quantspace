"""Time-series feature helpers for public strategy examples."""

from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd


def _make_logdiff_features(bars: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Build OHLC log-difference features for the public time-series strategy."""
    if lookback < 1:
        raise ValueError("diff_lookback must be positive.")
    base_factors = ["open", "close", "high", "low"]
    missing = [column for column in base_factors if column not in bars.columns]
    if missing:
        raise ValueError(f"bars is missing OHLC columns: {missing}")

    log_bars = pd.DataFrame(
        {column: np.log(bars[column].astype(float)) for column in base_factors},
        index=bars.index,
    )
    features: dict[str, pd.Series] = {}
    for left, right, lag in product(base_factors, base_factors, [1, 2, 3, 4, 5]):
        base = log_bars[left] - log_bars[right].shift(lag)
        for shift in range(lookback):
            features[f"logdiff_{left}_{right}{lag}_shift{shift}"] = base.shift(shift)
    return pd.DataFrame(features, index=bars.index)


def make_price_volume_features(bars: pd.DataFrame, diff_lookback: int = 5) -> pd.DataFrame:
    """Build public OHLCV features used by the time-series ML example."""
    features = _make_logdiff_features(bars, lookback=diff_lookback)
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
