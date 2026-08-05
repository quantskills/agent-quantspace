"""Deterministic predictive-power and trading evaluation helpers.

Execution-aligned return labels
-------------------------------
Predictive/group/pool labels and formal VectorBacktester semantics share one
canonical definition over ``protocol.trade_at`` prices:

Let ``P`` be the trade_at price, ``L = signal_lag``, ``H = horizon_bars``.

* ``return_mode="forward"``: label at signal time ``t`` is
  ``P[t+L+H]/P[t+L] - 1`` (holding ``H`` bars starting at the first
  executable bar ``t+L``).
* ``return_mode="backward"``: label at signal time ``t`` is
  ``P[t+L]/P[t+L-H] - 1`` (holding ``H`` bars ending at executable bar
  ``t+L``).

Missing prices never fabricate returns (no fill across gaps). Formal trading
via VectorBacktester is available only when ``H == 1`` (engine is one-bar);
otherwise trading is explicitly unavailable. When available, ``trade_at``,
``signal_lag`` and ``return_mode`` are passed through unchanged so IC and
formal trading refer to the same executable interval.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from skills.analyze.contracts import (
    Finding,
    FindingSeverity,
    MetricResult,
    ProtocolSnapshot,
    UncertaintyResult,
)
from skills.analyze.validation import identify_levels
from skills.backtest import VectorBacktester

BacktesterFactory = Callable[..., Any]


def _finding(
    name: str,
    *,
    passed: bool,
    message: str,
    severity: FindingSeverity = FindingSeverity.HARD_FAIL,
    details: Mapping[str, Any] | None = None,
) -> Finding:
    return Finding(
        name=name,
        severity=severity,
        passed=passed,
        message=message,
        details=dict(details or {}),
    )


def _metric(
    name: str,
    value: float | int | str | bool | None,
    *,
    unit: str,
    sample_range: str,
    unavailable_reason: str | None = None,
) -> MetricResult:
    if unavailable_reason is not None:
        return MetricResult(
            name=name,
            value=None,
            unit=unit,
            sample_range=sample_range,
            unavailable_reason=unavailable_reason,
        )
    return MetricResult(
        name=name, value=value, unit=unit, sample_range=sample_range
    )


def _working_frame(
    panel: pd.DataFrame,
    values: pd.Series,
    protocol: ProtocolSnapshot,
) -> tuple[list[Finding], pd.DataFrame | None]:
    findings, symbol_pos, datetime_pos = identify_levels(panel.index, protocol)
    hard = [
        f
        for f in findings
        if (not f.passed) and f.severity is FindingSeverity.HARD_FAIL
    ]
    if hard or symbol_pos is None or datetime_pos is None:
        return findings, None

    if not isinstance(values, pd.Series):
        findings.append(
            _finding(
                "EVALUATION_VALUES_TYPE",
                passed=False,
                message="factor values must be a Series",
            )
        )
        return findings, None
    if list(values.index.names) != list(panel.index.names):
        findings.append(
            _finding(
                "EVALUATION_INDEX_NAMES",
                passed=False,
                message="values index names must match panel before any rename",
                details={
                    "values_names": list(values.index.names),
                    "panel_names": list(panel.index.names),
                },
            )
        )
        return findings, None
    if not values.index.equals(panel.index):
        findings.append(
            _finding(
                "EVALUATION_INDEX_VALUES",
                passed=False,
                message="values index keys must equal panel index keys",
            )
        )
        return findings, None

    work_panel = panel.copy(deep=True)
    work_values = values.copy(deep=True)
    if symbol_pos != 0 or datetime_pos != 1:
        order = [symbol_pos, datetime_pos]
        work_panel = work_panel.reorder_levels(order).sort_index()
        work_values = work_values.reorder_levels(order).sort_index()
    else:
        work_panel = work_panel.sort_index()
        work_values = work_values.sort_index()
    work_panel.index = work_panel.index.set_names(["symbol", "eob"])
    work_values.index = work_values.index.set_names(["symbol", "eob"])

    trade_col = protocol.trade_at
    if trade_col not in work_panel.columns:
        findings.append(
            _finding(
                "EVALUATION_MISSING_TRADE_AT",
                passed=False,
                message=f"panel requires trade_at column {trade_col!r} for execution-aligned returns",
            )
        )
        # Keep close-missing as its own code when close is also absent.
        if "close" not in work_panel.columns:
            findings.append(
                _finding(
                    "EVALUATION_MISSING_CLOSE",
                    passed=False,
                    message="panel requires a close column",
                )
            )
        return findings, None

    frame = pd.DataFrame(
        {
            "price": work_panel[trade_col],
            "fac_val": work_values.astype(float),
        }
    )
    for col in ("open", "high", "low", "close"):
        if col in work_panel.columns:
            frame[col] = work_panel[col]
    return findings, frame


def execution_aligned_returns(
    price: pd.Series,
    protocol: ProtocolSnapshot,
) -> pd.Series:
    """Canonical executable holding return labeled at signal time ``t``.

    Never fabricates returns across missing prices.
    """
    if list(price.index.names) != ["symbol", "eob"]:
        raise ValueError("execution_aligned_returns requires names ['symbol','eob']")
    wide = price.unstack("symbol")
    lag = int(protocol.signal_lag)
    horizon = int(protocol.horizon_bars)
    if protocol.return_mode == "forward":
        # P[t+L+H] / P[t+L] - 1
        end = wide.shift(-(lag + horizon))
        start = wide.shift(-lag)
        fut = end.div(start).sub(1.0)
    else:
        # P[t+L] / P[t+L-H] - 1
        end = wide.shift(-lag)
        start = wide.shift(-lag + horizon)
        fut = end.div(start).sub(1.0)
    # Explicitly keep NaNs where either endpoint missing (no fill).
    fut = fut.where(start.notna() & end.notna())
    try:
        stacked = fut.stack(future_stack=True)
    except TypeError:
        stacked = fut.stack()
    stacked.name = "future_return"
    if list(stacked.index.names) != ["symbol", "eob"]:
        stacked = stacked.reorder_levels(["symbol", "eob"]).sort_index()
    return stacked


# Backward-compatible name used by pool/incremental callers.
def _forward_returns(close: pd.Series, horizon: int) -> pd.Series:
    """Deprecated close-only helper retained for isolated unit tests of fill_method."""
    wide = close.unstack("symbol")
    fut = wide.pct_change(horizon, fill_method=None).shift(-horizon)
    try:
        stacked = fut.stack(future_stack=True)
    except TypeError:
        stacked = fut.stack()
    stacked.name = "future_return"
    if list(stacked.index.names) != ["symbol", "eob"]:
        stacked = stacked.reorder_levels(["symbol", "eob"]).sort_index()
    return stacked


def _cross_section_corr(
    factor: pd.Series,
    future: pd.Series,
    *,
    rank: bool,
    min_cross_section: int,
) -> pd.Series:
    merged = pd.concat([factor.rename("factor"), future.rename("future_return")], axis=1)
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if merged.empty:
        return pd.Series(dtype=float, name="IC")

    out: dict[Any, float] = {}
    for dt, group in merged.groupby(level="eob"):
        if len(group) < min_cross_section:
            continue
        if group["factor"].nunique(dropna=True) < 2:
            continue
        if group["future_return"].nunique(dropna=True) < 2:
            continue
        x = group["factor"]
        y = group["future_return"]
        if rank:
            x = x.rank(method="average")
            y = y.rank(method="average")
        if x.std(ddof=1) == 0 or y.std(ddof=1) == 0:
            continue
        corr = float(x.corr(y, method="pearson"))
        if np.isfinite(corr):
            out[dt] = corr
    return pd.Series(out, dtype=float, name="IC")


def newey_west_mean_tstat(series: pd.Series, *, lag: int) -> tuple[float, float, float]:
    """Newey-West HAC t-stat, SE, and two-sided asymptotic p-value for the mean."""
    if lag < 0:
        raise ValueError("Newey-West lag must be non-negative")
    x = series.to_numpy(dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    mean = float(np.mean(x))
    resid = x - mean
    gamma0 = float(np.dot(resid, resid) / n)
    hac = gamma0
    max_lag = min(lag, n - 1)
    for k in range(1, max_lag + 1):
        weight = 1.0 - k / (max_lag + 1)
        gamma = float(np.dot(resid[k:], resid[:-k]) / n)
        hac += 2.0 * weight * gamma
    if hac <= 0 or not np.isfinite(hac):
        return float("nan"), float("nan"), float("nan")
    se = float(np.sqrt(hac / n))
    if se == 0 or not np.isfinite(se):
        return float("nan"), se, float("nan")
    t_stat = mean / se
    # Asymptotic two-sided normal p-value.
    p_value = float(2.0 * stats.norm.sf(abs(t_stat)))
    return t_stat, se, p_value


def _quantile_labels(
    values: pd.Series,
    n_groups: int,
    *,
    tie_rule: str,
) -> tuple[pd.Series, bool]:
    if tie_rule not in {"average", "first", "dense", "min", "max"}:
        raise ValueError(f"unsupported tie_rule: {tie_rule}")
    n = len(values)
    unavailable = pd.Series(np.nan, index=values.index, dtype=float)
    if n < n_groups:
        return unavailable, False

    order = np.argsort(values.to_numpy(dtype=float), kind="mergesort")
    sorted_vals = values.to_numpy(dtype=float)[order]
    labels = np.full(n, np.nan, dtype=float)

    if tie_rule == "first":
        sizes = [n // n_groups] * n_groups
        for i in range(n % n_groups):
            sizes[-(i + 1)] += 1
        start = 0
        for gid, size in enumerate(sizes, start=1):
            end = start + size
            labels[order[start:end]] = gid
            start = end
        return pd.Series(labels, index=values.index), True

    runs: list[tuple[int, int]] = []
    start = 0
    while start < n:
        end = start + 1
        while end < n and sorted_vals[end] == sorted_vals[start]:
            end += 1
        runs.append((start, end))
        start = end
    if len(runs) < n_groups:
        return unavailable, False

    run_sizes = [e - s for s, e in runs]
    cum = np.cumsum(run_sizes)
    cut_ends: list[int] = []
    prev_end = -1
    for g in range(1, n_groups + 1):
        target = g * n / n_groups
        min_end = prev_end + 1
        max_end = len(runs) - (n_groups - g) - 1
        if min_end > max_end:
            return unavailable, False
        best = min(range(min_end, max_end + 1), key=lambda i: abs(float(cum[i]) - target))
        cut_ends.append(best)
        prev_end = best

    prev = 0
    for g_id, end_run in enumerate(cut_ends, start=1):
        for run_i in range(prev, end_run + 1):
            rs, re = runs[run_i]
            labels[order[rs:re]] = g_id
        prev = end_run + 1
    return pd.Series(labels, index=values.index), True


def _rebalance_dates(dates: pd.DatetimeIndex | list[Any], rebalance: str) -> list[Any]:
    ordered = pd.DatetimeIndex(pd.to_datetime(pd.Index(dates))).sort_values().unique()
    if rebalance == "daily":
        return list(ordered)
    if rebalance == "weekly":
        frame = pd.DataFrame({"dt": ordered})
        frame["key"] = frame["dt"].dt.isocalendar().week.astype(int) + frame[
            "dt"
        ].dt.isocalendar().year.astype(int) * 100
        return list(frame.groupby("key", sort=True)["dt"].max())
    if rebalance == "monthly":
        frame = pd.DataFrame({"dt": ordered})
        frame["key"] = frame["dt"].dt.to_period("M").astype(str)
        return list(frame.groupby("key", sort=True)["dt"].max())
    raise ValueError(f"unsupported rebalance: {rebalance}")


def formal_trading_supported(protocol: ProtocolSnapshot) -> tuple[bool, str | None]:
    if protocol.horizon_bars != 1:
        return False, "horizon_holding_not_representable_by_vector_backtester"
    if protocol.return_mode not in {"forward", "backward"}:
        return False, "unsupported_return_mode"
    if protocol.trade_at not in {"open", "close"}:
        return False, "unsupported_trade_at"
    return True, None


def compute_predictive_metrics(
    panel: pd.DataFrame,
    values: pd.Series,
    protocol: ProtocolSnapshot,
) -> tuple[list[Finding], list[MetricResult], list[UncertaintyResult], dict[str, Any]]:
    findings, frame = _working_frame(panel, values, protocol)
    tables: dict[str, Any] = {
        "return_label": {
            "formula": (
                "forward: P[t+L+H]/P[t+L]-1; backward: P[t+L]/P[t+L-H]-1"
            ),
            "trade_at": protocol.trade_at,
            "signal_lag": protocol.signal_lag,
            "return_mode": protocol.return_mode,
            "horizon_bars": protocol.horizon_bars,
        }
    }
    metrics: list[MetricResult] = []
    uncertainty: list[UncertaintyResult] = []
    if frame is None:
        return findings, metrics, uncertainty, tables

    future = execution_aligned_returns(frame["price"], protocol)
    factor = frame["fac_val"]
    if protocol.direction == "long_low":
        factor = -factor

    pearson_ic = _cross_section_corr(
        factor, future, rank=False, min_cross_section=protocol.min_cross_section
    )
    rank_ic = _cross_section_corr(
        factor, future, rank=True, min_cross_section=protocol.min_cross_section
    )
    tables["pearson_ic"] = {
        str(k): (None if pd.isna(v) else float(v)) for k, v in pearson_ic.items()
    }
    tables["rank_ic"] = {
        str(k): (None if pd.isna(v) else float(v)) for k, v in rank_ic.items()
    }

    sample_range = (
        f"horizon={protocol.horizon_bars};lag={protocol.signal_lag};"
        f"trade_at={protocol.trade_at};mode={protocol.return_mode}"
    )
    overlapping = protocol.horizon_bars > 1
    hac_lag = max(protocol.horizon_bars - 1, 0)

    def _summarize(ic: pd.Series, prefix: str) -> None:
        if len(ic) < protocol.min_ic_samples:
            reason = (
                "insufficient_ic_samples"
                if len(ic) > 0
                else "no_valid_cross_section_or_constant_factor"
            )
            for name in (
                f"{prefix}_mean", f"{prefix}_std", f"{prefix}_ir",
                f"{prefix}_t_stat", f"{prefix}_p_value",
                f"{prefix}_hac_t_stat", f"{prefix}_hac_p_value",
                f"{prefix}_positive_ratio", f"{prefix}_count",
            ):
                metrics.append(
                    _metric(
                        name, None,
                        unit="ratio" if "ratio" in name or name.endswith("_ir")
                        else "count" if name.endswith("_count")
                        else "stat" if "t_stat" in name or "p_value" in name
                        else "ic",
                        sample_range=sample_range,
                        unavailable_reason=reason,
                    )
                )
            findings.append(
                _finding(
                    "EVALUATION_INSUFFICIENT_SAMPLE",
                    passed=False,
                    severity=FindingSeverity.SOFT_FAIL,
                    message=f"{prefix} unavailable: {reason}",
                    details={"count": int(len(ic))},
                )
            )
            return
        mean = float(ic.mean())
        std = float(ic.std(ddof=1)) if len(ic) > 1 else float("nan")
        ir = mean / std if std and np.isfinite(std) and std != 0 else None
        metrics.extend(
            [
                _metric(f"{prefix}_mean", mean, unit="ic", sample_range=sample_range),
                _metric(
                    f"{prefix}_std",
                    float(std) if np.isfinite(std) else None,
                    unit="ic", sample_range=sample_range,
                    unavailable_reason=None if np.isfinite(std) else "undefined_std",
                ),
                _metric(
                    f"{prefix}_ir",
                    float(ir) if ir is not None and np.isfinite(ir) else None,
                    unit="ratio", sample_range=sample_range,
                    unavailable_reason=None if ir is not None and np.isfinite(ir) else "undefined_ir",
                ),
            ]
        )
        if overlapping:
            metrics.append(
                _metric(
                    f"{prefix}_t_stat", None, unit="stat", sample_range=sample_range,
                    unavailable_reason="overlapping_horizon_iid_unavailable",
                )
            )
            metrics.append(
                _metric(
                    f"{prefix}_p_value", None, unit="p", sample_range=sample_range,
                    unavailable_reason="overlapping_horizon_iid_unavailable",
                )
            )
            hac_t, hac_se, hac_p = newey_west_mean_tstat(ic, lag=hac_lag)
            metrics.append(
                _metric(
                    f"{prefix}_hac_t_stat",
                    float(hac_t) if np.isfinite(hac_t) else None,
                    unit="stat", sample_range=sample_range,
                    unavailable_reason=None if np.isfinite(hac_t) else "undefined_hac_t",
                )
            )
            metrics.append(
                _metric(
                    f"{prefix}_hac_p_value",
                    float(hac_p) if np.isfinite(hac_p) else None,
                    unit="p", sample_range=sample_range,
                    unavailable_reason=None if np.isfinite(hac_p) else "undefined_hac_p",
                )
            )
            uncertainty.append(
                UncertaintyResult(
                    name=f"{prefix}_mean_significance",
                    method="newey_west_hac",
                    estimates={
                        "lag": hac_lag,
                        "t_stat": None if not np.isfinite(hac_t) else float(hac_t),
                        "se": None if not np.isfinite(hac_se) else float(hac_se),
                        "p_value": None if not np.isfinite(hac_p) else float(hac_p),
                        "horizon_bars": protocol.horizon_bars,
                    },
                )
            )
        else:
            t_stat, p_value = stats.ttest_1samp(ic.to_numpy(dtype=float), 0.0)
            metrics.append(
                _metric(
                    f"{prefix}_t_stat",
                    float(t_stat) if np.isfinite(t_stat) else None,
                    unit="stat", sample_range=sample_range,
                    unavailable_reason=None if np.isfinite(t_stat) else "undefined_t",
                )
            )
            metrics.append(
                _metric(
                    f"{prefix}_p_value",
                    float(p_value) if np.isfinite(p_value) else None,
                    unit="p", sample_range=sample_range,
                    unavailable_reason=None if np.isfinite(p_value) else "undefined_p",
                )
            )
            metrics.append(
                _metric(
                    f"{prefix}_hac_t_stat", None, unit="stat", sample_range=sample_range,
                    unavailable_reason="not_required_for_horizon_1",
                )
            )
            metrics.append(
                _metric(
                    f"{prefix}_hac_p_value", None, unit="p", sample_range=sample_range,
                    unavailable_reason="not_required_for_horizon_1",
                )
            )
            uncertainty.append(
                UncertaintyResult(
                    name=f"{prefix}_mean_significance",
                    method="iid_t_test",
                    estimates={
                        "t_stat": None if not np.isfinite(t_stat) else float(t_stat),
                        "p_value": None if not np.isfinite(p_value) else float(p_value),
                        "horizon_bars": protocol.horizon_bars,
                    },
                )
            )
        metrics.append(
            _metric(f"{prefix}_positive_ratio", float((ic > 0).mean()), unit="ratio", sample_range=sample_range)
        )
        metrics.append(
            _metric(f"{prefix}_count", int(len(ic)), unit="count", sample_range=sample_range)
        )

    _summarize(pearson_ic, "pearson_ic")
    _summarize(rank_ic, "rank_ic")

    tables["ic_decay"] = {}
    for decay_h in protocol.ic_decay_horizons:
        decay_proto = replace(
            protocol,
            horizon_bars=int(decay_h),
            ic_decay_horizons=(int(decay_h),),
        )
        fut_h = execution_aligned_returns(frame["price"], decay_proto)
        ic_h = _cross_section_corr(
            factor, fut_h, rank=True, min_cross_section=protocol.min_cross_section
        )
        key = f"rank_ic_decay_horizon_{decay_h}"
        if len(ic_h) < protocol.min_ic_samples:
            metrics.append(
                _metric(key, None, unit="ic", sample_range=f"horizon={decay_h}",
                        unavailable_reason="insufficient_ic_samples")
            )
            tables["ic_decay"][str(decay_h)] = None
        else:
            mean_h = float(ic_h.mean())
            metrics.append(_metric(key, mean_h, unit="ic", sample_range=f"horizon={decay_h}"))
            tables["ic_decay"][str(decay_h)] = mean_h

    merged = pd.concat(
        [factor.rename("factor"), future.rename("future_return")], axis=1
    ).dropna()
    group_returns: dict[int, list[float]] = {i: [] for i in range(1, protocol.n_groups + 1)}
    weight_turnovers: list[float] = []
    unavailable_rebals = 0
    prev_weights: pd.Series | None = None
    dates = sorted(merged.index.get_level_values("eob").unique())
    try:
        rebalance_dates = _rebalance_dates(dates, protocol.rebalance)
    except (TypeError, ValueError) as exc:
        findings.append(
            _finding(
                "EVALUATION_REBALANCE_DATES",
                passed=False,
                message="could not derive rebalance dates",
                details={"cause_type": type(exc).__name__},
            )
        )
        rebalance_dates = []
    tables["rebalance_dates"] = [str(d) for d in rebalance_dates]
    for dt in rebalance_dates:
        try:
            cross = merged.xs(dt, level="eob")
        except KeyError:
            continue
        if len(cross) < protocol.n_groups or len(cross) < protocol.min_cross_section:
            unavailable_rebals += 1
            continue
        if cross["factor"].nunique(dropna=True) < 2:
            unavailable_rebals += 1
            continue
        labels, ok = _quantile_labels(
            cross["factor"], protocol.n_groups, tie_rule=protocol.tie_rule
        )
        if not ok:
            unavailable_rebals += 1
            continue
        labeled = cross.assign(group=labels).dropna(subset=["group"])
        for gid, part in labeled.groupby("group"):
            group_returns[int(gid)].append(float(part["future_return"].mean()))
        # Canonical equal-weight group portfolio weights on this cross-section.
        w = pd.Series(0.0, index=labeled.index)
        top = labeled.index[labeled["group"] == protocol.n_groups]
        bottom = labeled.index[labeled["group"] == 1]
        if len(top):
            w.loc[top] = 1.0 / len(top)
        if protocol.allow_short and len(bottom):
            w.loc[bottom] = -1.0 / len(bottom)
        if prev_weights is not None:
            union = prev_weights.index.union(w.index)
            delta = w.reindex(union).fillna(0.0) - prev_weights.reindex(union).fillna(0.0)
            weight_turnovers.append(float(0.5 * delta.abs().sum()))
        prev_weights = w

    if unavailable_rebals:
        findings.append(
            _finding(
                "EVALUATION_QUANTILE_UNAVAILABLE",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message="some rebalance dates could not form exact n_groups under tie rule",
                details={"unavailable_rebalances": unavailable_rebals},
            )
        )

    mean_by_group: dict[str, float | None] = {}
    for gid, rets in group_returns.items():
        key = f"quantile_{gid}_mean_return"
        if not rets:
            metrics.append(
                _metric(key, None, unit="return", sample_range=sample_range,
                        unavailable_reason="insufficient_quantile_samples")
            )
            mean_by_group[str(gid)] = None
        else:
            mean_ret = float(np.mean(rets))
            metrics.append(_metric(key, mean_ret, unit="return", sample_range=sample_range))
            mean_by_group[str(gid)] = mean_ret
    tables["quantile_mean_returns"] = mean_by_group

    finite_means = [v for v in mean_by_group.values() if v is not None]
    if len(finite_means) >= 2:
        ordered = [
            mean_by_group[str(i)]
            for i in range(1, protocol.n_groups + 1)
            if mean_by_group.get(str(i)) is not None
        ]
        if len(ordered) >= 2:
            mono = float(
                pd.Series(ordered).corr(
                    pd.Series(range(1, len(ordered) + 1), dtype=float), method="spearman"
                )
            )
            metrics.append(
                _metric(
                    "quantile_monotonicity",
                    mono if np.isfinite(mono) else None,
                    unit="corr", sample_range=sample_range,
                    unavailable_reason=None if np.isfinite(mono) else "undefined",
                )
            )
        top = mean_by_group.get(str(protocol.n_groups))
        bottom = mean_by_group.get("1")
        if top is not None and bottom is not None:
            metrics.append(
                _metric("long_short_spread", float(top - bottom), unit="return", sample_range=sample_range)
            )
        else:
            metrics.append(
                _metric("long_short_spread", None, unit="return", sample_range=sample_range,
                        unavailable_reason="missing_extreme_quantiles")
            )
    else:
        metrics.append(
            _metric("quantile_monotonicity", None, unit="corr", sample_range=sample_range,
                    unavailable_reason="insufficient_quantile_samples")
        )
        metrics.append(
            _metric("long_short_spread", None, unit="return", sample_range=sample_range,
                    unavailable_reason="insufficient_quantile_samples")
        )

    if weight_turnovers:
        metrics.append(
            _metric(
                "group_turnover_mean",
                float(np.mean(weight_turnovers)),
                unit="ratio",
                sample_range=sample_range,
            )
        )
        tables["group_turnover"] = [float(x) for x in weight_turnovers]
        tables["group_turnover_definition"] = "0.5*sum(|delta equal-weight group portfolio weights|)"
    else:
        metrics.append(
            _metric(
                "group_turnover_mean", None, unit="ratio", sample_range=sample_range,
                unavailable_reason="insufficient_rebalance_pairs",
            )
        )

    findings.append(
        _finding(
            "EVALUATION_PREDICTIVE_COMPLETE",
            passed=True,
            severity=FindingSeverity.INFO,
            message="predictive metrics computed with execution-aligned labels",
        )
    )
    return findings, metrics, uncertainty, tables


def build_long_short_weights(
    values: pd.Series,
    protocol: ProtocolSnapshot,
    *,
    calendar: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    work = values.copy(deep=True)
    if list(work.index.names) != ["symbol", "eob"]:
        raise ValueError("build_long_short_weights requires working names ['symbol','eob']")
    factor = work.unstack("symbol")
    if protocol.direction == "long_low":
        factor = -factor
    if calendar is None:
        calendar = pd.DatetimeIndex(pd.to_datetime(pd.Index(factor.index)))
    rebalance_ts = {pd.Timestamp(x) for x in _rebalance_dates(list(calendar), protocol.rebalance)}
    weights = pd.DataFrame(np.nan, index=factor.index, columns=factor.columns)
    for dt, row in factor.iterrows():
        if pd.Timestamp(dt) not in rebalance_ts:
            continue
        clean = row.dropna()
        if len(clean) < protocol.n_groups or clean.nunique() < 2:
            continue
        labels, ok = _quantile_labels(clean, protocol.n_groups, tie_rule=protocol.tie_rule)
        if not ok:
            continue
        top = labels[labels == protocol.n_groups].index
        bottom = labels[labels == 1].index
        if len(top) == 0:
            continue
        weights.loc[dt, :] = 0.0
        weights.loc[dt, top] = 1.0 / len(top)
        if protocol.allow_short:
            if len(bottom) == 0:
                continue
            weights.loc[dt, bottom] = -1.0 / len(bottom)
    return weights


def run_formal_backtest(
    panel: pd.DataFrame,
    values: pd.Series,
    protocol: ProtocolSnapshot,
    *,
    backtester_factory: BacktesterFactory | None = None,
) -> tuple[list[Finding], list[MetricResult], dict[str, Any]]:
    findings: list[Finding] = []
    metrics: list[MetricResult] = []
    tables: dict[str, Any] = {
        "protocol": {
            "trade_at": protocol.trade_at,
            "signal_lag": protocol.signal_lag,
            "return_mode": protocol.return_mode,
            "rebalance": protocol.rebalance,
            "horizon_bars": protocol.horizon_bars,
            "allow_short": protocol.allow_short,
        },
        "return_label_alignment": "same as execution_aligned_returns / predictive",
    }
    supported, reason = formal_trading_supported(protocol)
    if not supported:
        findings.append(
            _finding(
                "BACKTEST_PROTOCOL_UNSUPPORTED",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message="formal trading unavailable for this protocol under VectorBacktester",
                details={"reason": reason},
            )
        )
        metrics.append(
            _metric(
                "backtest_total_return", None, unit="return", sample_range="trading",
                unavailable_reason=reason or "protocol_unsupported",
            )
        )
        return findings, metrics, tables

    level_findings, frame = _working_frame(panel, values, protocol)
    findings.extend(level_findings)
    if frame is None:
        findings.append(
            _finding("BACKTEST_INPUT_INVALID", passed=False, message="cannot build backtest inputs")
        )
        return findings, metrics, tables

    trade_col = protocol.trade_at
    raw_weights = build_long_short_weights(frame["fac_val"], protocol)
    weights = raw_weights.ffill().fillna(0.0)
    tables["rebalance_weight_dates"] = [
        str(idx) for idx, row in raw_weights.iterrows() if row.notna().any()
    ]
    if weights.abs().sum().sum() == 0:
        metrics.append(
            _metric(
                "backtest_total_return", None, unit="return", sample_range="trading",
                unavailable_reason="empty_weights",
            )
        )
        findings.append(
            _finding(
                "BACKTEST_EMPTY_WEIGHTS",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message="no tradable quantile weights",
            )
        )
        return findings, metrics, tables

    factory = backtester_factory or VectorBacktester
    slippage_bp = float(protocol.slippage) * 10_000.0
    try:
        data = frame[[trade_col]].copy(deep=True)
        if trade_col != "close" and "close" in frame.columns:
            data["close"] = frame["close"]
        data.index = data.index.set_names(["symbol", "eob"])
        engine = factory(
            data,
            trade_at=protocol.trade_at,
            signal_lag=int(protocol.signal_lag),
            commission=float(protocol.commission),
            slippage_bp=slippage_bp,
            return_mode=protocol.return_mode,
        )
        result = engine.run(weights)
    except Exception as exc:  # noqa: BLE001
        findings.append(
            _finding(
                "BACKTEST_FAILED",
                passed=False,
                message="VectorBacktester run failed",
                details={"cause_type": type(exc).__name__},
            )
        )
        return findings, metrics, tables

    bt_metrics = getattr(result, "metrics", {}) or {}
    for key in sorted(bt_metrics):
        value = bt_metrics[key]
        if isinstance(value, (int, float, bool, str)) or value is None:
            if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
                metrics.append(
                    _metric(
                        f"backtest_{key}", None, unit="metric", sample_range="trading",
                        unavailable_reason="non_finite",
                    )
                )
            else:
                metrics.append(
                    _metric(f"backtest_{key}", value, unit="metric", sample_range="trading")
                )
    tables["backtest_metrics"] = {
        str(k): bt_metrics[k]
        for k in sorted(bt_metrics)
        if isinstance(bt_metrics[k], (int, float, str, bool)) or bt_metrics[k] is None
    }
    findings.append(
        _finding(
            "BACKTEST_COMPLETE",
            passed=True,
            severity=FindingSeverity.INFO,
            message="formal backtest completed via VectorBacktester",
            details={
                "trade_at": protocol.trade_at,
                "signal_lag": protocol.signal_lag,
                "return_mode": protocol.return_mode,
                "rebalance": protocol.rebalance,
            },
        )
    )
    return findings, metrics, tables


__all__ = [
    "BacktesterFactory",
    "build_long_short_weights",
    "compute_predictive_metrics",
    "execution_aligned_returns",
    "formal_trading_supported",
    "newey_west_mean_tstat",
    "run_formal_backtest",
]
