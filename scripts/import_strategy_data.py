"""Import PandaData bars used by strategy examples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.ingest import PandaDataClient  # noqa: E402
from skills.store.data_manager import DataManager  # noqa: E402

FUTURE_SYMBOLS = [
    "INE.SC99",
    "SHFE.AU99",
    "SHFE.AG99",
    "SHFE.CU99",
    "SHFE.RB99",
    "SHFE.AL99",
    "DCE.I99",
    "DCE.M99",
    "DCE.Y99",
    "CZCE.TA99",
    "CZCE.MA99",
    "CZCE.CF99",
    "CFFEX.IF99",
    "CFFEX.IC99",
    "CFFEX.IM99",
]

INDEX_SYMBOLS = [
    "SHSE.000001",
    "SHSE.000016",
    "SHSE.000300",
    "SHSE.000905",
    "SHSE.000852",
    "SZSE.399001",
    "SZSE.399006",
    "SZSE.399005",
]


def _year_chunks(start_date: str, end_date: str) -> list[tuple[str, str]]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if start > end:
        raise ValueError("start_date must be before or equal to end_date")

    chunks: list[tuple[str, str]] = []
    current = start
    while current <= end:
        year_end = min(pd.Timestamp(current.year, 12, 31), end)
        chunks.append((current.strftime("%Y%m%d"), year_end.strftime("%Y%m%d")))
        current = year_end + pd.Timedelta(days=1)
    return chunks


def _normalize_bars(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    frame = raw.drop_duplicates(subset=["date"]).copy()
    frame["eob"] = pd.to_datetime(frame["date"])
    for column in ["open", "high", "low", "close", "volume"]:
        if column not in frame.columns:
            frame[column] = 0.0
    return frame.set_index("eob")[["open", "high", "low", "close", "volume"]].sort_index().astype(float)


def _fetch_symbol(
    client: PandaDataClient,
    symbol: str,
    start_date: str,
    end_date: str,
    symbol_type: str,
) -> pd.DataFrame:
    parts = []
    for chunk_start, chunk_end in _year_chunks(start_date, end_date):
        data = client.fetch_market_data(symbol, chunk_start, chunk_end, type=symbol_type)
        if len(data):
            parts.append(data)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def _write_pool(dm: DataManager, pool_id: str, symbols: list[str], description: str) -> None:
    path = dm.root / "pools" / f"{pool_id}.json"
    payload = {
        "pool_id": pool_id,
        "description": description,
        "frequency": "1d",
        "symbols": symbols,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def import_strategy_data(
    start_date: str,
    end_date: str,
    data_root: str | Path | None = None,
    include_indexes: bool = True,
) -> None:
    dm = DataManager(data_root=str(data_root) if data_root is not None else None)
    client = PandaDataClient()

    imported_futures = []
    for symbol in FUTURE_SYMBOLS:
        bars = _normalize_bars(_fetch_symbol(client, symbol, start_date, end_date, "future"))
        if bars.empty:
            print(f"{symbol}: no data")
            continue
        dm.save_symbol(symbol, bars, frequency="1d", source="panda_data_future")
        imported_futures.append(symbol)
        print(f"{symbol}: {len(bars)} rows {bars.index.min().date()} -> {bars.index.max().date()}")
    _write_pool(
        dm,
        "future_trend",
        imported_futures,
        "PandaData dominant futures pool for public trend examples",
    )

    if not include_indexes:
        return

    imported_indexes = []
    for symbol in INDEX_SYMBOLS:
        bars = _normalize_bars(_fetch_symbol(client, symbol, start_date, end_date, "index"))
        if bars.empty:
            print(f"{symbol}: no data")
            continue
        dm.save_symbol(symbol, bars, frequency="1d", source="panda_data_index")
        imported_indexes.append(symbol)
        print(f"{symbol}: {len(bars)} rows {bars.index.min().date()} -> {bars.index.max().date()}")
    _write_pool(
        dm,
        "index_rotation",
        imported_indexes,
        "PandaData broad China index pool for public strategy examples",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20190101")
    parser.add_argument("--end-date", default="20260612")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--skip-indexes", action="store_true")
    args = parser.parse_args()

    import_strategy_data(
        start_date=args.start_date,
        end_date=args.end_date,
        data_root=args.data_root,
        include_indexes=not args.skip_indexes,
    )


if __name__ == "__main__":
    main()
