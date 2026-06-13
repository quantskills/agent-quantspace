"""Small generic time-series factor examples.

Each function accepts one instrument's OHLCV frame and returns a Series aligned
to the input index. These helpers are intentionally simple so they can be used
as public examples or as inputs to ``skills.compute.wrappers.Factor``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "ts_momentum",
    "ts_volatility",
    "ts_trend_slope",
    "ts_mean_reversion_zscore",
]


def _require_price(group: pd.DataFrame, price_col: str, func_name: str) -> pd.Series:
    if price_col not in group.columns:
        raise ValueError(f"{func_name} requires '{price_col}' column")
    return group[price_col].astype(float)


def _require_lookback(lookback: int, func_name: str, *, minimum: int = 1) -> None:
    if lookback < minimum:
        raise ValueError(f"{func_name} requires lookback >= {minimum}")


def ts_momentum(
    group: pd.DataFrame,
    *,
    lookback: int = 20,
    price_col: str = "close",
) -> pd.Series:
    """Trailing percentage return over ``lookback`` bars."""

    _require_lookback(lookback, "ts_momentum")
    price = _require_price(group, price_col, "ts_momentum")
    return price.pct_change(lookback).rename(None)


def ts_volatility(
    group: pd.DataFrame,
    *,
    lookback: int = 20,
    price_col: str = "close",
    annualization: int = 252,
) -> pd.Series:
    """Annualized trailing return volatility."""

    _require_lookback(lookback, "ts_volatility")
    if annualization <= 0:
        raise ValueError("ts_volatility requires positive annualization")

    price = _require_price(group, price_col, "ts_volatility")
    returns = price.pct_change()
    volatility = returns.rolling(lookback, min_periods=lookback).std(ddof=0)
    return (volatility * np.sqrt(float(annualization))).rename(None)


def ts_trend_slope(
    group: pd.DataFrame,
    *,
    lookback: int = 20,
    price_col: str = "close",
) -> pd.Series:
    """Rolling OLS slope of log price over ``lookback`` bars."""

    _require_lookback(lookback, "ts_trend_slope", minimum=2)
    price = _require_price(group, price_col, "ts_trend_slope")
    log_price = np.log(price.where(price > 0.0))
    x = np.arange(lookback, dtype=float)
    x_centered = x - x.mean()
    denominator = float(np.sum(x_centered**2))

    def slope(values: np.ndarray) -> float:
        if not np.isfinite(values).all():
            return np.nan
        y_centered = values - values.mean()
        return float(np.sum(y_centered * x_centered) / denominator)

    return log_price.rolling(lookback, min_periods=lookback).apply(slope, raw=True).rename(None)


def ts_mean_reversion_zscore(
    group: pd.DataFrame,
    *,
    lookback: int = 20,
    price_col: str = "close",
) -> pd.Series:
    """Negative rolling price z-score, so lower-than-average prices rank higher."""

    _require_lookback(lookback, "ts_mean_reversion_zscore", minimum=2)
    price = _require_price(group, price_col, "ts_mean_reversion_zscore")
    mean = price.rolling(lookback, min_periods=lookback).mean()
    std = price.rolling(lookback, min_periods=lookback).std(ddof=0).replace(0.0, np.nan)
    return (-(price - mean) / std).rename(None)
