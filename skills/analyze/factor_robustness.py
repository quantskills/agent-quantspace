"""Deterministic robustness checks with fixed seeds and preregistered neighborhoods."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from skills.analyze.attribution_robustness import (
    block_bootstrap_metric,
    deflated_sharpe_ratio,
    pbo_from_candidate_returns,
)
from skills.analyze.attribution_stat_tests import hansen_spa_test
from skills.analyze.contracts import (
    Finding,
    FindingSeverity,
    MetricResult,
    ProtocolSnapshot,
    UncertaintyResult,
)
from skills.analyze.factor_evaluation import compute_predictive_metrics
from skills.analyze.validation import identify_levels


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
    return MetricResult(
        name=name,
        value=None if unavailable_reason else value,
        unit=unit,
        sample_range=sample_range,
        unavailable_reason=unavailable_reason,
    )


def _ic_series_from_tables(tables: Mapping[str, Any], key: str) -> pd.Series:
    raw = tables.get(key) or {}
    if not isinstance(raw, Mapping) or not raw:
        return pd.Series(dtype=float)
    idx = list(raw.keys())
    vals = [np.nan if raw[k] is None else float(raw[k]) for k in idx]
    return pd.Series(vals, index=pd.Index(idx), dtype=float).dropna()


def compute_robustness(
    panel: pd.DataFrame,
    values: pd.Series,
    protocol: ProtocolSnapshot,
    *,
    regime_masks: Mapping[str, pd.Series] | None = None,
    time_subsample_masks: Mapping[str, pd.Series] | None = None,
    parameter_outputs: Mapping[str, pd.Series] | None = None,
    liquidity_scores: pd.Series | None = None,
    volatility_scores: pd.Series | None = None,
    formal_returns: pd.Series | None = None,
    candidate_returns: pd.DataFrame | None = None,
) -> tuple[list[Finding], list[MetricResult], list[UncertaintyResult], dict[str, Any]]:
    """Robustness diagnostics.

    DSR/PBO/SPA require explicit formal/candidate return matrices — never a single
    IC series used as a returns proxy.
    """
    findings: list[Finding] = []
    metrics: list[MetricResult] = []
    uncertainty: list[UncertaintyResult] = []
    tables: dict[str, Any] = {}

    _, _, _, base_tables = compute_predictive_metrics(panel, values, protocol)
    rank_ic = _ic_series_from_tables(base_tables, "rank_ic")
    tables["base_rank_ic"] = base_tables.get("rank_ic", {})

    # Time halves.
    if len(rank_ic) >= protocol.min_ic_samples * 2:
        mid = len(rank_ic) // 2
        metrics.append(
            _metric(
                "robustness_rank_ic_first_half_mean",
                float(rank_ic.iloc[:mid].mean()),
                unit="ic",
                sample_range="time_half",
            )
        )
        metrics.append(
            _metric(
                "robustness_rank_ic_second_half_mean",
                float(rank_ic.iloc[mid:].mean()),
                unit="ic",
                sample_range="time_half",
            )
        )
    else:
        for name in (
            "robustness_rank_ic_first_half_mean",
            "robustness_rank_ic_second_half_mean",
        ):
            metrics.append(
                _metric(
                    name,
                    None,
                    unit="ic",
                    sample_range="time_half",
                    unavailable_reason="insufficient_ic_samples",
                )
            )

    window = max(5, protocol.min_ic_samples)
    if len(rank_ic) >= window:
        rolling = rank_ic.rolling(window).mean().dropna()
        tables["rolling_rank_ic_mean"] = {str(k): float(v) for k, v in rolling.items()}
        metrics.append(
            _metric(
                "robustness_rolling_rank_ic_mean",
                float(rolling.mean()),
                unit="ic",
                sample_range=f"rolling_{window}",
            )
        )
    else:
        metrics.append(
            _metric(
                "robustness_rolling_rank_ic_mean",
                None,
                unit="ic",
                sample_range=f"rolling_{window}",
                unavailable_reason="insufficient_ic_samples",
            )
        )

    # Regime slices: exact registered keyset only.
    provided = set(regime_masks or {})
    expected = set(protocol.regimes)
    extra = sorted(provided - expected)
    missing = sorted(expected - provided)
    if extra:
        findings.append(
            _finding(
                "ROBUSTNESS_REGIME_POSTHOC_FORBIDDEN",
                passed=False,
                message="unregistered regime masks are forbidden",
                details={"extra": extra, "expected": sorted(expected)},
            )
        )
    if missing:
        findings.append(
            _finding(
                "ROBUSTNESS_REGIME_UNAVAILABLE",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message="registered regime masks missing",
                details={"missing": missing},
            )
        )
        for regime in missing:
            metrics.append(
                _metric(
                    f"robustness_regime_{regime}_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range=f"regime:{regime}",
                    unavailable_reason="regime_mask_missing",
                )
            )
    for regime in sorted(expected & provided):
        mask = regime_masks[regime]  # type: ignore[index]
        if not isinstance(mask, pd.Series) or not mask.index.equals(values.index):
            findings.append(
                _finding(
                    "ROBUSTNESS_REGIME_MASK_MISALIGNED",
                    passed=False,
                    severity=FindingSeverity.SOFT_FAIL,
                    message=f"regime mask {regime!r} misaligned with values",
                )
            )
            metrics.append(
                _metric(
                    f"robustness_regime_{regime}_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range=f"regime:{regime}",
                    unavailable_reason="regime_mask_misaligned",
                )
            )
            continue
        masked_values = values.where(mask.astype(bool))
        _, _, _, regime_tables = compute_predictive_metrics(panel, masked_values, protocol)
        regime_ic = _ic_series_from_tables(regime_tables, "rank_ic")
        if len(regime_ic) < protocol.min_ic_samples:
            metrics.append(
                _metric(
                    f"robustness_regime_{regime}_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range=f"regime:{regime}",
                    unavailable_reason="insufficient_ic_samples",
                )
            )
        else:
            metrics.append(
                _metric(
                    f"robustness_regime_{regime}_rank_ic_mean",
                    float(regime_ic.mean()),
                    unit="ic",
                    sample_range=f"regime:{regime}",
                )
            )

    # Time subsamples: exact registered keyset only.
    ts_provided = set(time_subsample_masks or {})
    ts_expected = set(protocol.time_subsamples)
    ts_extra = sorted(ts_provided - ts_expected)
    ts_missing = sorted(ts_expected - ts_provided)
    if ts_extra:
        findings.append(
            _finding(
                "ROBUSTNESS_TIME_SUBSAMPLE_POSTHOC_FORBIDDEN",
                passed=False,
                message="unregistered time_subsample masks are forbidden",
                details={"extra": ts_extra, "expected": sorted(ts_expected)},
            )
        )
    if ts_missing:
        findings.append(
            _finding(
                "ROBUSTNESS_TIME_SUBSAMPLE_UNAVAILABLE",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message="registered time_subsample masks missing",
                details={"missing": ts_missing},
            )
        )
        for label in ts_missing:
            metrics.append(
                _metric(
                    f"robustness_time_{label}_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range=f"time:{label}",
                    unavailable_reason="time_subsample_mask_missing",
                )
            )
    for label in sorted(ts_expected & ts_provided):
        mask = time_subsample_masks[label]  # type: ignore[index]
        if not isinstance(mask, pd.Series) or not mask.index.equals(values.index):
            findings.append(
                _finding(
                    "ROBUSTNESS_TIME_SUBSAMPLE_MISALIGNED",
                    passed=False,
                    severity=FindingSeverity.SOFT_FAIL,
                    message=f"time_subsample mask {label!r} misaligned with values",
                )
            )
            metrics.append(
                _metric(
                    f"robustness_time_{label}_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range=f"time:{label}",
                    unavailable_reason="time_subsample_mask_misaligned",
                )
            )
            continue
        masked_values = values.where(mask.astype(bool))
        _, _, _, ts_tables = compute_predictive_metrics(panel, masked_values, protocol)
        ts_ic = _ic_series_from_tables(ts_tables, "rank_ic")
        if len(ts_ic) < protocol.min_ic_samples:
            metrics.append(
                _metric(
                    f"robustness_time_{label}_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range=f"time:{label}",
                    unavailable_reason="insufficient_ic_samples",
                )
            )
        else:
            metrics.append(
                _metric(
                    f"robustness_time_{label}_rank_ic_mean",
                    float(ts_ic.mean()),
                    unit="ic",
                    sample_range=f"time:{label}",
                )
            )

    # Symbol leave-one-out dispersion.
    _f, symbol_pos, _dt = identify_levels(values.index, protocol)
    if symbol_pos is None:
        metrics.append(
            _metric(
                "robustness_symbol_loo_rank_ic_std",
                None,
                unit="ic",
                sample_range="symbol_loo",
                unavailable_reason="symbol_level_unresolved",
            )
        )
    else:
        symbols = sorted({str(s) for s in values.index.get_level_values(symbol_pos)})
        loo_means: list[float] = []
        if len(symbols) >= 2 and len(rank_ic) >= protocol.min_ic_samples:
            sym_level = values.index.names[symbol_pos]
            for symbol in symbols:
                if sym_level is None:
                    mask = values.index.get_level_values(symbol_pos) != symbol
                else:
                    mask = values.index.get_level_values(sym_level) != symbol
                subset = values.where(mask)
                _, _, _, t = compute_predictive_metrics(panel, subset, protocol)
                ic = _ic_series_from_tables(t, "rank_ic")
                if len(ic) >= protocol.min_ic_samples:
                    loo_means.append(float(ic.mean()))
        if len(loo_means) >= 2:
            metrics.append(
                _metric(
                    "robustness_symbol_loo_rank_ic_std",
                    float(np.std(loo_means, ddof=1)),
                    unit="ic",
                    sample_range="symbol_loo",
                )
            )
        else:
            metrics.append(
                _metric(
                    "robustness_symbol_loo_rank_ic_std",
                    None,
                    unit="ic",
                    sample_range="symbol_loo",
                    unavailable_reason="insufficient_symbol_slices",
                )
            )

    def _score_slice(scores: pd.Series | None, label: str) -> None:
        if scores is None:
            metrics.append(
                _metric(
                    f"robustness_{label}_high_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range=label,
                    unavailable_reason=f"{label}_scores_missing",
                )
            )
            metrics.append(
                _metric(
                    f"robustness_{label}_low_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range=label,
                    unavailable_reason=f"{label}_scores_missing",
                )
            )
            return
        if not scores.index.equals(values.index):
            findings.append(
                _finding(
                    "ROBUSTNESS_SCORE_MISALIGNED",
                    passed=False,
                    severity=FindingSeverity.SOFT_FAIL,
                    message=f"{label} scores misaligned with values",
                    details={"label": label},
                )
            )
            return
        median = float(scores.median())
        for side, mask in (
            ("high", scores >= median),
            ("low", scores < median),
        ):
            subset = values.where(mask)
            _, _, _, t = compute_predictive_metrics(panel, subset, protocol)
            ic = _ic_series_from_tables(t, "rank_ic")
            key = f"robustness_{label}_{side}_rank_ic_mean"
            if len(ic) < protocol.min_ic_samples:
                metrics.append(
                    _metric(
                        key,
                        None,
                        unit="ic",
                        sample_range=label,
                        unavailable_reason="insufficient_ic_samples",
                    )
                )
            else:
                metrics.append(
                    _metric(key, float(ic.mean()), unit="ic", sample_range=label)
                )

    _score_slice(liquidity_scores, "liquidity")
    _score_slice(volatility_scores, "volatility")

    # Extreme-sample deletion: drop top/bottom 5% |factor| days' cross-sections.
    abs_fac = values.abs()
    if abs_fac.notna().sum() >= protocol.min_cross_section * protocol.min_ic_samples:
        lo, hi = abs_fac.quantile([0.05, 0.95])
        trimmed = values.where((abs_fac >= lo) & (abs_fac <= hi))
        _, _, _, t = compute_predictive_metrics(panel, trimmed, protocol)
        ic = _ic_series_from_tables(t, "rank_ic")
        if len(ic) < protocol.min_ic_samples:
            metrics.append(
                _metric(
                    "robustness_extreme_trim_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range="extreme_trim",
                    unavailable_reason="insufficient_ic_samples",
                )
            )
        else:
            metrics.append(
                _metric(
                    "robustness_extreme_trim_rank_ic_mean",
                    float(ic.mean()),
                    unit="ic",
                    sample_range="extreme_trim",
                )
            )
    else:
        metrics.append(
            _metric(
                "robustness_extreme_trim_rank_ic_mean",
                None,
                unit="ic",
                sample_range="extreme_trim",
                unavailable_reason="insufficient_samples",
            )
        )

    # Parameter neighborhood: exact registered labels only; never pick best / posthoc.
    neighborhood = dict(protocol.parameter_neighborhood)
    # Flatten registered labels as "param=value" for each preregistered point.
    registered_labels: set[str] = set()
    for key, values_t in neighborhood.items():
        for value in values_t:
            registered_labels.add(f"{key}={value}")
    provided_params = set(parameter_outputs or {})
    param_extra = sorted(provided_params - registered_labels)
    param_missing = sorted(registered_labels - provided_params)
    if param_extra:
        findings.append(
            _finding(
                "ROBUSTNESS_PARAM_POSTHOC_FORBIDDEN",
                passed=False,
                message="unregistered parameter outputs are forbidden",
                details={"extra": param_extra, "expected": sorted(registered_labels)},
            )
        )
    if registered_labels and param_missing:
        findings.append(
            _finding(
                "ROBUSTNESS_PARAM_NEIGHBORHOOD_UNAVAILABLE",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message="preregistered parameter neighborhood lacks injected outputs",
                details={"missing": param_missing},
            )
        )
        for label in param_missing:
            metrics.append(
                _metric(
                    f"robustness_param_{label}_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range=f"param:{label}",
                    unavailable_reason="parameter_output_missing",
                )
            )
    param_means: dict[str, float] = {}
    for label in sorted(registered_labels & provided_params):
        series = parameter_outputs[label]  # type: ignore[index]
        _, _, _, param_tables = compute_predictive_metrics(panel, series, protocol)
        pic = _ic_series_from_tables(param_tables, "rank_ic")
        if len(pic) < protocol.min_ic_samples:
            metrics.append(
                _metric(
                    f"robustness_param_{label}_rank_ic_mean",
                    None,
                    unit="ic",
                    sample_range=f"param:{label}",
                    unavailable_reason="insufficient_ic_samples",
                )
            )
        else:
            mean = float(pic.mean())
            param_means[label] = mean
            metrics.append(
                _metric(
                    f"robustness_param_{label}_rank_ic_mean",
                    mean,
                    unit="ic",
                    sample_range=f"param:{label}",
                )
            )
    tables["parameter_neighborhood_means"] = param_means
    tables["parameter_label_contract"] = "key=value for each preregistered neighborhood point"

    # Block bootstrap on rank IC mean with fixed seed (distribution of IC mean only).
    if len(rank_ic) >= max(protocol.bootstrap_block_size, protocol.min_ic_samples):
        try:
            boot = block_bootstrap_metric(
                rank_ic,
                metric_fn=lambda s: float(s.mean()),
                n_bootstrap=protocol.bootstrap_samples,
                block_size=protocol.bootstrap_block_size,
                random_state=protocol.random_seed,
            )
            uncertainty.append(
                UncertaintyResult(
                    name="rank_ic_mean_block_bootstrap",
                    method="block_bootstrap",
                    estimates={k: float(v) for k, v in boot.items()},
                )
            )
            metrics.append(
                _metric(
                    "robustness_bootstrap_rank_ic_mean",
                    float(boot["mean"]),
                    unit="ic",
                    sample_range="bootstrap",
                )
            )
        except Exception as exc:  # noqa: BLE001
            uncertainty.append(
                UncertaintyResult(
                    name="rank_ic_mean_block_bootstrap",
                    method="block_bootstrap",
                    estimates={},
                    unavailable_reason=type(exc).__name__,
                )
            )
            findings.append(
                _finding(
                    "ROBUSTNESS_BOOTSTRAP_FAILED",
                    passed=False,
                    severity=FindingSeverity.SOFT_FAIL,
                    message="block bootstrap failed",
                    details={"cause_type": type(exc).__name__},
                )
            )
    else:
        uncertainty.append(
            UncertaintyResult(
                name="rank_ic_mean_block_bootstrap",
                method="block_bootstrap",
                estimates={},
                unavailable_reason="insufficient_ic_samples",
            )
        )

    # DSR requires formal returns series (not IC proxy).
    if formal_returns is None:
        uncertainty.append(
            UncertaintyResult(
                name="deflated_sharpe_ratio",
                method="dsr",
                estimates={},
                unavailable_reason="formal_returns_missing",
            )
        )
    else:
        try:
            dsr = deflated_sharpe_ratio(
                formal_returns,
                n_trials=max(protocol.multiple_testing_budget, 1),
            )
            uncertainty.append(
                UncertaintyResult(
                    name="deflated_sharpe_ratio",
                    method="dsr",
                    estimates={
                        str(k): float(v)
                        for k, v in dsr.items()
                        if isinstance(v, (int, float)) and np.isfinite(v)
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            uncertainty.append(
                UncertaintyResult(
                    name="deflated_sharpe_ratio",
                    method="dsr",
                    estimates={},
                    unavailable_reason=type(exc).__name__,
                )
            )

    # PBO / SPA require multi-candidate return matrices.
    if candidate_returns is None or not isinstance(candidate_returns, pd.DataFrame):
        uncertainty.append(
            UncertaintyResult(
                name="pbo",
                method="pbo",
                estimates={},
                unavailable_reason="candidate_returns_missing",
            )
        )
        uncertainty.append(
            UncertaintyResult(
                name="hansen_spa",
                method="spa",
                estimates={},
                unavailable_reason="candidate_returns_missing",
            )
        )
    elif candidate_returns.shape[1] < 2:
        uncertainty.append(
            UncertaintyResult(
                name="pbo",
                method="pbo",
                estimates={},
                unavailable_reason="single_candidate_insufficient",
            )
        )
        uncertainty.append(
            UncertaintyResult(
                name="hansen_spa",
                method="spa",
                estimates={},
                unavailable_reason="single_candidate_insufficient",
            )
        )
    else:
        try:
            pbo = pbo_from_candidate_returns(candidate_returns)
            uncertainty.append(
                UncertaintyResult(
                    name="pbo",
                    method="pbo",
                    estimates={
                        str(k): float(v)
                        for k, v in pbo.items()
                        if isinstance(v, (int, float)) and np.isfinite(v)
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            uncertainty.append(
                UncertaintyResult(
                    name="pbo",
                    method="pbo",
                    estimates={},
                    unavailable_reason=type(exc).__name__,
                )
            )
        try:
            spa = hansen_spa_test(
                candidate_returns,
                n_bootstrap=min(100, protocol.bootstrap_samples),
                block_size=protocol.bootstrap_block_size,
                random_state=protocol.random_seed,
            )
            uncertainty.append(
                UncertaintyResult(
                    name="hansen_spa",
                    method="spa",
                    estimates={
                        str(k): float(v)
                        for k, v in spa.items()
                        if isinstance(v, (int, float)) and np.isfinite(v)
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            uncertainty.append(
                UncertaintyResult(
                    name="hansen_spa",
                    method="spa",
                    estimates={},
                    unavailable_reason=type(exc).__name__,
                )
            )

    findings.append(
        _finding(
            "ROBUSTNESS_COMPLETE",
            passed=True,
            severity=FindingSeverity.INFO,
            message="robustness section finished",
            details={"seed": protocol.random_seed},
        )
    )
    return findings, metrics, uncertainty, tables


__all__ = ["compute_robustness"]
