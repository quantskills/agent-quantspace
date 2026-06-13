"""Robustness and overfit diagnostics for strategy attribution candidates."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from itertools import combinations
from math import ceil
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

MetricFn = Callable[[pd.Series], float]


def rolling_metric_slices(
    returns: pd.Series | Sequence[float] | np.ndarray,
    windows: Sequence[int] = (252, 504, 756),
    annualization: int = 252,
) -> pd.DataFrame:
    """Summarize full-period metrics and rolling-window metric distributions."""
    annualization = _positive_int(annualization, "annualization")
    r, n_missing = _clean_return_series(returns)
    rows = [_full_metric_row(r, n_missing=n_missing, annualization=annualization)]

    for window in windows:
        window = _positive_int(window, "window")
        rolling_rows = [
            _metric_dict(r.iloc[start : start + window], annualization=annualization)
            for start in range(0, max(len(r) - window + 1, 0))
        ]
        rows.append(_rolling_metric_row(r, rolling_rows, window, n_missing, annualization))

    return pd.DataFrame(rows)


def deflated_sharpe_ratio(
    returns: pd.Series | Sequence[float] | np.ndarray,
    n_trials: int,
    benchmark_sr: float = 0.0,
    annualization: int = 252,
) -> dict[str, float]:
    """Estimate deflated Sharpe ratio after accounting for multiple trials.

    The implementation follows the common Bailey-Lopez de Prado approximation:
    estimate the expected maximum Sharpe under repeated trials, then evaluate the
    observed Sharpe against that hurdle using a finite-sample Sharpe standard error.
    All Sharpe values returned by this function are annualized.
    """
    trials = _positive_int(n_trials, "n_trials")
    annualization = _positive_int(annualization, "annualization")
    r, n_missing = _clean_return_series(returns)
    n_obs = len(r)
    if n_obs == 0:
        raise ValueError("returns must contain at least one finite observation")

    daily_sr = _periodic_sharpe(r)
    sharpe = _annualize_sharpe(daily_sr, annualization)
    skew = _skew(r)
    kurtosis = _kurtosis(r)
    sr_std = _sharpe_standard_error(daily_sr, skew, kurtosis, n_obs) * np.sqrt(annualization)
    expected_max_sr = _expected_max_sharpe(benchmark_sr, sr_std, trials)

    if not np.isfinite(sharpe):
        if sharpe > expected_max_sr:
            dsr = 1.0
        elif sharpe < expected_max_sr:
            dsr = 0.0
        else:
            dsr = 0.5
    elif sr_std <= 0.0 or not np.isfinite(sr_std):
        dsr = float(sharpe > expected_max_sr)
        if sharpe == expected_max_sr:
            dsr = 0.5
    else:
        dsr = float(norm.cdf((sharpe - expected_max_sr) / sr_std))

    dsr = float(np.clip(dsr, 0.0, 1.0))
    return {
        "n_obs": float(n_obs),
        "n_missing": float(n_missing),
        "n_trials": float(trials),
        "sharpe": float(sharpe),
        "skew": float(skew),
        "kurtosis": float(kurtosis),
        "benchmark_sr": float(benchmark_sr),
        "expected_max_sr": float(expected_max_sr),
        "dsr": dsr,
        "p_value": float(1.0 - dsr),
    }


def pbo_from_candidate_returns(
    candidate_returns: pd.DataFrame,
    n_splits: int = 4,
    annualization: int = 252,
) -> dict[str, Any]:
    """Compute a CSCV-style probability of backtest overfitting diagnostic."""
    annualization = _positive_int(annualization, "annualization")
    candidates = _clean_candidate_returns(candidate_returns)
    splits = _validate_splits(len(candidates), n_splits)
    split_indices = np.array_split(np.arange(len(candidates)), splits)
    train_size = splits // 2

    rows: list[dict[str, Any]] = []
    selected: list[str] = []

    for train_split_ids in combinations(range(splits), train_size):
        train_ids = np.concatenate([split_indices[i] for i in train_split_ids])
        test_ids = np.concatenate(
            [split_indices[i] for i in range(splits) if i not in set(train_split_ids)]
        )
        train_scores = _candidate_sharpes(candidates.iloc[train_ids], annualization)
        test_scores = _candidate_sharpes(candidates.iloc[test_ids], annualization)
        valid_train = train_scores.dropna()
        valid_test = test_scores.dropna()
        valid_names = valid_train.index.intersection(valid_test.index)
        if valid_names.empty:
            continue

        valid_train = valid_train.loc[valid_names]
        valid_test = valid_test.loc[valid_names]
        selected_name = str(valid_train.idxmax())
        rank = float(valid_test.rank(ascending=False, method="average").loc[selected_name])
        n_candidates = len(valid_test)
        percentile = float((n_candidates - rank + 1.0) / (n_candidates + 1.0))
        percentile = float(np.clip(percentile, np.finfo(float).eps, 1.0 - np.finfo(float).eps))
        logit = float(np.log(percentile / (1.0 - percentile)))
        rows.append(
            {
                "train_splits": tuple(train_split_ids),
                "test_splits": tuple(i for i in range(splits) if i not in set(train_split_ids)),
                "selected_candidate": selected_name,
                "train_sharpe": float(valid_train.loc[selected_name]),
                "test_sharpe": float(valid_test.loc[selected_name]),
                "test_rank": rank,
                "relative_rank": percentile,
                "logit": logit,
                "is_overfit": bool(logit < 0.0),
            }
        )
        selected.append(selected_name)

    if not rows:
        raise ValueError("candidate_returns do not provide any valid CSCV train/test trial")

    details = pd.DataFrame(rows)
    counts = pd.Series(selected, dtype="object").value_counts().sort_index()
    return {
        "pbo": float(details["is_overfit"].mean()),
        "n_trials": int(len(details)),
        "selected_counts": {str(key): int(value) for key, value in counts.items()},
        "details": details,
    }


def pbo_sensitivity_from_candidate_returns(
    candidate_returns: pd.DataFrame,
    split_values: Sequence[int] = (8, 10, 12, 16),
    annualization: int = 252,
    promotion_threshold: float = 0.20,
) -> pd.DataFrame:
    """Run CSCV PBO across a fixed set of partition counts.

    Rows with too few observations for a requested partition count are kept as
    unavailable rows so attribution packs preserve the pre-registered grid.
    """
    annualization = _positive_int(annualization, "annualization")
    candidates = _clean_candidate_returns(candidate_returns)
    rows: list[dict[str, Any]] = []

    for split_value in split_values:
        n_splits = _positive_int(split_value, "n_splits")
        row: dict[str, Any] = {
            "n_splits": n_splits,
            "n_obs": int(len(candidates)),
            "n_candidates": int(candidates.shape[1]),
            "n_trials": np.nan,
            "pbo": np.nan,
            "pbo_standard_error": np.nan,
            "attribution_stability_score": np.nan,
            "promotion_flag": "watch",
            "selected_counts": "{}",
            "status": "unavailable",
            "notes": "",
        }
        try:
            result = pbo_from_candidate_returns(
                candidates,
                n_splits=n_splits,
                annualization=annualization,
            )
        except ValueError as exc:
            row["notes"] = str(exc)
            rows.append(row)
            continue

        pbo = float(result["pbo"])
        n_trials = int(result["n_trials"])
        row.update(
            {
                "n_trials": n_trials,
                "pbo": pbo,
                "pbo_standard_error": _proportion_standard_error(pbo, n_trials),
                "attribution_stability_score": 1.0 - pbo,
                "promotion_flag": "advance" if pbo <= promotion_threshold else "watch",
                "selected_counts": json.dumps(result["selected_counts"], sort_keys=True),
                "status": "ok",
                "notes": f"promotion_threshold={promotion_threshold:.2f}",
            }
        )
        rows.append(row)

    return pd.DataFrame(rows)


def block_bootstrap_metric(
    returns: pd.Series | Sequence[float] | np.ndarray,
    metric_fn: MetricFn,
    n_bootstrap: int = 200,
    block_size: int = 20,
    random_state: int | np.random.Generator | None = None,
) -> dict[str, float]:
    """Estimate a metric distribution with circular moving-block bootstrap."""
    n_bootstrap = _positive_int(n_bootstrap, "n_bootstrap")
    block_size = _positive_int(block_size, "block_size")
    r, n_missing = _clean_return_series(returns)
    if r.empty:
        raise ValueError("returns must contain at least one finite observation")

    rng = (
        random_state
        if isinstance(random_state, np.random.Generator)
        else np.random.default_rng(random_state)
    )
    values = np.empty(n_bootstrap, dtype=float)
    n_obs = len(r)
    n_blocks = ceil(n_obs / block_size)
    offsets = np.arange(block_size)

    for i in range(n_bootstrap):
        starts = rng.integers(0, n_obs, size=n_blocks)
        sample_idx = ((starts[:, None] + offsets[None, :]) % n_obs).reshape(-1)[:n_obs]
        sample = pd.Series(r.to_numpy()[sample_idx], index=r.index[:n_obs])
        values[i] = float(metric_fn(sample))

    valid = values[np.isfinite(values)]
    if valid.size == 0:
        raise ValueError("metric_fn did not produce any finite bootstrap values")

    quantiles = np.quantile(valid, [0.05, 0.25, 0.50, 0.75, 0.95])
    return {
        "n_obs": float(n_obs),
        "n_missing": float(n_missing),
        "n_bootstrap": float(n_bootstrap),
        "block_size": float(block_size),
        "mean": float(np.mean(valid)),
        "std": float(np.std(valid, ddof=1)) if valid.size > 1 else 0.0,
        "q05": float(quantiles[0]),
        "q25": float(quantiles[1]),
        "q50": float(quantiles[2]),
        "q75": float(quantiles[3]),
        "q95": float(quantiles[4]),
    }


def _full_metric_row(returns: pd.Series, n_missing: int, annualization: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "slice": "full",
        "window": len(returns),
        "n_obs": len(returns),
        "n_missing": n_missing,
        "n_slices": 1 if len(returns) > 0 else 0,
        "start": returns.index[0] if len(returns) > 0 else pd.NaT,
        "end": returns.index[-1] if len(returns) > 0 else pd.NaT,
    }
    row.update(_metric_dict(returns, annualization))
    return row


def _rolling_metric_row(
    returns: pd.Series,
    rolling_rows: list[dict[str, float]],
    window: int,
    n_missing: int,
    annualization: int,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "slice": f"rolling_{window}",
        "window": window,
        "n_obs": len(returns),
        "n_missing": n_missing,
        "n_slices": len(rolling_rows),
        "start": returns.index[0] if len(returns) > 0 else pd.NaT,
        "end": returns.index[-1] if len(returns) > 0 else pd.NaT,
    }
    metric_names = tuple(_metric_dict(pd.Series([0.0]), annualization).keys())
    if not rolling_rows:
        for name in metric_names:
            row[f"{name}_mean"] = np.nan
            row[f"{name}_std"] = np.nan
            row[f"{name}_min"] = np.nan
            row[f"{name}_max"] = np.nan
        return row

    metrics = pd.DataFrame(rolling_rows)
    for name in metric_names:
        values = pd.to_numeric(metrics[name], errors="coerce").replace([np.inf, -np.inf], np.nan)
        row[f"{name}_mean"] = float(values.mean()) if values.notna().any() else np.nan
        row[f"{name}_std"] = float(values.std(ddof=1)) if values.notna().sum() > 1 else 0.0
        row[f"{name}_min"] = float(values.min()) if values.notna().any() else np.nan
        row[f"{name}_max"] = float(values.max()) if values.notna().any() else np.nan
    return row


def _metric_dict(returns: pd.Series, annualization: int) -> dict[str, float]:
    total_return = _total_return(returns)
    ann_return = _annualized_return(returns, annualization)
    maxdd = _max_drawdown(returns)
    sharpe = _annualized_sharpe(returns, annualization)
    return {
        "total_return": total_return,
        "ann_return": ann_return,
        "maxdd": maxdd,
        "sharpe": sharpe,
        "calmar": _calmar(ann_return, maxdd),
        "worst20D": _worst_window_return(returns, 20),
    }


def _clean_return_series(
    returns: pd.Series | Sequence[float] | np.ndarray,
) -> tuple[pd.Series, int]:
    if isinstance(returns, pd.Series):
        series = returns.copy()
    else:
        series = pd.Series(returns)
    series = pd.to_numeric(series, errors="coerce")
    n_missing = int(series.isna().sum())
    series = series.dropna().astype(float)
    if isinstance(series.index, pd.DatetimeIndex):
        series = series.sort_index()
    return series, n_missing


def _clean_candidate_returns(candidate_returns: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(candidate_returns, pd.DataFrame):
        raise TypeError("candidate_returns must be a pandas DataFrame")
    if candidate_returns.empty:
        raise ValueError("candidate_returns must not be empty")

    df = candidate_returns.apply(pd.to_numeric, errors="coerce")
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    if df.empty:
        raise ValueError("candidate_returns must contain finite observations")
    if df.shape[1] < 2:
        raise ValueError("candidate_returns must contain at least two candidates")
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()
    return df


def _candidate_sharpes(frame: pd.DataFrame, annualization: int) -> pd.Series:
    return frame.apply(
        lambda col: _annualized_sharpe(col.dropna().astype(float), annualization), axis=0
    )


def _validate_splits(n_obs: int, n_splits: int) -> int:
    splits = _positive_int(n_splits, "n_splits")
    if splits < 2:
        raise ValueError("n_splits must be at least 2")
    if splits % 2 != 0:
        raise ValueError("n_splits must be even for CSCV train/test halves")
    if n_obs < splits:
        raise ValueError("candidate_returns must have at least n_splits observations")
    return splits


def _proportion_standard_error(p: float, n: int) -> float:
    if n <= 0 or not np.isfinite(p):
        return np.nan
    return float(np.sqrt(max(p * (1.0 - p), 0.0) / n))


def _positive_int(value: int, name: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise ValueError(f"{name} must be positive")
    return ivalue


def _total_return(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan
    return float(np.prod(1.0 + returns.to_numpy(dtype=float)) - 1.0)


def _annualized_return(returns: pd.Series, annualization: int) -> float:
    if returns.empty:
        return np.nan
    terminal = 1.0 + _total_return(returns)
    if terminal <= 0.0:
        return -1.0
    return float(terminal ** (annualization / len(returns)) - 1.0)


def _periodic_sharpe(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan
    mean = float(returns.mean())
    std = float(returns.std(ddof=1))
    if std <= 0.0 or not np.isfinite(std):
        if mean > 0.0:
            return float("inf")
        if mean < 0.0:
            return float("-inf")
        return 0.0
    return mean / std


def _annualized_sharpe(returns: pd.Series, annualization: int) -> float:
    return _annualize_sharpe(_periodic_sharpe(returns), annualization)


def _annualize_sharpe(periodic_sharpe: float, annualization: int) -> float:
    return float(periodic_sharpe * np.sqrt(annualization))


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan
    wealth = np.concatenate([[1.0], np.cumprod(1.0 + returns.to_numpy(dtype=float))])
    peaks = np.maximum.accumulate(wealth)
    drawdowns = wealth / peaks - 1.0
    return float(abs(np.min(drawdowns)))


def _calmar(ann_return: float, maxdd: float) -> float:
    if not np.isfinite(ann_return):
        return np.nan
    if maxdd > 0.0:
        return float(ann_return / maxdd)
    if ann_return > 0.0:
        return float("inf")
    if ann_return < 0.0:
        return float("-inf")
    return 0.0


def _worst_window_return(returns: pd.Series, window: int) -> float:
    if returns.empty:
        return np.nan
    actual_window = min(window, len(returns))
    rolling = (1.0 + returns).rolling(actual_window, min_periods=actual_window).apply(
        np.prod, raw=True
    ) - 1.0
    valid = rolling.dropna()
    return float(valid.min()) if not valid.empty else _total_return(returns)


def _skew(returns: pd.Series) -> float:
    if len(returns) < 3:
        return 0.0
    value = float(returns.skew())
    return value if np.isfinite(value) else 0.0


def _kurtosis(returns: pd.Series) -> float:
    if len(returns) < 4:
        return 3.0
    value = float(returns.kurt()) + 3.0
    return value if np.isfinite(value) else 3.0


def _sharpe_standard_error(daily_sr: float, skew: float, kurtosis: float, n_obs: int) -> float:
    if n_obs <= 1:
        return np.inf
    if not np.isfinite(daily_sr):
        return 0.0
    variance = (1.0 - skew * daily_sr + ((kurtosis - 1.0) / 4.0) * daily_sr**2) / (n_obs - 1)
    return float(np.sqrt(max(variance, 0.0)))


def _expected_max_sharpe(benchmark_sr: float, sr_std: float, n_trials: int) -> float:
    if n_trials <= 1 or sr_std <= 0.0 or not np.isfinite(sr_std):
        return float(benchmark_sr)
    gamma = 0.5772156649015329
    first = norm.ppf(1.0 - 1.0 / n_trials)
    second = norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    return float(benchmark_sr + sr_std * ((1.0 - gamma) * first + gamma * second))
