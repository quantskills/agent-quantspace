"""Causal multi-factor score and target-weight construction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from skills.strategy.cross_sectional.selection import top_n_weights

CombinationMethod = Literal["equal_rank", "equal_vote", "rolling_ic", "rolling_icir", "max_icir"]


@dataclass(frozen=True)
class FactorCombinationResult:
    factor_weights: pd.DataFrame
    composite_scores: pd.DataFrame
    target_weights: pd.DataFrame


@dataclass(frozen=True)
class DynamicFactorWeightConfig:
    """Causal rolling factor-weight estimation settings."""

    availability_delay: int
    lookback: int = 252
    min_periods: int = 126
    max_weight: float = 0.5
    correlation_shrinkage: float = 0.5

    def __post_init__(self) -> None:
        if self.availability_delay < 0:
            raise ValueError("availability_delay must be non-negative")
        if self.lookback <= 0:
            raise ValueError("lookback must be positive")
        if self.min_periods <= 0 or self.min_periods > self.lookback:
            raise ValueError("min_periods must be between 1 and lookback")
        if not 0.0 < self.max_weight <= 1.0:
            raise ValueError("max_weight must be in (0, 1]")
        if not 0.0 <= self.correlation_shrinkage <= 1.0:
            raise ValueError("correlation_shrinkage must be in [0, 1]")


def orient_factor_frames(
    factors: Mapping[str, pd.DataFrame], directions: Mapping[str, int]
) -> dict[str, pd.DataFrame]:
    """Orient every factor so a higher value means a more bullish forecast."""
    missing = set(factors).difference(directions)
    if missing:
        raise ValueError(f"missing directions for factors: {sorted(missing)}")
    invalid = {name: directions[name] for name in factors if directions[name] not in {-1, 1}}
    if invalid:
        raise ValueError(f"directions must be -1 or 1: {invalid}")
    return {name: frame * float(directions[name]) for name, frame in factors.items()}


def rank_factor_frames(factors: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Convert direction-corrected factor values to daily percentile ranks."""
    if not factors:
        raise ValueError("factors cannot be empty")
    return {
        name: frame.rank(axis=1, pct=True, method="average").replace([np.inf, -np.inf], np.nan)
        for name, frame in factors.items()
    }


def _cap_simplex(weights: np.ndarray, cap: float) -> np.ndarray:
    """Project non-negative scores to sum one with a deterministic upper cap."""
    n = weights.size
    if cap <= 0 or cap * n < 1.0 - 1e-12:
        raise ValueError("max_weight is infeasible")
    values = np.clip(np.nan_to_num(weights, nan=0.0), 0.0, None)
    if values.sum() <= 0:
        values = np.ones(n)
    values /= values.sum()
    fixed = np.zeros(n, dtype=bool)
    while np.any(values > cap + 1e-12):
        newly = (values > cap + 1e-12) & ~fixed
        values[newly] = cap
        fixed |= newly
        remaining = ~fixed
        residual = 1.0 - values[fixed].sum()
        if not remaining.any():
            break
        base = values[remaining]
        values[remaining] = residual * (
            base / base.sum() if base.sum() > 0 else 1.0 / remaining.sum()
        )
    return values / values.sum()


def _correlation_history_wide(
    correlation_history: pd.DataFrame,
    *,
    factor_names: list[str],
    dates: pd.Index,
    availability_delay: int,
) -> pd.DataFrame:
    required = {"eob", "factor_a", "factor_b", "correlation"}
    missing = required.difference(correlation_history.columns)
    if missing:
        raise ValueError(f"correlation_history missing columns: {sorted(missing)}")
    history = correlation_history.loc[:, list(required)].copy()
    history["eob"] = pd.to_datetime(history["eob"])
    known = set(factor_names)
    history = history[
        history["factor_a"].isin(known) & history["factor_b"].isin(known)
    ].copy()
    history["pair"] = list(zip(history["factor_a"], history["factor_b"]))
    if history.duplicated(["eob", "pair"]).any():
        raise ValueError("correlation_history contains duplicate date/pair rows")
    wide = history.pivot(index="eob", columns="pair", values="correlation")
    return wide.reindex(dates).shift(availability_delay)


