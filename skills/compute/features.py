"""Strategy-agnostic OHLCV feature builders."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import product

import numpy as np
import pandas as pd

DEFAULT_LOGDIFF_FACTORS: tuple[str, ...] = ("open", "close", "high", "low")
DEFAULT_LOGDIFF_LAGS: tuple[int, ...] = (1, 2, 3, 4, 5, 10, 15, 20, 25)


def default_logdiff_shifts(lookback: int = 5) -> tuple[int, ...]:
    """Shifts aligned with the reference logdiff notebook when ``lookback=5``."""
    if lookback < 1:
        raise ValueError("lookback must be positive.")
    lookback_list = list(range(lookback))
    lookback_x_5 = [(index + 1) * 5 for index in lookback_list]
    return tuple(lookback_list + lookback_x_5)


def make_logdiff_features(
    bars: pd.DataFrame,
    *,
    factors: Sequence[str] = DEFAULT_LOGDIFF_FACTORS,
    lags: Sequence[int] = DEFAULT_LOGDIFF_LAGS,
    shifts: Sequence[int] | None = None,
    lookback: int = 5,
) -> pd.DataFrame:
    """Build OHLC log-difference features for a single instrument.

    For each ``(f1, f2, lag)`` combination compute ``log(f1) - log(f2).shift(lag)``
    and emit one column per ``shift`` as ``logdiff_{f1}_{f2}{lag}_shift{shift}``.

    Non-positive prices (zero open/high/low on non-trading days) become NaN instead
    of ``-inf`` so downstream ``dropna`` removes them.

    Default parameters match the reference notebook (``lookback=5`` → 1440 columns).
    """
    if lookback < 1:
        raise ValueError("lookback must be positive.")
    factor_list = tuple(factors)
    lag_list = tuple(lags)
    if not factor_list:
        raise ValueError("factors must not be empty.")
    if not lag_list:
        raise ValueError("lags must not be empty.")
    if any(lag < 1 for lag in lag_list):
        raise ValueError("lags must be positive integers.")

    shift_list = tuple(shifts) if shifts is not None else default_logdiff_shifts(lookback)
    if any(shift < 0 for shift in shift_list):
        raise ValueError("shifts must be non-negative integers.")

    missing = [column for column in factor_list if column not in bars.columns]
    if missing:
        raise ValueError(f"bars is missing OHLC columns: {missing}")

    log_bars = pd.DataFrame(
        {column: _positive_log(bars[column]) for column in factor_list},
        index=bars.index,
    )
    features: dict[str, pd.Series] = {}
    for left, right, lag in product(factor_list, factor_list, lag_list):
        base = log_bars[left] - log_bars[right].shift(lag)
        for shift in shift_list:
            features[f"logdiff_{left}_{right}{lag}_shift{shift}"] = base.shift(shift)
    return pd.DataFrame(features, index=bars.index)


def _positive_log(prices: pd.Series) -> pd.Series:
    values = prices.astype(float)
    return np.log(values.where(values > 0.0))


def make_logdiff_panel_features(
    panel: pd.DataFrame,
    *,
    factors: Sequence[str] = DEFAULT_LOGDIFF_FACTORS,
    lags: Sequence[int] = DEFAULT_LOGDIFF_LAGS,
    shifts: Sequence[int] | None = None,
    lookback: int = 5,
) -> pd.DataFrame:
    """Build model-ready LogDiff features for a ``(symbol, eob)`` OHLCV panel.

    Each symbol is transformed independently by :func:`make_logdiff_features`; rows
    that are not finite (warm-up bars, non-positive prices) are dropped so the
    returned panel can be fed to estimators without further cleaning.
    """
    frames: list[pd.DataFrame] = []
    for symbol, group in panel.groupby(level="symbol", sort=False):
        frame = make_logdiff_features(
            group.droplevel("symbol"),
            factors=factors,
            lags=lags,
            shifts=shifts,
            lookback=lookback,
        ).dropna()
        frame.index = pd.MultiIndex.from_product(
            [[symbol], frame.index],
            names=["symbol", "eob"],
        )
        frames.append(frame)
    if not frames:
        raise ValueError("panel cannot be empty.")
    return pd.concat(frames).sort_index()


__all__ = [
    "DEFAULT_LOGDIFF_FACTORS",
    "DEFAULT_LOGDIFF_LAGS",
    "default_logdiff_shifts",
    "make_logdiff_features",
    "make_logdiff_panel_features",
]
