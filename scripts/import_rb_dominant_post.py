"""Download RB (rebar) dominant continuous contract with post-adjustment.

Futures dominant/continuous contracts (e.g. ``RB_DOMINANT.SHF`` -> ``SHFE.RB99``)
need *backward* adjustment to splice across contract rolls, which is provided by
PandaData's ``get_future_market_post`` interface. This is the standard way to
"复权" a futures continuous contract (not the stock adj-factor path).

Output parquet schema (per QuantSpace convention, eob-indexed):
    open, high, low, close, volume, open_interest, settlement, dominant_id
"""

from __future__ import annotations

import argparse

import pandas as pd

from skills.ingest import PandaDataClient
from skills.store.data_manager import DataManager

RAW_SYMBOL = "RB_DOMINANT.SHF"
STORE_SYMBOL = "SHFE.RB99"
FREQUENCY = "1d_adj"


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


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
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


def download(
    start_date: str,
    end_date: str,
    data_root: str | None = None,
) -> None:
    client = PandaDataClient()
    parts: list[pd.DataFrame] = []
    for chunk_start, chunk_end in _year_chunks(start_date, end_date):
        raw = client._call(
            "get_future_market_post",
            symbol=[RAW_SYMBOL],
            start_date=chunk_start,
            end_date=chunk_end,
            fields=[],
        )
        parts.append(_normalize(raw))
        print(f"  chunk {chunk_start}~{chunk_end}: {len(raw)} rows")

    bars = pd.concat(parts).sort_index()
    bars = bars[~bars.index.duplicated(keep="last")]
    if bars.empty:
        print(f"{STORE_SYMBOL}: no data returned")
        return

    dm = DataManager(data_root=data_root)
    dm.save_symbol(STORE_SYMBOL, bars, frequency=FREQUENCY, source="panda_data_future_post")
    print(
        f"Saved {len(bars)} rows for {STORE_SYMBOL} (post-adjusted): "
        f"{bars.index.min().date()} -> {bars.index.max().date()}"
    )
    print(f"distinct dominant contracts: {bars['dominant_id'].nunique()}")
    print(bars.tail(3).to_string())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20190101")
    parser.add_argument("--end-date", default="20260630")
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args()
    download(args.start_date, args.end_date, args.data_root)


if __name__ == "__main__":
    main()
