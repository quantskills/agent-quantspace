"""Quality checks for adjusted market data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .data_manager import DataManager

QUALITY_COLUMNS = [
    "symbol",
    "eob",
    "close",
    "reference_close",
    "relative_change",
    "volume",
    "is_suspended",
]


def find_zero_volume_price_jumps(
    frame: pd.DataFrame,
    symbol: str = "",
    price_col: str = "close",
    volume_col: str = "volume",
    suspended_col: str = "is_suspended",
    threshold: float = 0.2,
) -> pd.DataFrame:
    """Find zero-volume or suspended adjusted rows with implausible price jumps."""
    if price_col not in frame.columns:
        return pd.DataFrame(columns=QUALITY_COLUMNS)

    close = pd.to_numeric(frame[price_col], errors="coerce")
    zero_or_suspended = pd.Series(False, index=frame.index)
    if volume_col in frame.columns:
        volume = pd.to_numeric(frame[volume_col], errors="coerce")
        zero_or_suspended = zero_or_suspended | volume.fillna(0.0).le(0.0)
    else:
        volume = pd.Series(pd.NA, index=frame.index, dtype="Float64")

    if suspended_col in frame.columns:
        suspended = frame[suspended_col].fillna(False).astype(bool)
        zero_or_suspended = zero_or_suspended | suspended
    else:
        suspended = pd.Series(False, index=frame.index)

    reference_close = close.where(~zero_or_suspended).ffill()
    relative_change = close.div(reference_close).sub(1.0)
    issues = (
        zero_or_suspended & reference_close.notna() & relative_change.abs().gt(float(threshold))
    )
    if not bool(issues.any()):
        return pd.DataFrame(columns=QUALITY_COLUMNS)

    result = pd.DataFrame(
        {
            "symbol": symbol,
            "eob": pd.to_datetime(frame.index[issues]),
            "close": close.loc[issues].astype(float).to_numpy(),
            "reference_close": reference_close.loc[issues].astype(float).to_numpy(),
            "relative_change": relative_change.loc[issues].astype(float).to_numpy(),
            "volume": volume.loc[issues].astype(float).to_numpy(),
            "is_suspended": suspended.loc[issues].astype(bool).to_numpy(),
        }
    )
    return result.reset_index(drop=True)


def scan_adjusted_market_data(
    symbols: list[str],
    frequency: str = "1d_adj",
    data_root: str | Path | None = None,
    threshold: float = 0.2,
) -> pd.DataFrame:
    """Scan adjusted data files for zero-volume or suspended price jumps."""
    dm = DataManager(data_root=str(data_root) if data_root is not None else None)
    issues = []
    for symbol in symbols:
        try:
            frame = dm.read_symbol(symbol, frequency=frequency)
        except FileNotFoundError:
            continue
        issues.append(find_zero_volume_price_jumps(frame, symbol=symbol, threshold=threshold))

    non_empty = [item for item in issues if len(item) > 0]
    if not non_empty:
        return pd.DataFrame(columns=QUALITY_COLUMNS)
    return pd.concat(non_empty, ignore_index=True)
