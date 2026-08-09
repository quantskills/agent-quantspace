"""Rule-based cross-sectional strategy helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from skills.backtest.weighting import risk_parity
from skills.strategy.cross_sectional import apply_rebalance_schedule, top_n_weights


def ma_gap_reversal_score(close: pd.DataFrame, symbols: list[str], lookback: int) -> pd.DataFrame:
    """Negative distance from moving average; larger means more stretched below MA."""
    if lookback <= 1:
        raise ValueError("lookback must be greater than 1.")
    moving_average = close[symbols].rolling(lookback, min_periods=lookback).mean()
    return -(close[symbols] / moving_average - 1.0)


def ma_gap_reversal_weights(
    close: pd.DataFrame,
    symbols: list[str],
    lookback: int = 120,
    top_n: int = 2,
    vol_lookback: int = 60,
    rebalance_days: int = 3,
) -> pd.DataFrame:
    """Select the most stretched contracts and weight them by inverse volatility."""
    if not symbols:
        raise ValueError("symbols cannot be empty.")
    if top_n < 1:
        raise ValueError("top_n must be positive.")
    if vol_lookback <= 1:
        raise ValueError("vol_lookback must be greater than 1.")
    if rebalance_days < 1:
        raise ValueError("rebalance_days must be positive.")

    score = ma_gap_reversal_score(close, symbols, lookback=lookback)
    votes = top_n_weights(score, top_n=top_n).gt(0.0).astype(float)
    returns = close[symbols].pct_change(fill_method=None)
    weights = risk_parity(
        votes,
        returns_df=returns,
        lookback=vol_lookback,
        min_periods=vol_lookback,
    )
    weights = weights.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if rebalance_days > 1:
        weights = apply_rebalance_schedule(weights, every=rebalance_days)
    return weights.reindex(columns=symbols).fillna(0.0)


__all__ = ["ma_gap_reversal_score", "ma_gap_reversal_weights"]
