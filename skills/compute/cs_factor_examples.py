"""Small generic cross-sectional factor examples.

Functions operate on a panel indexed by ``(symbol, eob)`` and return a Series
aligned to the input index. They are deliberately compact examples for public
ETF rotation or asset-selection demos.
"""

from __future__ import annotations

import pandas as pd

from skills.compute.ts_factor_examples import (
    ts_mean_reversion_zscore,
    ts_momentum,
    ts_trend_slope,
    ts_volatility,
)

__all__ = [
    "cs_momentum_score",
    "cs_volatility_score",
    "cs_trend_score",
    "cs_mean_reversion_score",
]


def _validate_panel(panel: pd.DataFrame, *, required_columns: set[str], func_name: str) -> None:
    if not isinstance(panel.index, pd.MultiIndex):
        raise ValueError(f"{func_name} requires MultiIndex input")
    if not {"symbol", "eob"}.issubset(panel.index.names):
        raise ValueError(f"{func_name} requires MultiIndex with 'symbol' and 'eob'")

    missing_columns = required_columns.difference(panel.columns)
    if missing_columns:
        missing = "', '".join(sorted(missing_columns))
        raise ValueError(f"{func_name} requires '{missing}' column")


def _apply_by_symbol(
    panel: pd.DataFrame,
    *,
    func_name: str,
    required_columns: set[str],
    factor_func,
    lookback: int,
    price_col: str,
) -> pd.Series:
    _validate_panel(panel, required_columns=required_columns, func_name=func_name)

    pieces = [
        factor_func(group, lookback=lookback, price_col=price_col)
        for _, group in panel.groupby(level="symbol", sort=False)
    ]
    if not pieces:
        return pd.Series(index=panel.index, dtype=float)
    return pd.concat(pieces).reindex(panel.index).rename(None)


def cs_momentum_score(
    panel: pd.DataFrame,
    *,
    lookback: int = 20,
    price_col: str = "close",
) -> pd.Series:
    """Per-symbol trailing return aligned to the panel index."""

    return _apply_by_symbol(
        panel,
        func_name="cs_momentum_score",
        required_columns={price_col},
        factor_func=ts_momentum,
        lookback=lookback,
        price_col=price_col,
    )


def cs_volatility_score(
    panel: pd.DataFrame,
    *,
    lookback: int = 20,
    price_col: str = "close",
) -> pd.Series:
    """Negative realized volatility, so lower-volatility assets rank higher."""

    return -_apply_by_symbol(
        panel,
        func_name="cs_volatility_score",
        required_columns={price_col},
        factor_func=ts_volatility,
        lookback=lookback,
        price_col=price_col,
    )


def cs_trend_score(
    panel: pd.DataFrame,
    *,
    lookback: int = 20,
    price_col: str = "close",
) -> pd.Series:
    """Rolling log-price trend slope for each symbol."""

    return _apply_by_symbol(
        panel,
        func_name="cs_trend_score",
        required_columns={price_col},
        factor_func=ts_trend_slope,
        lookback=lookback,
        price_col=price_col,
    )


def cs_mean_reversion_score(
    panel: pd.DataFrame,
    *,
    lookback: int = 20,
    price_col: str = "close",
) -> pd.Series:
    """Negative rolling z-score for each symbol."""

    return _apply_by_symbol(
        panel,
        func_name="cs_mean_reversion_score",
        required_columns={price_col},
        factor_func=ts_mean_reversion_zscore,
        lookback=lookback,
        price_col=price_col,
    )
