"""Volatility sizing with loss stops and recovery re-entry for 932365.CSI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

SizingFamily = Literal["target_vol", "vol_band", "hybrid"]


@dataclass(frozen=True)
class VolRecoveryParams:
    """Parameters for volatility-scaled long trend and recovery rules."""

    family: SizingFamily = "target_vol"
    trend_ma: int = 120
    breakout_lookback: int = 40
    fast_ma: int = 20
    slow_ma: int = 60
    trend_slope_lookback: int = 20
    volatility_lookback: int = 20
    target_volatility: float = 0.10
    regime_lookback: int = 252
    low_vol_quantile: float = 1.0 / 3.0
    high_vol_quantile: float = 2.0 / 3.0
    low_vol_exposure: float = 1.0
    mid_vol_exposure: float = 0.6
    high_vol_exposure: float = 0.3
    loss_stop: float = 0.08
    recovery_threshold: float = 0.03
    cooldown_bars: int = 5
    reduce_trigger: float = 0.04
    reduced_exposure_multiplier: float = 0.5

    def __post_init__(self) -> None:
        if self.family not in {"target_vol", "vol_band", "hybrid"}:
            raise ValueError("family must be target_vol, vol_band, or hybrid")
        lookbacks = (
            self.trend_ma,
            self.breakout_lookback,
            self.fast_ma,
            self.slow_ma,
            self.trend_slope_lookback,
            self.volatility_lookback,
            self.regime_lookback,
        )
        if any(value <= 1 for value in lookbacks):
            raise ValueError("all lookbacks must be greater than 1")
        if self.fast_ma >= self.slow_ma:
            raise ValueError("fast_ma must be less than slow_ma")
        if self.target_volatility <= 0:
            raise ValueError("target_volatility must be positive")
        if not 0 < self.low_vol_quantile < self.high_vol_quantile < 1:
            raise ValueError("volatility quantiles must be increasing inside (0, 1)")
        exposures = (
            self.low_vol_exposure,
            self.mid_vol_exposure,
            self.high_vol_exposure,
            self.reduced_exposure_multiplier,
        )
        if any(not 0 <= value <= 1 for value in exposures):
            raise ValueError("exposure values must be inside [0, 1]")
        if not 0 < self.loss_stop < 1:
            raise ValueError("loss_stop must be inside (0, 1)")
        if not 0 <= self.recovery_threshold < 1:
            raise ValueError("recovery_threshold must be inside [0, 1)")
        if self.cooldown_bars < 0:
            raise ValueError("cooldown_bars must be non-negative")
        if self.reduce_trigger <= 0:
            raise ValueError("reduce_trigger must be positive")
        if self.family == "hybrid" and self.reduce_trigger >= self.loss_stop:
            raise ValueError("hybrid reduce_trigger must be below loss_stop")


def realized_volatility(close: pd.Series, lookback: int) -> pd.Series:
    """Annualized rolling standard deviation of close-to-close log returns."""
    if lookback <= 1:
        raise ValueError("lookback must be greater than 1")
    values = pd.to_numeric(close, errors="coerce").astype(float)
    return np.log(values).diff().rolling(lookback, min_periods=lookback).std(ddof=1) * np.sqrt(
        252.0
    )


def volatility_exposure(close: pd.Series, params: VolRecoveryParams) -> pd.Series:
    """Return the base exposure implied by the selected volatility family."""
    vol = realized_volatility(close, params.volatility_lookback)
    if params.family in {"target_vol", "hybrid"}:
        return (params.target_volatility / vol).replace([np.inf, -np.inf], 1.0).clip(0.0, 1.0)

    prior_vol = vol.shift(1)
    low = prior_vol.rolling(
        params.regime_lookback, min_periods=params.regime_lookback
    ).quantile(params.low_vol_quantile)
    high = prior_vol.rolling(
        params.regime_lookback, min_periods=params.regime_lookback
    ).quantile(params.high_vol_quantile)
    exposure = pd.Series(np.nan, index=close.index, dtype=float)
    exposure.loc[vol <= low] = params.low_vol_exposure
    exposure.loc[(vol > low) & (vol <= high)] = params.mid_vol_exposure
    exposure.loc[vol > high] = params.high_vol_exposure
    return exposure


def cashflow_vol_recovery_weights(
    bars: pd.DataFrame,
    *,
    symbol: str = "932365.CSI",
    params: VolRecoveryParams | None = None,
) -> pd.DataFrame:
    """Create volatility-sized weights with loss-stop recovery state.

    Normal entry requires a rising long moving average, a close-channel
    breakout, and fast MA above slow MA. A position is stopped when its close
    falls ``loss_stop`` below entry. Re-entry after such a stop requires the
    cooldown to expire, price to recover above the stopped close by
    ``recovery_threshold``, and the trend regime to be positive. Hybrid sizing
    additionally cuts exposure after an unrealized loss and restores it with
    hysteresis after recovery.
    """
    if "close" not in bars.columns:
        raise ValueError("bars must contain a close column")
    p = params or VolRecoveryParams()
    close = pd.to_numeric(bars["close"], errors="coerce").astype(float).sort_index()
    if close.isna().any() or not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
        raise ValueError("close must contain finite positive values")

    fast = close.rolling(p.fast_ma, min_periods=p.fast_ma).mean()
    slow = close.rolling(p.slow_ma, min_periods=p.slow_ma).mean()
    trend = close.rolling(p.trend_ma, min_periods=p.trend_ma).mean()
    trend_rising = trend > trend.shift(p.trend_slope_lookback)
    prior_high = close.shift(1).rolling(
        p.breakout_lookback, min_periods=p.breakout_lookback
    ).max()
    base_exposure = volatility_exposure(close, p)

    weights: list[float] = []
    in_position = False
    entry_price = np.nan
    risk_reduced = False
    stopped_out = False
    stopped_price = np.nan
    stopped_at = -1

    for position, date in enumerate(close.index):
        price = float(close.loc[date])
        ready = not any(
            pd.isna(value)
            for value in (
                fast.loc[date],
                slow.loc[date],
                trend.loc[date],
                prior_high.loc[date],
                base_exposure.loc[date],
            )
        )
        if not ready:
            weights.append(0.0)
            continue

        positive_regime = (
            price > float(trend.loc[date])
            and bool(trend_rising.loc[date])
            and float(fast.loc[date]) > float(slow.loc[date])
        )

        if in_position:
            position_return = price / entry_price - 1.0
            if position_return <= -p.loss_stop:
                in_position = False
                entry_price = np.nan
                risk_reduced = False
                stopped_out = True
                stopped_price = price
                stopped_at = position
            elif not positive_regime:
                in_position = False
                entry_price = np.nan
                risk_reduced = False
                stopped_out = False
                stopped_price = np.nan
                stopped_at = -1
            elif p.family == "hybrid":
                if not risk_reduced and position_return <= -p.reduce_trigger:
                    risk_reduced = True
                elif risk_reduced and position_return >= -(p.reduce_trigger / 2.0):
                    risk_reduced = False
        else:
            if stopped_out:
                cooldown_complete = position - stopped_at >= p.cooldown_bars
                recovered = price >= stopped_price * (1.0 + p.recovery_threshold)
                should_enter = cooldown_complete and recovered and positive_regime
            else:
                should_enter = positive_regime and price > float(prior_high.loc[date])
            if should_enter:
                in_position = True
                entry_price = price
                risk_reduced = False
                stopped_out = False
                stopped_price = np.nan
                stopped_at = -1

        if in_position:
            multiplier = p.reduced_exposure_multiplier if risk_reduced else 1.0
            weights.append(float(base_exposure.loc[date]) * multiplier)
        else:
            weights.append(0.0)

    result = pd.DataFrame({symbol: weights}, index=close.index)
    result.index.name = "eob"
    return result


__all__ = [
    "SizingFamily",
    "VolRecoveryParams",
    "cashflow_vol_recovery_weights",
    "realized_volatility",
    "volatility_exposure",
]
