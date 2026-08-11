"""Download 2023 daily (post-adjusted) and minute bars for four dominant
continuous futures contracts: IF, RB, I, MA.

Symbols (QuantSpace dominant convention):
    CFFEX.IF99  -> IF   (CSI 300 index futures)
    SHFE.RB99   -> RB   (rebar)
    DCE.I99     -> I    (iron ore)
    CZCE.MA99   -> MA   (methanol)

Daily bars use PandaData's ``get_future_market_post`` (backward/后复权 across
contract rolls). Minute bars use ``get_market_min_data`` with the dominant
symbol. Both are saved under data/market with QuantSpace ``eob``-indexed schema.

Output frequencies:
    data/market/1d_adj/<SYMBOL>.parquet   (daily, post-adjusted)
    data/market/1m/<SYMBOL>.parquet       (minute)

Requires the optional PandaData SDK and credentials:
    uv sync --extra panda_data
    export PANDA_DATA_USERNAME=... PANDA_DATA_PASSWORD=...
"""

from __future__ import annotations

import argparse

import pandas as pd

from skills.ingest import PandaDataClient
from skills.store.data_manager import DataManager

# QuantSpace dominant-continuous symbols requested.
SYMBOLS = ["CFFEX.IF99", "SHFE.RB99", "DCE.I99", "CZCE.MA99"]

# panda_data native dominant symbols (used by get_future_market_post which
# does NOT auto-convert; must be passed in native <PRODUCT>_DOMINANT.<EX> form).
NATIVE_SYMBOLS = {
    "CFFEX.IF99": "IF_DOMINANT.CFE",
    "SHFE.RB99": "RB_DOMINANT.SHF",
    "DCE.I99": "I_DOMINANT.DCE",
    "CZCE.MA99": "MA_DOMINANT.CZC",
}

START_DATE = "20230101"
END_DATE = "20231231"
DAILY_FREQUENCY = "1d_adj"
MINUTE_FREQUENCY = "1m"


def _year_chunks(start: str, end: str) -> list[tuple[str, str]]:
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    chunks: list[tuple[str, str]] = []
    cur = s
    while cur <= e:
        nxt = min(cur + pd.DateOffset(years=1) - pd.Timedelta(days=1), e)
        chunks.append((cur.strftime("%Y%m%d"), nxt.strftime("%Y%m%d")))
        cur = nxt + pd.Timedelta(days=1)
    return chunks


def _month_chunks(start: str, end: str) -> list[tuple[str, str]]:
    """Finer chunks for minute data (large payloads)."""
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    chunks: list[tuple[str, str]] = []
    cur = s
    while cur <= e:
        nxt = min(cur + pd.offsets.MonthEnd(0), e)
        chunks.append((cur.strftime("%Y%m%d"), nxt.strftime("%Y%m%d")))
        cur = nxt + pd.Timedelta(days=1)
    return chunks


def _normalize_daily(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or len(raw) == 0:
        return pd.DataFrame()
    frame = raw.drop_duplicates(subset=["date", "symbol"]).copy()
    frame["eob"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("eob").sort_index()
    out = pd.DataFrame(index=frame.index)
    out["open"] = frame["open"].astype(float)
    out["high"] = frame["high"].astype(float)
    out["low"] = frame["low"].astype(float)
    out["close"] = frame["close"].astype(float)
    out["volume"] = frame["volume"].astype(float)
    out["open_interest"] = frame.get("open_interest", 0.0).astype(float)
    out["settlement"] = frame.get("settlement", frame["close"]).astype(float)
    out["dominant_id"] = frame.get("dominant_id")
    return out


def _normalize_minute(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or len(raw) == 0:
        return pd.DataFrame()
    frame = raw.drop_duplicates(subset=["date", "minute", "symbol"]).copy()
    ts = pd.to_datetime(frame["date"].astype(str) + " " + frame["minute"].astype(str).str.zfill(6))
    frame["eob"] = ts
    frame = frame.set_index("eob").sort_index()
    out = pd.DataFrame(index=frame.index)
    out["open"] = frame["open"].astype(float)
    out["high"] = frame["high"].astype(float)
    out["low"] = frame["low"].astype(float)
    out["close"] = frame["close"].astype(float)
    out["volume"] = frame["volume"].astype(float)
    out["amount"] = frame["amount"].astype(float) if "amount" in frame else 0.0
    out["open_interest"] = frame["open_interest"].astype(float) if "open_interest" in frame else 0.0
    out["dominant_id"] = frame["dominant_id"] if "dominant_id" in frame else None
    return out


def download_daily(client: PandaDataClient, dm: DataManager, symbols: list[str]) -> None:
    for symbol in symbols:
        native = NATIVE_SYMBOLS[symbol]
        parts: list[pd.DataFrame] = []
        for chunk_start, chunk_end in _year_chunks(START_DATE, END_DATE):
            raw = client._call(
                "get_future_market_post",
                symbol=[native],
                start_date=chunk_start,
                end_date=chunk_end,
                fields=[],
            )
            parts.append(_normalize_daily(raw))
            print(f"  [daily] {symbol} {chunk_start}~{chunk_end}: {len(raw)} rows")
        bars = pd.concat(parts).sort_index()
        bars = bars[~bars.index.duplicated(keep="last")]
        if bars.empty:
            print(f"[daily] {symbol}: no data returned")
            continue
        dm.save_symbol(symbol, bars, frequency=DAILY_FREQUENCY, source="panda_data_future_post")
        print(
            f"[daily] Saved {len(bars)} rows for {symbol} (post-adjusted): "
            f"{bars.index.min().date()} -> {bars.index.max().date()}, "
            f"distinct dominant contracts: {bars['dominant_id'].nunique()}"
        )


def download_minute(client: PandaDataClient, dm: DataManager, symbols: list[str]) -> None:
    for symbol in symbols:
        parts: list[pd.DataFrame] = []
        for chunk_start, chunk_end in _month_chunks(START_DATE, END_DATE):
            raw = client.fetch_market_min_data(
                symbol,
                chunk_start,
                chunk_end,
                symbol_type="future",
                frequency="1m",
            )
            parts.append(_normalize_minute(raw))
            print(f"  [minute] {symbol} {chunk_start}~{chunk_end}: {len(raw)} rows")
        bars = pd.concat(parts).sort_index()
        bars = bars[~bars.index.duplicated(keep="last")]
        if bars.empty:
            print(f"[minute] {symbol}: no data returned")
            continue
        dm.save_symbol(symbol, bars, frequency=MINUTE_FREQUENCY, source="panda_data_future_min")
        print(
            f"[minute] Saved {len(bars)} rows for {symbol} (1m): "
            f"{bars.index.min()} -> {bars.index.max()}, "
            f"distinct dominant contracts: {bars['dominant_id'].nunique()}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--only", choices=["daily", "minute", "all"], default="all")
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=SYMBOLS,
        help="QuantSpace dominant symbols; default all four.",
    )
    args = parser.parse_args()

    client = PandaDataClient()
    dm = DataManager(data_root=args.data_root)

    if args.only in {"daily", "all"}:
        download_daily(client, dm, args.symbols)
    if args.only in {"minute", "all"}:
        download_minute(client, dm, args.symbols)


if __name__ == "__main__":
    main()
