from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def make_ohlcv(
    prices: list[float] | np.ndarray | None = None,
    *,
    start: str = "2024-01-01",
    symbol: str | None = None,
) -> pd.DataFrame:
    values = prices if prices is not None else np.linspace(100.0, 110.0, 40)
    close = pd.Series(
        values,
        index=pd.date_range(start, periods=len(values), name="eob"),
        dtype=float,
    )
    bars = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1000.0,
        },
        index=close.index,
    )
    if symbol is not None:
        return bars.assign(symbol=symbol).reset_index().set_index(["symbol", "eob"])
    return bars


def make_panel(symbols: tuple[str, ...] = ("AAA", "BBB", "CCC"), periods: int = 80) -> pd.DataFrame:
    frames = []
    for i, symbol in enumerate(symbols):
        prices = 100.0 + i * 5.0 + np.linspace(0.0, 8.0 + i, periods)
        frames.append(make_ohlcv(prices, symbol=symbol))
    return pd.concat(frames).sort_index()


def write_symbol_parquet(root: Path, symbol: str, bars: pd.DataFrame, frequency: str = "1d") -> Path:
    path = root / "market" / frequency / f"{symbol}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    bars.to_parquet(path)
    return path
