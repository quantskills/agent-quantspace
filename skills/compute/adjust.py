"""Forward adjustment using cumulative adjustment factors.

Adjustment-factor table schema (indexed by ex_date):
- ex_cum_factor: cumulative adjustment factor, applied on and after ex_date
- ex_factor: per-event factor (cum_new = cum_old * ex_factor on ex_date)
- ex_end_date, announcement_date: metadata

Forward-adjust formula (preserve latest price, scale history down):
    fwd_adj_price_t = raw_price_t * (cum_at_t / cum_at_latest_event)
    fwd_adj_volume_t = raw_volume_t * (cum_at_latest_event / cum_at_t)

At bars on or after the latest ex_date, fwd_adj equals raw (no adjustment).
At earlier bars, historical prices are compressed to be comparable with today.
Volume is scaled inversely so that turnover (price * volume) is preserved.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

PRICE_COLS_DEFAULT: tuple[str, ...] = ("open", "high", "low", "close")


def forward_adjust(
    raw_df: pd.DataFrame,
    adj_factor_df: pd.DataFrame,
    price_cols: Iterable[str] = PRICE_COLS_DEFAULT,
    volume_col: str = "volume",
) -> pd.DataFrame:
    """Apply forward adjustment to an OHLCV DataFrame.

    Parameters
    ----------
    raw_df : DataFrame indexed by DatetimeIndex (1d or intraday), with at least
        one of the price columns and optionally a volume column.
    adj_factor_df : DataFrame indexed by ex_date (DatetimeIndex), must contain
        'ex_cum_factor' and 'ex_factor' columns.
    price_cols : columns to adjust as prices (multiplied by ratio).
    volume_col : column to adjust as volume (divided by ratio).

    Returns a new DataFrame with the same index/columns; input is not mutated.
    """
    if adj_factor_df.empty:
        return raw_df.copy()

    af = adj_factor_df.sort_index()
    cum_latest = float(af["ex_cum_factor"].iloc[-1])
    first_cum = float(af["ex_cum_factor"].iloc[0])
    first_ex_factor = float(af["ex_factor"].iloc[0])
    pre_first_cum = first_cum / first_ex_factor

    left = pd.DataFrame({"_dt": raw_df.index}).sort_values("_dt").reset_index(drop=True)
    right = (
        pd.DataFrame({"_dt": af.index, "_cum": af["ex_cum_factor"].astype(float).values})
        .sort_values("_dt")
        .reset_index(drop=True)
    )
    merged = pd.merge_asof(left, right, on="_dt", direction="backward")
    merged["_cum"] = merged["_cum"].fillna(pre_first_cum)

    cum_at_t = pd.Series(merged["_cum"].values, index=left["_dt"].values)
    cum_at_t = cum_at_t.reindex(raw_df.index)
    ratio = cum_at_t / cum_latest

    out = raw_df.copy()
    for col in price_cols:
        if col in out.columns:
            out[col] = out[col].astype(float).multiply(ratio, axis=0)
    if volume_col in out.columns:
        out[volume_col] = out[volume_col].astype(float).divide(ratio, axis=0)
    return repair_zero_volume_price_stubs(out, price_cols=price_cols, volume_col=volume_col)


def repair_zero_volume_price_stubs(
    adjusted_df: pd.DataFrame,
    price_cols: Iterable[str] = PRICE_COLS_DEFAULT,
    volume_col: str = "volume",
    suspended_col: str = "is_suspended",
) -> pd.DataFrame:
    """Replace zero-volume adjusted OHLC stubs with the prior tradable close.

    Some data providers return an unadjusted previous close on an ex-date that
    is also a suspended day. The row is still useful for calendar alignment and
    volume should remain zero, but OHLC must stay on the adjusted price scale.
    """
    out = adjusted_df.copy()
    existing_price_cols = [col for col in price_cols if col in out.columns]
    if "close" not in out.columns or not existing_price_cols:
        return out

    mask = pd.Series(False, index=out.index)
    if volume_col in out.columns:
        volume = pd.to_numeric(out[volume_col], errors="coerce")
        mask = mask | volume.le(0).fillna(False)
    elif suspended_col in out.columns:
        mask = mask | out[suspended_col].fillna(False).astype(bool)

    if not bool(mask.any()):
        return out

    prior_tradable_close = out["close"].where(~mask).ffill()
    replace = mask & prior_tradable_close.notna()
    if not bool(replace.any()):
        return out

    for col in existing_price_cols:
        out.loc[replace, col] = prior_tradable_close.loc[replace].astype(float)
    return out


def load_adjusted(
    symbol: str,
    frequency: str = "1d",
    data_root: str | None = None,
) -> pd.DataFrame:
    """Convenience loader: read raw OHLCV and apply forward adjust in one shot.

    Reads data/market/{frequency}/{symbol}.parquet and data/adj_factor/{symbol}.parquet,
    returns a forward-adjusted DataFrame. data_root defaults to the quantspace root.
    """
    from pathlib import Path

    root = Path(data_root) if data_root else Path(__file__).resolve().parents[2] / "data"
    raw_path = root / "market" / frequency / f"{symbol}.parquet"
    adj_path = root / "adj_factor" / f"{symbol}.parquet"
    raw = pd.read_parquet(raw_path)
    if not adj_path.exists():
        return raw.copy()
    adj = pd.read_parquet(adj_path)
    return forward_adjust(raw, adj)
