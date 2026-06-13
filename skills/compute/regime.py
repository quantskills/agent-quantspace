"""Simple regime slicing for lithium-cycle studies."""

from __future__ import annotations

import pandas as pd

REGIMES: dict[str, tuple[str, str]] = {
    "up_2019_2021": ("2019-01-02", "2021-12-31"),
    "peak_2022_2023": ("2022-01-01", "2023-12-31"),
    "down_2024_2026": ("2024-01-01", "2026-05-07"),
}


def split_by_regime(
    df: pd.DataFrame,
    regimes: dict[str, tuple[str, str]] | None = None,
    date_level: str = "eob",
) -> dict[str, pd.DataFrame]:
    """
    Slice a DataFrame into named regimes.

    Supports DatetimeIndex or MultiIndex with date level ``date_level``.
    """
    mapping = regimes or REGIMES
    if isinstance(df.index, pd.MultiIndex):
        if date_level not in df.index.names:
            raise ValueError(f"date level '{date_level}' not in MultiIndex names")
        dt_index = pd.DatetimeIndex(df.index.get_level_values(date_level))
    elif isinstance(df.index, pd.DatetimeIndex):
        dt_index = df.index
    else:
        raise ValueError("split_by_regime expects DatetimeIndex or MultiIndex")

    out: dict[str, pd.DataFrame] = {}
    for name, (start, end) in mapping.items():
        mask = (dt_index >= pd.Timestamp(start)) & (dt_index <= pd.Timestamp(end))
        out[name] = df.loc[mask]
    return out
