"""Close-channel Donchian breakout with close-only ATR-proxy stops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from strategies.time_series.cashflow_trend import close_atr_proxy

SizingMode = Literal["fixed", "target_vol"]


@dataclass(frozen=True)
class DonchianAtrParams:
    """Parameters for long-only Donchian breakout and trailing stops."""

    entry_lookback: int = 55
    exit_lookback: int = 20
    atr_lookback: int = 20
    atr_multiplier: float = 3.0
    sizing: SizingMode = "fixed"
    target_volatility: float = 0.10
    volatility_lookback: int = 20

    def __post_init__(self) -> None:
        if self.entry_lookback <= 1 or self.exit_lookback <= 1:
            raise ValueError("channel lookbacks must be greater than 1")
        if self.entry_lookback <= self.exit_lookback:
            raise ValueError("entry_lookback must be greater than exit_lookback")
        if self.atr_lookback <= 1 or self.volatility_lookback <= 1:
            raise ValueError("volatility lookbacks must be greater than 1")
        if self.atr_multiplier <= 0 or self.target_volatility <= 0:
            raise ValueError("ATR multiplier and target volatility must be positive")
        if self.sizing not in {"fixed", "target_vol"}:
            raise ValueError("sizing must be fixed or target_vol")


def donchian_atr_weights(
    bars: pd.DataFrame,
    *,
    symbol: str = "932365.CSI",
    params: DonchianAtrParams | None = None,
) -> pd.DataFrame:
    """Create long weights from prior-close channels and ATR-proxy stops.

    A close above the prior entry channel opens a position. Exit occurs at the
    prior closing-low channel or the tighter of the initial and trailing
    ATR-proxy stops. Historical highs/lows are not used because the index's
    official pre-launch backfill contains only valid close levels.
    """
    if "close" not in bars.columns:
        raise ValueError("bars must contain a close column")
    p = params or DonchianAtrParams()
    close = pd.to_numeric(bars["close"], errors="coerce").astype(float).sort_index()
    if close.isna().any() or not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
        raise ValueError("close must contain finite positive values")

    upper = close.shift(1).rolling(
        p.entry_lookback, min_periods=p.entry_lookback
    ).max()
    lower = close.shift(1).rolling(
        p.exit_lookback, min_periods=p.exit_lookback
    ).min()
    atr = close_atr_proxy(close, p.atr_lookback)
    if p.sizing == "fixed":
        exposure = pd.Series(1.0, index=close.index)
    else:
        realized_vol = (
            np.log(close)
            .diff()
            .rolling(p.volatility_lookback, min_periods=p.volatility_lookback)
            .std(ddof=1)
            * np.sqrt(252.0)
        )
        exposure = (
            (p.target_volatility / realized_vol)
            .replace([np.inf, -np.inf], 1.0)
            .clip(0.0, 1.0)
        )

    weights: list[float] = []
    in_position = False
    high_water = np.nan
    stop_level = np.nan

    for date in close.index:
        price = float(close.loc[date])
        ready = not any(
            pd.isna(value)
            for value in (upper.loc[date], lower.loc[date], atr.loc[date], exposure.loc[date])
        )
        if not ready:
            weights.append(0.0)
            continue

        if in_position:
            high_water = max(high_water, price)
            stop_level = max(
                stop_level,
                high_water - p.atr_multiplier * float(atr.loc[date]),
            )
            if price <= stop_level or price <= float(lower.loc[date]):
                in_position = False
                high_water = np.nan
                stop_level = np.nan
        elif price > float(upper.loc[date]):
            in_position = True
            high_water = price
            stop_level = price - p.atr_multiplier * float(atr.loc[date])

        weights.append(float(exposure.loc[date]) if in_position else 0.0)

    result = pd.DataFrame({symbol: weights}, index=close.index)
    result.index.name = "eob"
    return result


__all__ = ["DonchianAtrParams", "SizingMode", "donchian_atr_weights"]
