"""Reusable cross-sectional selection and rebalance helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd


def top_n_weights(
    scores: pd.DataFrame,
    *,
    top_n: int,
    gross_exposure: float = 1.0,
) -> pd.DataFrame:
    """Equal-weight the highest-scoring available names on each date."""
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    if gross_exposure < 0:
        raise ValueError("gross_exposure must be non-negative")

    ranks = scores.rank(axis=1, method="first", ascending=False)
    selected = ranks.le(top_n) & scores.notna()
    selected_counts = selected.sum(axis=1)
    weights = selected.astype(float).div(
        selected_counts.where(selected_counts.ne(0)),
        axis=0,
    )
    return weights.fillna(0.0) * gross_exposure


def apply_rebalance_schedule(
    weights: pd.DataFrame,
    *,
    every: int,
    start: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Sample target weights every N rows and hold them until the next rebalance."""
    if isinstance(every, bool) or not isinstance(every, (int, np.integer)) or every <= 0:
        raise ValueError("every must be a positive integer")
    eligible = np.ones(len(weights), dtype=bool)
    if start is not None:
        eligible = np.asarray(weights.index >= pd.Timestamp(start))
    positions = np.flatnonzero(eligible)
    sampled = weights.astype(float).copy()
    sampled.loc[:, :] = np.nan
    sampled.iloc[positions[:: int(every)]] = weights.iloc[positions[:: int(every)]]
    return sampled.ffill().fillna(0.0)


__all__ = ["apply_rebalance_schedule", "top_n_weights"]
