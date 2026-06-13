"""I/O helpers for backtesting data."""

from __future__ import annotations

import pandas as pd


def load_price_data(
    filepath: str,
    symbol_col: str = "symbol",
    time_col: str = "eob",
) -> pd.DataFrame:
    """Load OHLCV data from CSV into a sorted MultiIndex DataFrame."""
    df = pd.read_csv(filepath)
    df[time_col] = (
        pd.to_datetime(df[time_col], utc=True).dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
    )

    price_cols = ["open", "high", "low", "close", "volume"]
    keep_cols = [symbol_col, time_col] + [column for column in price_cols if column in df.columns]
    result = df[keep_cols].set_index([symbol_col, time_col]).sort_index()
    result.index.names = ["symbol", "eob"]
    return result