def estimate_factor_weights(
    *,
    method: CombinationMethod,
    factor_names: Sequence[str],
    dates: pd.Index,
    ic_history: pd.DataFrame | None = None,
    correlation_history: pd.DataFrame | None = None,
    dynamic_config: DynamicFactorWeightConfig | None = None,
) -> pd.DataFrame:
    """Estimate factor-level weights without constructing asset weights."""
    names = list(factor_names)
    if not names:
        raise ValueError("factor_names cannot be empty")
    if len(set(names)) != len(names):
        raise ValueError("factor_names must be unique")
    if method in {"equal_rank", "equal_vote"}:
        return pd.DataFrame(1.0 / len(names), index=dates, columns=names)
    if ic_history is None:
        raise ValueError(f"{method} requires ic_history")
    if dynamic_config is None:
        raise ValueError(f"{method} requires dynamic_config")
    if dynamic_config.max_weight * len(names) < 1.0 - 1e-12:
        raise ValueError("max_weight is infeasible for the factor count")
    if method == "max_icir" and correlation_history is None:
        raise ValueError("max_icir requires correlation_history")

    available = (
        ic_history.reindex(index=dates, columns=names).shift(dynamic_config.availability_delay)
    )
    mean = available.rolling(
        dynamic_config.lookback, min_periods=dynamic_config.min_periods
    ).mean()
    std = available.rolling(
        dynamic_config.lookback, min_periods=dynamic_config.min_periods
    ).std(ddof=1)
    raw = mean if method == "rolling_ic" else mean.div(std.replace(0.0, np.nan))
    correlations = None
    if correlation_history is not None:
        correlations = _correlation_history_wide(
            correlation_history,
            factor_names=names,
            dates=dates,
            availability_delay=dynamic_config.availability_delay,
        )

    rows: list[np.ndarray] = []
    for date in raw.index:
        vector = raw.loc[date].to_numpy(dtype=float)
        if method == "max_icir":
            assert correlations is not None
            values = correlations.loc[date]
            corr = np.eye(len(names))
            enough = True
            for i, left in enumerate(names):
                for j, right in enumerate(names[i + 1 :], start=i + 1):
                    rho = values.get((left, right), values.get((right, left), np.nan))
                    if not np.isfinite(rho):
                        enough = False
                        break
                    corr[i, j] = corr[j, i] = float(rho)
                if not enough:
                    break
            if enough:
                shrinkage = dynamic_config.correlation_shrinkage
                corr = (1.0 - shrinkage) * corr + shrinkage * np.eye(len(names))
                try:
                    vector = np.linalg.solve(corr + np.eye(len(names)) * 1e-8, vector)
                except np.linalg.LinAlgError:
                    vector = np.zeros(len(names))
            else:
                vector = np.zeros(len(names))
        rows.append(
            _cap_simplex(np.clip(vector, 0.0, None), dynamic_config.max_weight)
        )
    return pd.DataFrame(rows, index=dates, columns=names)


def combine_factor_scores(
    ranked_factors: Mapping[str, pd.DataFrame],
    *,
    method: CombinationMethod,
    top_n: int = 3,
    ic_history: pd.DataFrame | None = None,
    correlation_history: pd.DataFrame | None = None,
    dynamic_config: DynamicFactorWeightConfig | None = None,
) -> FactorCombinationResult:
    """Combine factors, then select Top-N assets at equal asset weights."""
    if not ranked_factors:
        raise ValueError("ranked_factors cannot be empty")
    names = list(ranked_factors)
    first = ranked_factors[names[0]]
    frames = {name: frame.reindex_like(first) for name, frame in ranked_factors.items()}
    factor_weights = estimate_factor_weights(
        method=method,
        factor_names=names,
        dates=first.index,
        ic_history=ic_history,
        correlation_history=correlation_history,
        dynamic_config=dynamic_config,
    )

    if method == "equal_vote":
        votes = sum(
            (frame.rank(axis=1, ascending=False, method="first").le(top_n) & frame.notna()).astype(
                float
            )
            for frame in frames.values()
        )
        tie_break = sum(frames.values()) / float(len(names))
        composite = votes + tie_break.fillna(0.0) * 1e-3
    else:
        weighted = [frames[name].mul(factor_weights[name], axis=0) for name in names]
        numerator = sum(frame.fillna(0.0) for frame in weighted)
        denominator = sum(frames[name].notna().mul(factor_weights[name], axis=0) for name in names)
        composite = numerator.div(denominator.where(denominator > 0))
    targets = top_n_weights(composite, top_n=top_n)
    return FactorCombinationResult(factor_weights, composite, targets)


__all__ = [
    "CombinationMethod",
    "DynamicFactorWeightConfig",
    "FactorCombinationResult",
    "combine_factor_scores",
    "estimate_factor_weights",
    "orient_factor_frames",
    "rank_factor_frames",
]
