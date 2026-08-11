"""Close-only trend-breakout rules for the CSI All Share Free Cash Flow Index.

The index's pre-launch backfill contains official close levels but no usable
open/high/low history.  This strategy therefore uses prior closing highs/lows
for channels and a Wilder-smoothed absolute close change as an explicit ATR
proxy.  It never fabricates historical intraday ranges.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CashflowTrendParams:
    """Parameter bundle for the close-only long trend strategy."""

    trend_ma: int = 120
    breakout_lookback: int = 20
    fast_ma: int = 20
    slow_ma: int = 60
    atr_lookback: int = 14
    initial_stop_atr: float = 2.5
    trailing_stop_atr: float = 3.0
    exit_lookback: int = 20
    target_volatility: float = 0.10
    trend_slope_lookback: int = 20
    volatility_lookback: int = 20

    def __post_init__(self) -> None:
        integer_fields = (
            self.trend_ma,
            self.breakout_lookback,
            self.fast_ma,
            self.slow_ma,
            self.atr_lookback,
            self.exit_lookback,
            self.trend_slope_lookback,
            self.volatility_lookback,
        )
        if any(value <= 1 for value in integer_fields):
            raise ValueError("all lookbacks must be greater than 1")
        if self.fast_ma >= self.slow_ma:
            raise ValueError("fast_ma must be less than slow_ma")
        if self.initial_stop_atr <= 0 or self.trailing_stop_atr <= 0:
            raise ValueError("ATR stop multipliers must be positive")
        if self.target_volatility <= 0:
            raise ValueError("target_volatility must be positive")


def close_atr_proxy(close: pd.Series, lookback: int = 14) -> pd.Series:
    """Return Wilder-smoothed absolute close changes as a close-only ATR proxy."""
    if lookback <= 1:
        raise ValueError("lookback must be greater than 1")
    values = pd.to_numeric(close, errors="coerce").astype(float)
    return values.diff().abs().ewm(
        alpha=1.0 / lookback,
        adjust=False,
        min_periods=lookback,
    ).mean()


def cashflow_trend_weights(
    bars: pd.DataFrame,
    *,
    symbol: str = "932365.CSI",
    params: CashflowTrendParams | None = None,
) -> pd.DataFrame:
    """Create date x symbol target weights from close-only trend rules.

    Entry requires a rising long moving average, a prior-close channel
    breakout, and a bullish fast/slow moving-average relationship.  Exits use
    the tighter of an initial/trailing ATR-proxy stop, a prior-close channel
    low, or loss of the long moving-average regime.  Exposure is capped at one
    and scaled to the requested annualized volatility target.
    """
    if "close" not in bars.columns:
        raise ValueError("bars must contain a close column")
    p = params or CashflowTrendParams()
    close = pd.to_numeric(bars["close"], errors="coerce").astype(float).sort_index()
    if close.isna().any() or (close <= 0).any():
        raise ValueError("close must contain finite positive values")

    fast = close.rolling(p.fast_ma, min_periods=p.fast_ma).mean()
    slow = close.rolling(p.slow_ma, min_periods=p.slow_ma).mean()
    trend = close.rolling(p.trend_ma, min_periods=p.trend_ma).mean()
    trend_rising = trend > trend.shift(p.trend_slope_lookback)
    prior_high = close.shift(1).rolling(
        p.breakout_lookback, min_periods=p.breakout_lookback
    ).max()
    prior_low = close.shift(1).rolling(
        p.exit_lookback, min_periods=p.exit_lookback
    ).min()
    atr = close_atr_proxy(close, p.atr_lookback)
    realized_vol = (
        np.log(close)
        .diff()
        .rolling(p.volatility_lookback, min_periods=p.volatility_lookback)
        .std(ddof=1)
        * np.sqrt(252.0)
    )
    exposure = (p.target_volatility / realized_vol).clip(lower=0.0, upper=1.0)

    weights: list[float] = []
    in_position = False
    high_water = np.nan
    stop_level = np.nan

    for date in close.index:
        price = float(close.loc[date])
        current_atr = atr.loc[date]
        ready = not any(
            pd.isna(value)
            for value in (
                fast.loc[date],
                slow.loc[date],
                trend.loc[date],
                prior_high.loc[date],
                prior_low.loc[date],
                current_atr,
                exposure.loc[date],
            )
        )

        if not ready:
            weights.append(0.0)
            continue

        if in_position:
            high_water = max(high_water, price)
            stop_level = max(
                stop_level,
                high_water - p.trailing_stop_atr * float(current_atr),
            )
            should_exit = (
                price <= stop_level
                or price <= float(prior_low.loc[date])
                or price < float(trend.loc[date])
            )
            if should_exit:
                in_position = False
                high_water = np.nan
                stop_level = np.nan
        else:
            should_enter = (
                price > float(trend.loc[date])
                and bool(trend_rising.loc[date])
                and price > float(prior_high.loc[date])
                and float(fast.loc[date]) > float(slow.loc[date])
            )
            if should_enter:
                in_position = True
                high_water = price
                stop_level = price - p.initial_stop_atr * float(current_atr)

        weights.append(float(exposure.loc[date]) if in_position else 0.0)

    result = pd.DataFrame({symbol: weights}, index=close.index)
    result.index.name = "eob"
    return result


__all__ = ["CashflowTrendParams", "cashflow_trend_weights", "close_atr_proxy"]
