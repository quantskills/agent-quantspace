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


def write_symbol_parquet(
    root: Path, symbol: str, bars: pd.DataFrame, frequency: str = "1d"
) -> Path:
    path = root / "market" / frequency / f"{symbol}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    bars.to_parquet(path)
    return path


def write_strategy_report_data(root: Path, symbols: list[str], periods: int = 2100) -> Path:
    """Write deterministic, non-private daily bars spanning report train/test dates."""
    dates = pd.bdate_range("2018-01-02", periods=periods, name="eob")
    time = np.arange(periods, dtype=float)
    for offset, symbol in enumerate(sorted(set(symbols))):
        rng = np.random.default_rng(10_000 + offset)
        cycle = 0.0008 * np.sin(time / (18.0 + offset % 7))
        shocks = rng.normal(0.00005 + offset * 0.000002, 0.012, periods) + cycle
        close = 100.0 * np.exp(np.cumsum(shocks))
        open_ = close * (1.0 + rng.normal(0.0, 0.002, periods))
        spread = rng.uniform(0.002, 0.015, periods)
        bars = pd.DataFrame(
            {
                "open": open_,
                "high": np.maximum(open_, close) * (1.0 + spread),
                "low": np.minimum(open_, close) * (1.0 - spread),
                "close": close,
                "volume": rng.integers(500_000, 5_000_000, periods).astype(float),
            },
            index=dates,
        )
        write_symbol_parquet(root, symbol, bars)
    return root
