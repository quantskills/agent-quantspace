"""Core-satellite mean-reversion rules for the cash-flow total-return index."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CashflowMeanReversionParams:
    """Parameters for a long-only core, oversold satellite, and risk window."""

    core_exposure: float = 1.0
    oversold_exposure: float = 1.5
    defensive_exposure: float = 0.0
    rsi_lookback: int = 14
    oversold_rsi: float = 35.0
    mean_exit_ma: int = 20
    trend_ma: int = 120
    trend_slope_lookback: int = 20
    oversold_take_profit: float = 0.07
    oversold_stop: float = 0.07
    oversold_max_hold: int = 10
    recovery_threshold: float = 0.03
    recovery_cooldown: int = 5
    overbought_lookback: int = 60
    overbought_distance: float = 0.13
    overbought_restore_drop: float = 0.05
    overbought_max_hold: int = 10

    def __post_init__(self) -> None:
        lookbacks = (
            self.rsi_lookback,
            self.mean_exit_ma,
            self.trend_ma,
            self.trend_slope_lookback,
            self.overbought_lookback,
        )
        if any(value <= 1 for value in lookbacks):
            raise ValueError("indicator lookbacks must be greater than 1")
        if not 0 <= self.defensive_exposure <= self.core_exposure:
            raise ValueError("defensive_exposure must be inside [0, core_exposure]")
        if not self.core_exposure <= self.oversold_exposure <= 1.5:
            raise ValueError("oversold_exposure must be inside [core_exposure, 1.5]")
        if not 0 < self.oversold_rsi < 100:
            raise ValueError("oversold_rsi must be inside (0, 100)")
        rates = (
            self.oversold_take_profit,
            self.oversold_stop,
            self.recovery_threshold,
            self.overbought_distance,
            self.overbought_restore_drop,
        )
        if any(not 0 < value < 1 for value in rates):
            raise ValueError("return thresholds must be inside (0, 1)")
        if self.oversold_max_hold <= 0 or self.overbought_max_hold <= 0:
            raise ValueError("maximum holding periods must be positive")
        if self.recovery_cooldown < 0:
            raise ValueError("recovery_cooldown must be non-negative")


def simple_rsi(close: pd.Series, lookback: int) -> pd.Series:
    """Return the simple-moving-average RSI used by the statistical study."""
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(lookback, min_periods=lookback).mean()
    loss = (-delta.clip(upper=0.0)).rolling(lookback, min_periods=lookback).mean()
    relative_strength = gain / loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + relative_strength)).fillna(50.0)


def cashflow_mean_reversion_signals(
    bars: pd.DataFrame,
    *,
    params: CashflowMeanReversionParams | None = None,
) -> pd.DataFrame:
    """Return indicators, state, events, and close-known target exposure.

    The core remains invested. An RSI first-crossing can add a satellite only
    while price is below a still-rising long moving average. The satellite is
    closed at a short moving-average recovery, take-profit, loss stop, or time
    limit. Its loss stop removes only the incremental exposure; recovery
    re-entry requires a cooldown and a rebound from the stopped close.

    A first crossing of the distance from the rolling low opens a temporary
    defensive window. This state has priority over the oversold satellite and
    ends after a configured pullback or time limit. All target changes use
    information known at the current close and require an execution lag in the
    backtester.
    """
    if "close" not in bars.columns:
        raise ValueError("bars must contain a close column")
    p = params or CashflowMeanReversionParams()
    close = pd.to_numeric(bars["close"], errors="coerce").astype(float).sort_index()
    if close.isna().any() or not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
        raise ValueError("close must contain finite positive values")

    rsi = simple_rsi(close, p.rsi_lookback)
    mean_ma = close.rolling(p.mean_exit_ma, min_periods=p.mean_exit_ma).mean()
    trend_ma = close.rolling(p.trend_ma, min_periods=p.trend_ma).mean()
    trend_rising = trend_ma > trend_ma.shift(p.trend_slope_lookback)
    distance_from_low = close.div(
        close.rolling(p.overbought_lookback, min_periods=p.overbought_lookback).min()
    ).sub(1.0)

    weights: list[float] = []
    states: list[str] = []
    events: list[str] = []
    oversold_active = False
    oversold_entry = np.nan
    oversold_started = -1
    recovery_wait = False
    stopped_price = np.nan
    stopped_at = -1
    defensive_active = False
    defensive_entry = np.nan
    defensive_started = -1
    prior_oversold_condition = False
    prior_defensive_condition = False

    for position, date in enumerate(close.index):
        price = float(close.loc[date])
        trend_ready = pd.notna(trend_ma.loc[date])
        favorable_pullback = bool(
            trend_ready
            and price < float(trend_ma.loc[date])
            and bool(trend_rising.loc[date])
        )
        oversold_condition = bool(rsi.loc[date] <= p.oversold_rsi and favorable_pullback)
        defensive_condition = bool(
            pd.notna(distance_from_low.loc[date])
            and distance_from_low.loc[date] >= p.overbought_distance
        )
        oversold_cross = oversold_condition and not prior_oversold_condition
        defensive_cross = defensive_condition and not prior_defensive_condition
        day_events: list[str] = []

        if defensive_active:
            held = position - defensive_started
            pullback = price <= defensive_entry * (1.0 - p.overbought_restore_drop)
            if pullback or held >= p.overbought_max_hold:
                defensive_active = False
                defensive_entry = np.nan
                defensive_started = -1
                day_events.append(
                    "defensive_exit_pullback" if pullback else "defensive_exit_time"
                )

        if oversold_active:
            held = position - oversold_started
            satellite_return = price / oversold_entry - 1.0
            recovered_to_mean = pd.notna(mean_ma.loc[date]) and price >= mean_ma.loc[date]
            exit_reason = ""
            if satellite_return >= p.oversold_take_profit:
                exit_reason = "take_profit"
            elif satellite_return <= -p.oversold_stop:
                exit_reason = "stop"
            elif held >= p.oversold_max_hold:
                exit_reason = "time"
            elif recovered_to_mean:
                exit_reason = "mean"
            if exit_reason:
                oversold_active = False
                oversold_entry = np.nan
                oversold_started = -1
                day_events.append(f"oversold_exit_{exit_reason}")
                if exit_reason == "stop":
                    recovery_wait = True
                    stopped_price = price
                    stopped_at = position

        if not defensive_active and defensive_cross:
            defensive_active = True
            defensive_entry = price
            defensive_started = position
            oversold_active = False
            oversold_entry = np.nan
            oversold_started = -1
            day_events.append("defensive_entry")
        elif not defensive_active and not oversold_active:
            if recovery_wait:
                cooldown_complete = position - stopped_at >= p.recovery_cooldown
                recovered = price >= stopped_price * (1.0 + p.recovery_threshold)
                if cooldown_complete and recovered and favorable_pullback:
                    oversold_active = True
                    oversold_entry = price
                    oversold_started = position
                    recovery_wait = False
                    stopped_price = np.nan
                    stopped_at = -1
                    day_events.append("oversold_reentry_recovery")
                elif not favorable_pullback:
                    recovery_wait = False
                    stopped_price = np.nan
                    stopped_at = -1
            elif oversold_cross:
                oversold_active = True
                oversold_entry = price
                oversold_started = position
                day_events.append("oversold_entry")

        if defensive_active:
            weight = p.defensive_exposure
            state = "defensive"
        elif oversold_active:
            weight = p.oversold_exposure
            state = "oversold_satellite"
        elif recovery_wait:
            weight = p.core_exposure
            state = "recovery_wait"
        else:
            weight = p.core_exposure
            state = "core"
        weights.append(float(weight))
        states.append(state)
        events.append("|".join(day_events))
        prior_oversold_condition = oversold_condition
        prior_defensive_condition = defensive_condition

    result = pd.DataFrame(
        {
            "close": close,
            "rsi": rsi,
            "mean_ma": mean_ma,
            "trend_ma": trend_ma,
            "trend_rising": trend_rising.fillna(False),
            "distance_from_low": distance_from_low,
            "state": states,
            "event": events,
            "target_exposure": weights,
        },
        index=close.index,
    )
    result.index.name = "eob"
    return result


def cashflow_mean_reversion_weights(
    bars: pd.DataFrame,
    *,
    symbol: str = "932365CNY010.CSI",
    params: CashflowMeanReversionParams | None = None,
) -> pd.DataFrame:
    """Return date-by-symbol target weights for the core-satellite rule."""
    signals = cashflow_mean_reversion_signals(bars, params=params)
    result = signals[["target_exposure"]].rename(columns={"target_exposure": symbol})
    result.index.name = "eob"
    return result


__all__ = [
    "CashflowMeanReversionParams",
    "cashflow_mean_reversion_signals",
    "cashflow_mean_reversion_weights",
    "simple_rsi",
]
