"""Rule-based time-series strategy helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from skills.compute.indicators import ma_cross
from skills.compute.utils import calculate_atr
from skills.strategy.time_series import signal_to_single_asset_weights


def ma_reversion_atr_stop_signal(
    bars: pd.DataFrame,
    ma_lookback: int = 10,
    atr_lookback: int = 14,
    atr_multiplier: float = 2.0,
) -> pd.Series:
    """Long below moving average, exit via ATR trailing stop."""
    if ma_lookback <= 1:
        raise ValueError("ma_lookback must be greater than 1.")
    if atr_lookback <= 1:
        raise ValueError("atr_lookback must be greater than 1.")
    if atr_multiplier <= 0:
        raise ValueError("atr_multiplier must be positive.")

    close = bars["close"].astype(float)
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)
    moving_average = close.rolling(ma_lookback, min_periods=ma_lookback).mean()
    atr = calculate_atr(high, low, close, atr_lookback)

    weights = []
    position = 0.0
    high_water = np.nan
    stop_level = np.nan
    for date in close.index:
        price = float(close.loc[date])
        average = moving_average.loc[date]
        current_atr = atr.loc[date]
        current_high = float(high.loc[date])

        if pd.isna(average) or pd.isna(current_atr):
            weights.append(0.0)
            continue

        if position == 0.0:
            if price < float(average):
                position = 1.0
                high_water = max(price, current_high)
                stop_level = high_water - atr_multiplier * float(current_atr)
        else:
            high_water = max(high_water, price, current_high)
            stop_level = max(stop_level, high_water - atr_multiplier * float(current_atr))
            if price <= stop_level:
                position = 0.0
                high_water = np.nan
                stop_level = np.nan
        weights.append(position)

    return pd.Series(weights, index=close.index, dtype=float)


def ma_reversion_atr_stop_weights(
    bars: pd.DataFrame,
    symbol: str,
    ma_lookback: int = 10,
    atr_lookback: int = 14,
    atr_multiplier: float = 2.0,
) -> pd.DataFrame:
    """Return a date x symbol weight matrix for the MA/ATR rule."""
    signal = ma_reversion_atr_stop_signal(
        bars,
        ma_lookback=ma_lookback,
        atr_lookback=atr_lookback,
        atr_multiplier=atr_multiplier,
    )
    return signal_to_single_asset_weights(signal, symbol=symbol)


def ma_golden_death_cross_signal(
    bars: pd.DataFrame,
    short: int = 10,
    long: int = 60,
) -> pd.Series:
    """Long while the short MA is above the long MA; flat otherwise.

    A golden cross (short MA crossing above the long MA) enters +1. A death
    cross (short MA crossing below the long MA) exits to 0. Warm-up bars stay
    flat. Equal moving averages are treated as flat.
    """
    if short < 1:
        raise ValueError("short must be at least 1.")
    if long <= short:
        raise ValueError("long must be greater than short.")

    spread = ma_cross(bars, short=short, long=long)
    position = (spread > 0).astype(float)
    return position.where(spread.notna(), 0.0).astype(float)


def ma_golden_death_cross_weights(
    bars: pd.DataFrame,
    symbol: str,
    short: int = 10,
    long: int = 60,
) -> pd.DataFrame:
    """Return a date x symbol weight matrix for the MA golden/death-cross rule."""
    signal = ma_golden_death_cross_signal(bars, short=short, long=long)
    return signal_to_single_asset_weights(signal, symbol=symbol)


__all__ = [
    "ma_golden_death_cross_signal",
    "ma_golden_death_cross_weights",
    "ma_reversion_atr_stop_signal",
    "ma_reversion_atr_stop_weights",
]
