"""Horizon/Lagged IC and cross-sectional factor redundancy diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from skills.analyze.factor_evaluation import newey_west_mean_tstat


@dataclass(frozen=True)
class ICInformationResult:
    """Summary statistics and signal-date-labelled daily IC observations."""

    summary: pd.DataFrame
    daily_ic: pd.DataFrame


def execution_forward_return_wide(
    prices: pd.DataFrame,
    *,
    horizon: int,
    lag: int = 0,
    signal_lag: int = 1,
) -> pd.DataFrame:
    """Return ``P[t+signal_lag+lag+horizon]/P[t+signal_lag+lag]-1``.

    Both endpoints must exist.  The returned frame is labelled at signal date
    ``t``, which makes the execution convention explicit and testable.
    """
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    if lag < 0 or signal_lag < 0:
        raise ValueError("lag and signal_lag must be non-negative")
    start_offset = signal_lag + lag
    start = prices.shift(-start_offset)
    end = prices.shift(-(start_offset + horizon))
    return end.div(start).sub(1.0).where(start.notna() & end.notna())


def rank_ic_series(
    factor: pd.DataFrame,
    forward_return: pd.DataFrame,
    *,
    min_cross_section: int = 6,
) -> pd.Series:
    """Daily cross-sectional Spearman IC for two date-by-symbol frames."""
    common_dates = factor.index.intersection(forward_return.index)
    common_symbols = factor.columns.intersection(forward_return.columns)
    x = factor.loc[common_dates, common_symbols].replace([np.inf, -np.inf], np.nan)
    y = forward_return.loc[common_dates, common_symbols].replace([np.inf, -np.inf], np.nan)
    valid = x.notna() & y.notna()
    xr = x.where(valid).rank(axis=1, method="average")
    yr = y.where(valid).rank(axis=1, method="average")
    ic = xr.corrwith(yr, axis=1).where(valid.sum(axis=1) >= min_cross_section)
    ic.name = "IC"
    return ic.dropna()


def summarize_ic_series(ic: pd.Series, *, hac_lag: int) -> dict[str, float | int]:
    """Mean, ICIR, Newey-West inference, confidence interval and count."""
    clean = ic.replace([np.inf, -np.inf], np.nan).dropna()
    count = int(clean.size)
    mean = float(clean.mean()) if count else np.nan
    std = float(clean.std(ddof=1)) if count > 1 else np.nan
    icir = mean / std if np.isfinite(std) and std > 0 else np.nan
    t_stat, se, p_value = newey_west_mean_tstat(clean, lag=hac_lag)
    half_width = 1.96 * se if np.isfinite(se) else np.nan
    return {
        "ic_mean": mean,
        "ic_std": std,
        "icir": icir,
        "hac_t": t_stat,
        "hac_se": se,
        "hac_p": p_value,
        "ci_low": mean - half_width if np.isfinite(half_width) else np.nan,
        "ci_high": mean + half_width if np.isfinite(half_width) else np.nan,
        "effective_dates": count,
    }


def compute_ic_information_surface(
    factors: Mapping[str, pd.DataFrame],
    prices: pd.DataFrame,
    *,
    horizons: Sequence[int],
    lags: Sequence[int],
    signal_lag: int = 1,
    segments: Mapping[str, tuple[str | None, str | None]] | None = None,
    min_cross_section: int = 6,
) -> ICInformationResult:
    """Compute the complete factor × horizon × lag IC information surface.

    Returns a summary table and a tidy daily-IC table.  HAC lag is ``H-1`` to
    account for overlapping H-day forward returns.
    """
    if not factors:
        raise ValueError("factors cannot be empty")
    if signal_lag < 0:
        raise ValueError("signal_lag must be non-negative")
    if min_cross_section <= 0:
        raise ValueError("min_cross_section must be positive")
    horizon_values = [int(value) for value in horizons]
    lag_values = [int(value) for value in lags]
    if not horizon_values or any(value <= 0 for value in horizon_values):
        raise ValueError("horizons must contain positive integers")
    if not lag_values or any(value < 0 for value in lag_values):
        raise ValueError("lags must contain non-negative integers")
    if len(set(horizon_values)) != len(horizon_values):
        raise ValueError("horizons must be unique")
    if len(set(lag_values)) != len(lag_values):
        raise ValueError("lags must be unique")

    segment_map = segments or {"full": (None, None)}
    for segment, (start, end) in segment_map.items():
        if not segment:
            raise ValueError("segment names cannot be empty")
        if start is not None and end is not None and pd.Timestamp(start) > pd.Timestamp(end):
            raise ValueError(f"segment {segment!r} has start after end")
    summaries: list[dict[str, object]] = []
    daily_rows: list[pd.DataFrame] = []
    for horizon in horizon_values:
        for lag in lag_values:
            future = execution_forward_return_wide(
                prices, horizon=horizon, lag=lag, signal_lag=signal_lag
            )
            for factor_name, factor in factors.items():
                ic = rank_ic_series(factor, future, min_cross_section=min_cross_section)
                daily = ic.rename("ic").to_frame().reset_index(names="eob")
                daily.insert(0, "lag", lag)
                daily.insert(0, "horizon", horizon)
                daily.insert(0, "factor", factor_name)
                daily_rows.append(daily)
                for segment, (start, end) in segment_map.items():
                    sliced = ic
                    if start is not None:
                        sliced = sliced.loc[sliced.index >= pd.Timestamp(start)]
                    if end is not None:
                        sliced = sliced.loc[sliced.index <= pd.Timestamp(end)]
                    row: dict[str, object] = {
                        "factor": factor_name,
                        "segment": segment,
                        "horizon": horizon,
                        "lag": lag,
                    }
                    row.update(summarize_ic_series(sliced, hac_lag=horizon - 1))
                    summaries.append(row)
    summary = pd.DataFrame(summaries).sort_values(["factor", "segment", "horizon", "lag"])
    daily_ic = pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame()
    return ICInformationResult(summary.reset_index(drop=True), daily_ic)


def compute_horizon_ic(
    factors: Mapping[str, pd.DataFrame],
    prices: pd.DataFrame,
    *,
    horizons: Sequence[int],
    signal_lag: int = 1,
    segments: Mapping[str, tuple[str | None, str | None]] | None = None,
    min_cross_section: int = 6,
) -> ICInformationResult:
    """Compute Horizon IC by fixing signal-use lag at zero."""
    return compute_ic_information_surface(
        factors,
        prices,
        horizons=horizons,
        lags=[0],
        signal_lag=signal_lag,
        segments=segments,
        min_cross_section=min_cross_section,
    )


def compute_lagged_ic(
    factors: Mapping[str, pd.DataFrame],
    prices: pd.DataFrame,
    *,
    horizons: Sequence[int],
    lags: Sequence[int],
    signal_lag: int = 1,
    segments: Mapping[str, tuple[str | None, str | None]] | None = None,
    min_cross_section: int = 6,
) -> ICInformationResult:
    """Compute signal-delay decay curves for one or more return horizons."""
    return compute_ic_information_surface(
        factors,
        prices,
        horizons=horizons,
        lags=lags,
        signal_lag=signal_lag,
        segments=segments,
        min_cross_section=min_cross_section,
    )


def mean_daily_factor_rank_correlation(
    factors: Mapping[str, pd.DataFrame],
    *,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Average daily Spearman correlations across direction-corrected factors."""
    names = list(factors)
    out = pd.DataFrame(np.eye(len(names)), index=names, columns=names, dtype=float)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            a, b = factors[left].align(factors[right], join="inner", axis=None)
            if start is not None:
                a, b = a.loc[a.index >= pd.Timestamp(start)], b.loc[b.index >= pd.Timestamp(start)]
            if end is not None:
                a, b = a.loc[a.index <= pd.Timestamp(end)], b.loc[b.index <= pd.Timestamp(end)]
            daily = a.rank(axis=1).corrwith(b.rank(axis=1), axis=1)
            value = float(daily.mean())
            out.loc[left, right] = value
            out.loc[right, left] = value
    return out


