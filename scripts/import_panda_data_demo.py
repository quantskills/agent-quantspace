"""Fetch one PandaData daily series and save it with DataManager."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.ingest import PandaDataClient  # noqa: E402
from skills.store.data_manager import DataManager  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="SHSE.600000")
    parser.add_argument("--start-date", default="20230101")
    parser.add_argument("--end-date", default="20231231")
    parser.add_argument("--frequency", default="1d")
    args = parser.parse_args()

    raw = PandaDataClient().fetch_market_data(
        args.symbol,
        args.start_date,
        args.end_date,
        type="stock",
    )
    bars = raw.copy()
    bars["eob"] = pd.to_datetime(bars["date"])
    bars = bars.set_index("eob")[["open", "high", "low", "close", "volume"]].sort_index()
    DataManager().save_symbol(args.symbol, bars, frequency=args.frequency, source="panda_data")
    print(f"Saved {len(bars)} rows for {args.symbol}")


if __name__ == "__main__":
    main()
