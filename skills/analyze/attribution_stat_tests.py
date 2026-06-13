"""Lightweight multiple-testing diagnostics for attribution candidates."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations
from math import ceil
from typing import Any

import numpy as np
import pandas as pd


def white_reality_check(
    candidate_returns: pd.DataFrame,
    benchmark_col: str | None = None,
    n_bootstrap: int = 500,
    block_size: int = 20,
    random_state: int | np.random.Generator | None = None,
) -> dict[str, Any]:
    """Run an approximate White Reality Check on candidate return columns.

    When ``benchmark_col`` is provided, candidate performance is measured as
    candidate return minus benchmark return and the benchmark column is not
    tested as a candidate.
    """
    n_bootstrap = _positive_int(n_bootstrap, "n_bootstrap")
    prepared = _prepare_candidate_differentials(candidate_returns, benchmark_col)
    diff = prepared["differentials"]
    block_size = _effective_block_size(block_size, len(diff))

    means = diff.mean(axis=0)
    best_candidate = str(means.idxmax())
    observed_best_mean = float(means.loc[best_candidate])

    rng = _rng(random_state)
    centered = diff - means
    bootstrap_values = _bootstrap_max_means(
        centered.to_numpy(dtype=float),
        n_bootstrap=n_bootstrap,
        block_size=block_size,
        rng=rng,
    )
    p_value = _right_tail_p_value(bootstrap_values, observed_best_mean)

    return {
        "test": "reality_check",
        "best_candidate": best_candidate,
        "observed_best_mean": observed_best_mean,
        "p_value": p_value,
        "bootstrap_mean": float(np.mean(bootstrap_values)),
        "bootstrap_std": _sample_std(bootstrap_values),
        "n_obs": int(len(diff)),
        "n_candidates": int(diff.shape[1]),
        "n_bootstrap": int(n_bootstrap),
        "block_size": int(block_size),
        "benchmark_col": benchmark_col,
        "dropped_rows": int(prepared["dropped_rows"]),
        "candidate_means": {str(key): float(value) for key, value in means.items()},
    }


def hansen_spa_test(
    candidate_returns: pd.DataFrame,
    benchmark_col: str | None = None,
    n_bootstrap: int = 500,
    block_size: int = 20,
    random_state: int | np.random.Generator | None = None,
    studentize: bool = True,
) -> dict[str, Any]:
    """Run a compact Hansen SPA-style bootstrap test.

    This implementation keeps the mechanics intentionally simple: weak
    alternatives are screened by a finite-sample threshold, the best observed
    mean differential defines the selected candidate, and the bootstrap null is
    built from centered moving-block samples.
    """
    n_bootstrap = _positive_int(n_bootstrap, "n_bootstrap")
    prepared = _prepare_candidate_differentials(candidate_returns, benchmark_col)
    diff = prepared["differentials"]
    block_size = _effective_block_size(block_size, len(diff))

    means = diff.mean(axis=0)
    std = diff.std(axis=0, ddof=1).replace(0.0, np.nan)
    std = std.fillna(_fallback_std(diff))
    best_candidate = str(means.idxmax())
    included = _spa_included_candidates(means, std, len(diff))
    included_diff = diff.loc[:, included]
    included_means = means.loc[included]
    included_std = std.loc[included]

    if studentize:
        observed_stats = _studentized_stats(
            included_means.to_numpy(), included_std.to_numpy(), len(diff)
        )
    else:
        observed_stats = np.sqrt(len(diff)) * included_means.to_numpy(dtype=float)
    test_stat = float(np.max(observed_stats))

    rng = _rng(random_state)
    centered = included_diff - included_means
    samples = _bootstrap_column_means(
        centered.to_numpy(dtype=float),
        n_bootstrap=n_bootstrap,
        block_size=block_size,
        rng=rng,
    )
    if studentize:
        bootstrap_stats = _studentized_stats(samples, included_std.to_numpy(), len(diff)).max(
            axis=1
        )
    else:
        bootstrap_stats = (np.sqrt(len(diff)) * samples).max(axis=1)
    p_value = _right_tail_p_value(bootstrap_stats, test_stat)

    return {
        "test": "spa",
        "best_candidate": best_candidate,
        "included_candidates": [str(name) for name in included],
        "test_stat": test_stat,
        "p_value": p_value,
        "bootstrap_mean": float(np.mean(bootstrap_stats)),
        "bootstrap_std": _sample_std(bootstrap_stats),
        "n_obs": int(len(diff)),
        "n_candidates": int(diff.shape[1]),
        "n_bootstrap": int(n_bootstrap),
        "block_size": int(block_size),
        "benchmark_col": benchmark_col,
        "studentize": bool(studentize),
        "dropped_rows": int(prepared["dropped_rows"]),
        "candidate_means": {str(key): float(value) for key, value in means.items()},
    }


def cpcv_splits(
    n_obs: int,
    n_groups: int,
    n_test_groups: int = 1,
    purge: int = 0,
    embargo: int = 0,
) -> list[dict[str, Any]]:
    """Create combinatorial purged cross-validation train/test splits."""
    n_obs = _positive_int(n_obs, "n_obs")
    n_groups = _positive_int(n_groups, "n_groups")
    n_test_groups = _positive_int(n_test_groups, "n_test_groups")
    purge = _non_negative_int(purge, "purge")
    embargo = _non_negative_int(embargo, "embargo")
    if n_groups > n_obs:
        raise ValueError("n_groups must be less than or equal to n_obs")
    if n_test_groups > n_groups:
        raise ValueError("n_test_groups must be less than or equal to n_groups")

    indices = np.arange(n_obs)
    groups = [np.asarray(group, dtype=int) for group in np.array_split(indices, n_groups)]
    splits: list[dict[str, Any]] = []
    for test_group_ids in combinations(range(n_groups), n_test_groups):
        test_indices = np.concatenate([groups[group_id] for group_id in test_group_ids])
        forbidden = _purged_forbidden_mask(n_obs, test_indices, purge=purge, embargo=embargo)
        train_indices = indices[~forbidden]
        splits.append(
            {
                "train_indices": train_indices,
                "test_indices": test_indices,
                "train_groups": tuple(i for i in range(n_groups) if i not in set(test_group_ids)),
                "test_groups": tuple(test_group_ids),
            }
        )
    return splits


def summarize_stat_tests(
    candidate_returns: pd.DataFrame,
    benchmark_col: str | None = None,
    n_bootstrap: int = 500,
    block_size: int = 20,
    random_state: int | np.random.Generator | None = None,
    studentize: bool = True,
) -> pd.DataFrame:
    """Return Reality Check and SPA diagnostics as a compact summary table."""
    seeds = _child_seeds(random_state, 2)
    reality = white_reality_check(
        candidate_returns,
        benchmark_col=benchmark_col,
        n_bootstrap=n_bootstrap,
        block_size=block_size,
        random_state=seeds[0],
    )
    spa = hansen_spa_test(
        candidate_returns,
        benchmark_col=benchmark_col,
        n_bootstrap=n_bootstrap,
        block_size=block_size,
        random_state=seeds[1],
        studentize=studentize,
    )
    rows = []
    for result in (reality, spa):
        rows.append(
            {
                "test": result["test"],
                "best_candidate": result["best_candidate"],
                "p_value": result["p_value"],
                "observed_best_mean": result.get("observed_best_mean", np.nan),
                "test_stat": result.get("test_stat", np.nan),
                "bootstrap_mean": result["bootstrap_mean"],
                "bootstrap_std": result["bootstrap_std"],
                "n_obs": result["n_obs"],
                "n_candidates": result["n_candidates"],
                "block_size": result["block_size"],
            }
        )
    return pd.DataFrame(rows)


def _prepare_candidate_differentials(
    candidate_returns: pd.DataFrame,
    benchmark_col: str | None,
) -> dict[str, Any]:
    if not isinstance(candidate_returns, pd.DataFrame):
        raise TypeError("candidate_returns must be a pandas DataFrame")
    if candidate_returns.empty:
        raise ValueError("candidate_returns must not be empty")

    frame = candidate_returns.apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(axis=1, how="all")
    if benchmark_col is not None and benchmark_col not in frame.columns:
        raise ValueError(f"benchmark_col is not in candidate_returns: {benchmark_col}")
    if isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.sort_index()

    if benchmark_col is None:
        diff = frame
    else:
        benchmark = frame[benchmark_col]
        diff = frame.drop(columns=[benchmark_col]).sub(benchmark, axis=0)

    diff = diff.dropna(axis=1, how="all")
    if diff.shape[1] < 2:
        raise ValueError("candidate_returns must contain at least two testable candidates")

    before = len(diff)
    diff = diff.replace([np.inf, -np.inf], np.nan).dropna(axis=0, how="any")
    dropped_rows = before - len(diff)
    if len(diff) < 2:
        raise ValueError("candidate_returns must contain at least two complete observations")
    return {"differentials": diff.astype(float), "dropped_rows": dropped_rows}


def _bootstrap_column_means(
    values: np.ndarray,
    n_bootstrap: int,
    block_size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    n_obs = values.shape[0]
    n_blocks = ceil(n_obs / block_size)
    offsets = np.arange(block_size)
    starts = rng.integers(0, n_obs, size=(n_bootstrap, n_blocks))
    sample_idx = ((starts[:, :, None] + offsets[None, None, :]) % n_obs).reshape(n_bootstrap, -1)
    sample_idx = sample_idx[:, :n_obs]
    return values[sample_idx].mean(axis=1)


def _bootstrap_max_means(
    values: np.ndarray,
    n_bootstrap: int,
    block_size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    return _bootstrap_column_means(values, n_bootstrap, block_size, rng).max(axis=1)


def _studentized_stats(means: np.ndarray, std: np.ndarray, n_obs: int) -> np.ndarray:
    denominator = np.where(std > 0.0, std, 1.0)
    return np.sqrt(n_obs) * means / denominator


def _spa_included_candidates(means: pd.Series, std: pd.Series, n_obs: int) -> list[str]:
    scale = np.sqrt(np.maximum(np.log(np.log(max(n_obs, 3))), 1.0) / n_obs)
    threshold = -scale * std
    included = [str(name) for name in means.index[means >= threshold]]
    if included:
        return included
    return [str(means.idxmax())]


def _purged_forbidden_mask(
    n_obs: int,
    test_indices: np.ndarray,
    purge: int,
    embargo: int,
) -> np.ndarray:
    forbidden = np.zeros(n_obs, dtype=bool)
    for test_idx in test_indices:
        start = max(0, int(test_idx) - purge)
        end = min(n_obs, int(test_idx) + embargo + 1)
        forbidden[start:end] = True
    return forbidden


def _effective_block_size(block_size: int, n_obs: int) -> int:
    block_size = _positive_int(block_size, "block_size")
    if n_obs <= 0:
        raise ValueError("n_obs must be positive")
    return min(block_size, n_obs)


def _fallback_std(frame: pd.DataFrame) -> float:
    values = frame.to_numpy(dtype=float).reshape(-1)
    std = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
    return std if std > 0.0 and np.isfinite(std) else 1.0


def _right_tail_p_value(samples: Sequence[float] | np.ndarray, observed: float) -> float:
    values = np.asarray(samples, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise ValueError("bootstrap samples must contain finite values")
    p_value = (float(np.sum(values >= observed)) + 1.0) / (float(values.size) + 1.0)
    return float(np.clip(p_value, 0.0, 1.0))


def _sample_std(values: Sequence[float] | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    return float(np.std(array, ddof=1)) if array.size > 1 else 0.0


def _rng(random_state: int | np.random.Generator | None) -> np.random.Generator:
    if isinstance(random_state, np.random.Generator):
        return random_state
    return np.random.default_rng(random_state)


def _child_seeds(
    random_state: int | np.random.Generator | None,
    n_children: int,
) -> list[int | np.random.Generator | None]:
    if random_state is None:
        return [None] * n_children
    rng = _rng(random_state)
    return [int(seed) for seed in rng.integers(0, np.iinfo(np.uint32).max, size=n_children)]


def _positive_int(value: int, name: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise ValueError(f"{name} must be positive")
    return ivalue


def _non_negative_int(value: int, name: str) -> int:
    ivalue = int(value)
    if ivalue < 0:
        raise ValueError(f"{name} must be non-negative")
    return ivalue