def rolling_factor_rank_correlation(
    factors: Mapping[str, pd.DataFrame], *, window: int = 252, min_periods: int = 126
) -> pd.DataFrame:
    """Tidy rolling mean of daily cross-sectional Spearman correlations."""
    if window <= 0:
        raise ValueError("window must be positive")
    if min_periods <= 0 or min_periods > window:
        raise ValueError("min_periods must be between 1 and window")
    rows: list[pd.DataFrame] = []
    names = list(factors)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            a, b = factors[left].align(factors[right], join="inner", axis=None)
            daily = a.rank(axis=1).corrwith(b.rank(axis=1), axis=1)
            rolling = daily.rolling(window, min_periods=min_periods).mean()
            frame = rolling.rename("correlation").to_frame().reset_index(names="eob")
            frame.insert(0, "factor_b", right)
            frame.insert(0, "factor_a", left)
            rows.append(frame)
    if rows:
        return pd.concat(rows, ignore_index=True)
    return pd.DataFrame(columns=["factor_a", "factor_b", "eob", "correlation"])


def top_n_jaccard_overlap(factors: Mapping[str, pd.DataFrame], *, top_n: int = 3) -> pd.DataFrame:
    """Mean daily Jaccard overlap between each pair's Top-N selections."""
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    names = list(factors)
    selections = {
        name: frame.rank(axis=1, ascending=False, method="first").le(top_n) & frame.notna()
        for name, frame in factors.items()
    }
    out = pd.DataFrame(np.eye(len(names)), index=names, columns=names, dtype=float)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            a, b = selections[left].align(selections[right], join="inner", axis=None)
            union = (a | b).sum(axis=1)
            overlap = (a & b).sum(axis=1).div(union.where(union > 0))
            value = float(overlap.mean())
            out.loc[left, right] = value
            out.loc[right, left] = value
    return out


def factor_rank_autocorrelation(factor: pd.DataFrame, *, periods: Sequence[int]) -> pd.Series:
    """Mean cross-sectional Spearman rank autocorrelation for each lag."""
    ranked = factor.rank(axis=1)
    return pd.Series(
        {
            int(period): float(ranked.corrwith(ranked.shift(int(period)), axis=1).mean())
            for period in periods
        },
        name="rank_autocorrelation",
    )


__all__ = [
    "ICInformationResult",
    "compute_horizon_ic",
    "compute_ic_information_surface",
    "compute_lagged_ic",
    "execution_forward_return_wide",
    "factor_rank_autocorrelation",
    "mean_daily_factor_rank_correlation",
    "rank_ic_series",
    "rolling_factor_rank_correlation",
    "summarize_ic_series",
    "top_n_jaccard_overlap",
]
