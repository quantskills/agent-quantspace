"""Download listed-fund (ETF/LOF) daily bars and save via DataManager.

These are listed funds, not A-share stocks, so they must be fetched with
``get_fund_daily`` (the fund daily API), never ``fetch_market_data(type="stock")``.

PandaData fund-daily APIs cap a single request at 1 year, so ranges are split
into yearly chunks and concatenated.

Adjustment strategy: the unadjusted fund-daily response carries a daily
``cum_adj_factor`` column (cumulative adjustment factor as of each bar).
PandaData's ``get_fund_daily_pre``/``get_fund_daily_post`` endpoints have
uneven coverage for cross-border/LOF proxies, so forward-adjustment is applied
locally from ``cum_adj_factor`` to guarantee a continuous series for all
symbols:

    forward-adjusted price = raw_price * (cum_adj_factor / latest_cum_adj_factor)
    forward-adjusted volume = raw_volume / (cum_adj_factor / latest_cum_adj_factor)

Default target is the 18 large-asset ETF/LOF universe from
``strategies.cross_sectional.asset_class_rotation``.
"""

from __future__ import annotations

import argparse

import pandas as pd

from skills.ingest import PandaDataClient
from skills.store.data_manager import DataManager

DEFAULT_SYMBOL = "SHSE.510300"
# Always fetch the full field set so cum_adj_factor is available for local adjust.
RAW_FIELDS = ["open", "high", "low", "close", "volume", "amount", "cum_adj_factor"]
OUT_COLS = ["open", "high", "low", "close", "volume"]


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep OHLCV + cum_adj_factor, indexed by eob, deduped, sorted."""
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=OUT_COLS + ["cum_adj_factor"])
    frame = raw.drop_duplicates(subset=["date"]).copy()
    frame["eob"] = pd.to_datetime(frame["date"])
    for column in OUT_COLS + ["cum_adj_factor"]:
        if column not in frame.columns:
            frame[column] = 0.0
    return (
        frame.set_index("eob")[OUT_COLS + ["cum_adj_factor"]]
        .sort_index()
        .astype(float)
    )


def _year_chunks(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """Split [start, end] into <=1-year chunks (PandaData fund APIs cap at 1y)."""
    s = pd.Timestamp(start_date)
    e = pd.Timestamp(end_date)
    chunks: list[tuple[str, str]] = []
    cur = s
    while cur <= e:
        nxt = min(cur + pd.DateOffset(years=1) - pd.Timedelta(days=1), e)
        chunks.append((cur.strftime("%Y%m%d"), nxt.strftime("%Y%m%d")))
        cur = nxt + pd.Timedelta(days=1)
    return chunks


def _forward_adjust(bars: pd.DataFrame) -> pd.DataFrame:
    """Apply forward adjustment from the daily cum_adj_factor column.

    Uses the latest cum_adj_factor as the anchor so the most recent prices are
    unchanged and historical prices are scaled to be continuous across
    splits/dividends. Volume is scaled inversely to preserve turnover.
    """
    out = bars[OUT_COLS].copy()
    af = bars["cum_adj_factor"].replace(0, pd.NA)
    if af.dropna().empty:
        return out
    latest = float(af.dropna().iloc[-1])
    if latest == 0:
        return out
    ratio = af / latest  # = 1.0 on the latest bar, < 1.0 for older bars
    for col in ["open", "high", "low", "close"]:
        out[col] = bars[col] * ratio
    out["volume"] = bars["volume"] / ratio
    return out


def download_etf(
    symbol: str,
    start_date: str,
    end_date: str,
    data_root: str | None = None,
    adjust: str = "none",
    frequency: str | None = None,
) -> None:
    client = PandaDataClient()
    parts: list[pd.DataFrame] = []
    for chunk_start, chunk_end in _year_chunks(start_date, end_date):
        raw = client.get_fund_daily(chunk_start, chunk_end, symbol=symbol, fields=RAW_FIELDS)
        if raw is not None and len(raw):
            parts.append(raw)

    bars = _normalize(pd.concat(parts, ignore_index=True) if parts else pd.DataFrame())
    if bars.empty:
        print(f"{symbol}: no data returned")
        return

    # Local forward-adjust from cum_adj_factor (robust for all fund proxies).
    if adjust == "pre":
        out_bars = _forward_adjust(bars)
    elif adjust == "post":
        # Backward-adjust: anchor on the earliest factor so earliest prices
        # are unchanged and later prices are scaled up.
        out_bars = bars[OUT_COLS].copy()
        af = bars["cum_adj_factor"].replace(0, pd.NA)
        if not af.dropna().empty:
            earliest = float(af.dropna().iloc[0])
            if earliest != 0:
                ratio = af / earliest
                for col in ["open", "high", "low", "close"]:
                    out_bars[col] = bars[col] * ratio
                out_bars["volume"] = bars["volume"] / ratio
    else:
        out_bars = bars[OUT_COLS].copy()

    # Default frequency mirrors the adjust mode: adjusted -> 1d_adj, raw -> 1d.
    # 1d_adj is still daily; the _adj suffix only marks adjustment-applied prices.
    if frequency is None:
        frequency = "1d_adj" if adjust in ("pre", "post") else "1d"

    dm = DataManager(data_root=data_root)
    dm.save_symbol(symbol, out_bars, frequency=frequency, source="panda_data_fund")
    print(
        f"Saved {len(out_bars)} rows for {symbol} [{adjust}/{frequency}]: "
        f"{out_bars.index.min().date()} -> {out_bars.index.max().date()}"
    )


# Backward-compatible alias.
def download_csi300_etf(start_date, end_date, data_root=None, adjust="none") -> None:
    download_etf(DEFAULT_SYMBOL, start_date, end_date, data_root, adjust)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        default=DEFAULT_SYMBOL,
        help="Comma-separated fund symbols (default: SHSE.510300). "
             "Use 'all' to fetch the 18 large-asset ETF/LOF universe.",
    )
    parser.add_argument("--start-date", default="20180101")
    parser.add_argument("--end-date", default="20260805")
    parser.add_argument("--data-root", default=None)
    parser.add_argument(
        "--adjust",
        default="none",
        choices=["none", "pre", "post"],
        help="none=unadjusted, pre=forward-adjusted (local from cum_adj_factor), "
             "post=backward-adjusted (local from cum_adj_factor)",
    )
    parser.add_argument(
        "--frequency",
        default=None,
        help="Output frequency dir under data/market/ (default: 1d_adj when "
             "adjust in {pre,post}, else 1d). 1d_adj is still daily; the _adj "
             "suffix only marks adjustment-applied prices.",
    )
    args = parser.parse_args()

    if args.symbols.strip().lower() == "all":
        from strategies.cross_sectional.asset_class_rotation import ASSET_CLASS_ETF_UNIVERSE

        symbols = list(ASSET_CLASS_ETF_UNIVERSE.values())
    else:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    for symbol in symbols:
        download_etf(
            symbol=symbol,
            start_date=args.start_date,
            end_date=args.end_date,
            data_root=args.data_root,
            adjust=args.adjust,
            frequency=args.frequency,
        )


if __name__ == "__main__":
    main()
