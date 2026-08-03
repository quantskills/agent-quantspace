"""Generate deterministic sample data for QuantSpace demos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from skills.store.data_manager import DataManager

ETF_SYMBOLS = ["SHSE.510300", "SHSE.510500", "SZSE.159915", "SHSE.513100"]
TS_SYMBOL = "SHSE.510300"


def _make_ohlcv(symbol: str, dates: pd.DatetimeIndex, seed: int, drift: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    shocks = rng.normal(loc=drift, scale=0.012, size=len(dates))
    close = 100.0 * np.exp(np.cumsum(shocks))
    open_ = close * (1.0 + rng.normal(0.0, 0.002, size=len(dates)))
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.001, 0.01, size=len(dates)))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.001, 0.01, size=len(dates)))
    volume = rng.integers(1_000_000, 5_000_000, size=len(dates))
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates.rename("eob"),
    )


def generate_sample_data(data_root: str | Path | None = None) -> Path:
    dm = DataManager(data_root=str(data_root) if data_root is not None else None)
    dates = pd.bdate_range("2022-01-03", periods=260)

    for i, symbol in enumerate(ETF_SYMBOLS):
        bars = _make_ohlcv(symbol, dates, seed=100 + i, drift=0.0002 + i * 0.00005)
        dm.save_symbol(symbol, bars, frequency="1d", source="synthetic_sample")

    return dm.root


if __name__ == "__main__":
    root = generate_sample_data()
    print(f"Sample data written to {root}")
