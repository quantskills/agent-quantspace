"""Generic public factors for cross-sectional examples."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _require_close(group: pd.DataFrame) -> pd.Series:
    if "close" not in group.columns:
        raise ValueError("factor requires a 'close' column.")
    return group["close"].astype(float)


def momentum_score(group: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """Simple trailing return. Higher values rank stronger recent winners first."""
    if lookback <= 0:
        raise ValueError("lookback must be positive.")
    close = _require_close(group)
    return close / close.shift(lookback) - 1.0


def volatility_score(group: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """Negative realized volatility. Higher values rank lower-volatility assets first."""
    if lookback <= 1:
        raise ValueError("lookback must be greater than 1.")
    close = _require_close(group)
    returns = close.pct_change()
    return -returns.rolling(lookback, min_periods=lookback).std()


def trend_score(group: pd.DataFrame, lookback: int = 60) -> pd.Series:
    """Rolling log-price slope annualized by trading days."""
    if lookback <= 1:
        raise ValueError("lookback must be greater than 1.")
    close = _require_close(group)
    log_close = np.log(close)
    x = np.arange(lookback, dtype=float)
    x = x - x.mean()
    denominator = float(np.dot(x, x))

    def _slope(window: np.ndarray) -> float:
        y = window - window.mean()
        return float(np.dot(x, y) / denominator * 252.0)

    return log_close.rolling(lookback, min_periods=lookback).apply(_slope, raw=True)


def mean_reversion_score(group: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """Negative z-score of price versus moving average."""
    if lookback <= 1:
        raise ValueError("lookback must be greater than 1.")
    close = _require_close(group)
    mean = close.rolling(lookback, min_periods=lookback).mean()
    std = close.rolling(lookback, min_periods=lookback).std()
    zscore = (close - mean) / std.replace(0.0, np.nan)
    return -zscore


__all__ = [
    "mean_reversion_score",
    "momentum_score",
    "trend_score",
    "volatility_score",
]
