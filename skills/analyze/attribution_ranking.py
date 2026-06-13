"""Ranking-signal attribution helpers for cross-sectional rotation strategies."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from skills.analyze.attribution_counterfactual import performance_metrics


def ranking_bucket_attribution(
    scores: pd.DataFrame,
    daily_returns: pd.DataFrame,
    top_k: int = 4,
    windows: Sequence[int] = (1, 5, 20),
    strategy_id: str = "default",
) -> pd.DataFrame:
    """Measure forward returns for top/next/rest/universe rank buckets."""
    score = _wide_numeric(scores, "scores")
    returns = _wide_numeric(daily_returns, "daily_returns")
    score, returns = _align_wide_frames(score, returns)
    top_k = _positive_int(top_k, "top_k")
    ranks = score.rank(axis=1, ascending=False, method="first")
    eligible = score.notna()

    rows: list[dict[str, Any]] = []
    for window in windows:
        window = _positive_int(window, "window")
        forward = _forward_return_wide(returns, window)
        for date in score.index:
            day_ranks = ranks.loc[date]
            day_eligible = eligible.loc[date] & forward.loc[date].notna()
            bucket_masks = {
                "top": day_eligible & day_ranks.le(top_k),
                "next": day_eligible & day_ranks.gt(top_k) & day_ranks.le(top_k * 2),
                "rest": day_eligible & day_ranks.gt(top_k),
                "universe": day_eligible,
            }
            for bucket, mask in bucket_masks.items():
                values = forward.loc[date, mask]
                rows.append(
                    {
                        "date": date,
                        "strategy_id": strategy_id,
                        "top_k": top_k,
                        "window": window,
                        "bucket": bucket,
                        "n_symbols": int(mask.sum()),
                        "avg_forward_return": float(values.mean()) if not values.empty else np.nan,
                    }
                )
    return pd.DataFrame(rows)


def summarize_ranking_buckets(bucket_returns: pd.DataFrame) -> pd.DataFrame:
    """Summarize rank bucket forward-return edge by horizon."""
    if bucket_returns.empty:
        return pd.DataFrame()
    required = {"date", "strategy_id", "top_k", "window", "bucket", "avg_forward_return"}
    missing = required.difference(bucket_returns.columns)
    if missing:
        raise ValueError(f"bucket_returns missing columns: {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    group_cols = ["strategy_id", "top_k", "window"]
    for keys, group in bucket_returns.groupby(group_cols, sort=True):
        strategy_id, top_k, window = keys
        pivot = group.pivot_table(
            index="date",
            columns="bucket",
            values="avg_forward_return",
            aggfunc="last",
        )
        top = pivot.get("top", pd.Series(index=pivot.index, dtype=float))
        next_bucket = pivot.get("next", pd.Series(index=pivot.index, dtype=float))
        rest = pivot.get("rest", pd.Series(index=pivot.index, dtype=float))
        universe = pivot.get("universe", pd.Series(index=pivot.index, dtype=float))
        rows.append(
            {
                "strategy_id": strategy_id,
                "top_k": int(top_k),
                "window": int(window),
                "n_dates": int(top.notna().sum()),
                "top_return_mean": _nanmean(top),
                "next_return_mean": _nanmean(next_bucket),
                "rest_return_mean": _nanmean(rest),
                "universe_return_mean": _nanmean(universe),
                "top_minus_next_mean": _nanmean(top - next_bucket),
                "top_minus_rest_mean": _nanmean(top - rest),
                "top_minus_universe_mean": _nanmean(top - universe),
                "top_win_rate_vs_next": _win_rate(top, next_bucket),
                "top_win_rate_vs_rest": _win_rate(top, rest),
                "top_win_rate_vs_universe": _win_rate(top, universe),
            }
        )
    return pd.DataFrame(rows)


def topk_parameter_sensitivity(
    scores: pd.DataFrame,
    daily_returns: pd.DataFrame,
    top_k_values: Sequence[int] = (2, 3, 4, 5, 6, 8),
    strategy_id: str = "default",
    annualization: int = 252,
) -> pd.DataFrame:
    """Back out equal-weight TopK ranking portfolios from one score matrix."""
    score = _wide_numeric(scores, "scores")
    returns = _wide_numeric(daily_returns, "daily_returns")
    score, returns = _align_wide_frames(score, returns)
    forward_1d = _forward_return_wide(returns, 1)
    ranks = score.rank(axis=1, ascending=False, method="first")
    eligible = score.notna() & forward_1d.notna()

    rows: list[dict[str, Any]] = []
    for top_k in top_k_values:
        top_k = _positive_int(top_k, "top_k")
        selected = ranks.le(top_k) & eligible
        counts = selected.sum(axis=1).replace(0, np.nan)
        weights = selected.astype(float).div(counts, axis=0).fillna(0.0)
        portfolio_returns = (weights * forward_1d.fillna(0.0)).sum(axis=1)
        active = counts.notna()
        active_returns = portfolio_returns.loc[active]
        metrics = performance_metrics(active_returns)
        turnover = weights.diff().abs()
        if not turnover.empty:
            turnover.iloc[0] = weights.iloc[0].abs()
        rows.append(
            {
                "strategy_id": strategy_id,
                "top_k": top_k,
                "n_days": int(active_returns.shape[0]),
                "avg_selected": _nanmean(counts),
                "turnover_abs_sum": float(turnover.sum().sum()),
                "turnover_abs_mean": float(turnover.sum(axis=1).mean())
                if not turnover.empty
                else np.nan,
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def _wide_numeric(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    if frame.empty:
        raise ValueError(f"{name} must not be empty")
    out = frame.copy()
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    return out.apply(pd.to_numeric, errors="coerce")


def _align_wide_frames(
    left: pd.DataFrame, right: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    index = left.index.intersection(right.index)
    columns = left.columns.intersection(right.columns)
    if index.empty or columns.empty:
        raise ValueError("scores and daily_returns must share dates and symbols")
    return left.loc[index, columns], right.loc[index, columns]


def _forward_return_wide(daily_returns: pd.DataFrame, window: int) -> pd.DataFrame:
    shifted = 1.0 + daily_returns.shift(-1)
    return (
        shifted.iloc[::-1]
        .rolling(window=window, min_periods=window)
        .apply(
            np.prod,
            raw=True,
        )
        .iloc[::-1]
        - 1.0
    )


def _positive_int(value: int, name: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise ValueError(f"{name} must be positive")
    return ivalue


def _nanmean(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce")
    return float(numeric.mean()) if numeric.notna().any() else np.nan


def _win_rate(left: pd.Series, right: pd.Series) -> float:
    aligned = pd.concat([left, right], axis=1).dropna()
    if aligned.empty:
        return np.nan
    return float((aligned.iloc[:, 0] > aligned.iloc[:, 1]).mean())
