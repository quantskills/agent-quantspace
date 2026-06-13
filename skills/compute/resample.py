"""A-share session-aware intraday resampling helpers."""

from __future__ import annotations

import pandas as pd

SESSION_WINDOWS = (
    ("09:31", "11:30", "09:30"),
    ("13:01", "15:00", "13:00"),
)


def _validate_ohlcv_columns(df: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close", "volume"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"resample_to_5m missing required columns: {missing}")


def _session_resample(df: pd.DataFrame, start: str, end: str, anchor: str) -> pd.DataFrame:
    session = df.between_time(start, end, inclusive="both")
    if session.empty:
        return session
    session_start = pd.Timedelta(hours=int(anchor[:2]), minutes=int(anchor[3:5]))
    session_dates = session.index.normalize()
    offset = ((session.index - session_dates - session_start).total_seconds() // 60).astype(int)
    bucket = ((offset - 1) // 5 + 1).astype(int)
    grouped = session.groupby([session_dates, bucket], sort=True)
    agg = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    labels = [d + session_start + pd.Timedelta(minutes=int(b) * 5) for d, b in agg.index.to_list()]
    agg.index = pd.DatetimeIndex(labels, name=session.index.name or "eob")
    return agg


def resample_to_5m(df_1m: pd.DataFrame) -> pd.DataFrame:
    """
    Resample 1-minute OHLCV bars to 5-minute bars without crossing lunch break.

    Rules:
    - Input index must be tz-naive DatetimeIndex named ``eob`` (name optional).
    - Only A-share eob sessions are kept (09:31-11:30 and 13:01-15:00).
    - 5-minute output uses right-edge eob timestamps such as 09:35 and 15:00.
    - Zero-volume minutes are removed before aggregation.
    """
    if not isinstance(df_1m.index, pd.DatetimeIndex):
        raise ValueError("resample_to_5m expects DatetimeIndex")
    if df_1m.index.tz is not None:
        raise ValueError("resample_to_5m expects tz-naive DatetimeIndex")
    _validate_ohlcv_columns(df_1m)

    base = df_1m.sort_index()
    base = base[base["volume"].fillna(0) > 0]
    if base.empty:
        return base.copy()

    frames: list[pd.DataFrame] = []
    for start, end, anchor in SESSION_WINDOWS:
        frames.append(_session_resample(base, start, end, anchor))
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out.index.name = df_1m.index.name or "eob"
    return out
