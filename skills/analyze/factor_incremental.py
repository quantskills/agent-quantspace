"""Explicit pool-incremental comparison (no global pool reads)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from skills.analyze.content_fingerprint import (
    fingerprint_frame,
    fingerprint_index,
    fingerprint_series,
)
from skills.analyze.contracts import (
    ENGINE_VERSION,
    Finding,
    FindingSeverity,
    FormalBacktestPair,
    MetricResult,
    PoolMemberSeries,
    ProtocolSnapshot,
    _register_formal_pair_digest,
    content_hash,
    formal_pair_issuance_digest,
    protocol_content_hash,
    verified_backtest_metrics,
)
from skills.analyze.factor_evaluation import (
    _cross_section_corr,
    _working_frame,
    execution_aligned_returns,
    formal_trading_supported,
)
from skills.analyze.validation import identify_levels
from skills.backtest import VectorBacktester


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


def _normalize_pool_sequence(
    pool: Mapping[str, pd.Series] | Sequence[PoolMemberSeries] | Sequence[Any] | None,
) -> list[tuple[str, pd.Series]]:
    if pool is None:
        return []
    if isinstance(pool, Mapping):
        return [(str(k), pool[k]) for k in sorted(pool.keys(), key=str)]
    out: list[tuple[str, pd.Series]] = []
    for i, item in enumerate(pool):
        if isinstance(item, PoolMemberSeries):
            out.append((str(item.ref_object_id), item.values))
        elif isinstance(item, tuple) and len(item) == 2:
            out.append((str(item[0]), item[1]))
        elif isinstance(item, pd.Series):
            out.append((f"member_{i}", item))
        else:
            raise TypeError("unsupported pool member type for formal pair")
    return out


def _ordered_pool_hash(
    pool: Mapping[str, pd.Series] | Sequence[PoolMemberSeries] | Sequence[Any] | None,
) -> str:
    members = _normalize_pool_sequence(pool)
    payload = [
        {"id": mid, "values": fingerprint_series(series)} for mid, series in members
    ]
    return content_hash(payload)


def _weights_hash(weights: pd.DataFrame) -> str:
    return fingerprint_frame(weights.astype("float64"))


def _build_backtest_data(
    panel: pd.DataFrame,
    candidate: pd.Series,
    protocol: ProtocolSnapshot,
) -> pd.DataFrame:
    findings, frame = _working_frame(panel, candidate, protocol)
    hard = [
        f for f in findings if (not f.passed) and f.severity is FindingSeverity.HARD_FAIL
    ]
    if frame is None or hard:
        raise ValueError("cannot build formal backtest panel frame")
    trade_col = protocol.trade_at
    data = frame[[trade_col]].copy(deep=True)
    if trade_col != "close" and "close" in frame.columns:
        data["close"] = frame["close"]
    data.index = data.index.set_names(["symbol", "eob"])
    return data


def _shared_sample_hash_from_index(index: pd.Index) -> str:
    return content_hash(
        {
            "kind": "formal_shared_sample",
            "index": fingerprint_index(index),
        }
    )


def run_official_formal_backtest_pair(
    panel: pd.DataFrame,
    protocol: ProtocolSnapshot,
    candidate: pd.Series,
    ordered_pool: Mapping[str, pd.Series] | Sequence[PoolMemberSeries] | Sequence[Any],
    *,
    before_weights: pd.DataFrame,
    after_weights: pd.DataFrame,
) -> FormalBacktestPair:
    """Official VectorBacktester formal-pair runner (only issuer of FormalBacktestPair).

    Explicit before/after target weights are required inputs and are hashed into
    the pair provenance and issuance digest. The runner always constructs
    ``VectorBacktester`` from this module (no caller factory injection). There
    is no helper that accepts caller-supplied ``BacktestResult`` objects.
    """
    if not isinstance(before_weights, pd.DataFrame) or not isinstance(
        after_weights, pd.DataFrame
    ):
        raise TypeError("before_weights/after_weights must be DataFrames")
    supported, reason = formal_trading_supported(protocol)
    if not supported:
        raise ValueError(reason or "formal trading unsupported")

    data = _build_backtest_data(panel, candidate, protocol)
    slippage_bp = float(protocol.slippage) * 10_000.0
    engine_kwargs = {
        "trade_at": protocol.trade_at,
        "signal_lag": int(protocol.signal_lag),
        "commission": float(protocol.commission),
        "slippage_bp": slippage_bp,
    }
    before = VectorBacktester(data.copy(deep=True), **engine_kwargs).run(before_weights)
    after = VectorBacktester(data.copy(deep=True), **engine_kwargs).run(after_weights)
    if before.result_df is None or after.result_df is None:
        raise ValueError("VectorBacktester returned empty result_df")
    if not before.result_df.index.equals(after.result_df.index):
        raise ValueError("before/after formal results must share the same sample index")

    shared = _shared_sample_hash_from_index(before.result_df.index)
    pair = object.__new__(FormalBacktestPair)
    object.__setattr__(pair, "before", before)
    object.__setattr__(pair, "after", after)
    object.__setattr__(pair, "protocol_content_hash", protocol_content_hash(protocol))
    object.__setattr__(pair, "panel_hash", fingerprint_frame(panel))
    object.__setattr__(pair, "candidate_hash", fingerprint_series(candidate))
    object.__setattr__(pair, "ordered_pool_hash", _ordered_pool_hash(ordered_pool))
    object.__setattr__(pair, "shared_sample_hash", shared)
    object.__setattr__(pair, "before_weights_hash", _weights_hash(before_weights))
    object.__setattr__(pair, "after_weights_hash", _weights_hash(after_weights))
    object.__setattr__(pair, "engine_version", ENGINE_VERSION)
    object.__setattr__(pair, "engine_name", "VectorBacktester")
    object.__setattr__(pair, "_frozen", True)
    _register_formal_pair_digest(formal_pair_issuance_digest(pair))
    return pair


def _formal_pair_binds_current_inputs(
    pair: FormalBacktestPair,
    *,
    panel: pd.DataFrame,
    candidate: pd.Series,
    pool: Mapping[str, pd.Series] | Sequence[PoolMemberSeries] | Sequence[Any] | None,
    protocol: ProtocolSnapshot,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(pair, FormalBacktestPair) or not pair.is_issued():
        errors.append("formal pair is not an issued official FormalBacktestPair")
        return errors
    if pair.protocol_content_hash != protocol_content_hash(protocol):
        errors.append("protocol_content_hash mismatch")
    if pair.panel_hash != fingerprint_frame(panel):
        errors.append("panel_hash mismatch")
    if pair.candidate_hash != fingerprint_series(candidate):
        errors.append("candidate_hash mismatch")
    if pair.ordered_pool_hash != _ordered_pool_hash(pool):
        errors.append("ordered_pool_hash mismatch")
    if pair.engine_version != ENGINE_VERSION:
        errors.append("engine_version mismatch")
    if pair.engine_name != "VectorBacktester":
        errors.append("engine_name mismatch")
    try:
        before_idx = pair.before.result_df.index
        after_idx = pair.after.result_df.index
    except Exception:  # noqa: BLE001
        errors.append("before/after result_df missing")
        return errors
    if not before_idx.equals(after_idx):
        errors.append("before/after shared sample index mismatch")
    expected_shared = _shared_sample_hash_from_index(before_idx)
    if pair.shared_sample_hash != expected_shared:
        errors.append("shared_sample_hash mismatch vs before/after result index")
    return errors


def _align_series_to_protocol(
    series: pd.Series,
    protocol: ProtocolSnapshot,
    *,
    member_name: str,
) -> tuple[list[Finding], pd.Series | None]:
    findings: list[Finding] = []
    if not isinstance(series.index, pd.MultiIndex) or series.index.nlevels != 2:
        findings.append(
            _finding(
                "POOL_INVALID_MEMBER_INDEX",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message=f"pool member {member_name!r} requires a two-level MultiIndex",
            )
        )
        return findings, None
    level_findings, symbol_pos, datetime_pos = identify_levels(series.index, protocol)
    hard = [
        f for f in level_findings
        if (not f.passed) and f.severity is FindingSeverity.HARD_FAIL
    ]
    if hard or symbol_pos is None or datetime_pos is None:
        findings.append(
            _finding(
                "POOL_MEMBER_LEVEL_MISMATCH",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message=f"pool member {member_name!r} index level names do not match protocol",
                details={"names": list(series.index.names)},
            )
        )
        return findings, None
    out = series.copy(deep=True)
    if symbol_pos != 0 or datetime_pos != 1:
        out = out.reorder_levels([symbol_pos, datetime_pos]).sort_index()
    else:
        out = out.sort_index()
    out.index = out.index.set_names(["symbol", "eob"])
    return findings, out


def _cs_ols(y: np.ndarray, x: np.ndarray) -> tuple[float | None, int, int]:
    """Return (R2, rank, residual_df). Requires n > n_params for honest in-sample R2."""
    n = len(y)
    if x.size == 0:
        design = np.ones((n, 1))
    elif x.ndim == 1:
        design = np.column_stack([np.ones(n), x.reshape(-1, 1)])
    else:
        design = np.column_stack([np.ones(n), x])
    n_params = design.shape[1]
    if n <= n_params:
        return None, 0, n - n_params
    try:
        beta, _resid, rank, _s = np.linalg.lstsq(design, y, rcond=None)
    except np.linalg.LinAlgError:
        return None, 0, n - n_params
    rank_i = int(rank)
    if rank_i < n_params:
        return None, rank_i, n - rank_i
    fitted = design @ beta
    ss_res = float(np.sum((y - fitted) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    if ss_tot <= 0 or not np.isfinite(ss_tot):
        return None, rank_i, n - rank_i
    return 1.0 - ss_res / ss_tot, rank_i, n - rank_i


def _partial_corr(y: np.ndarray, x: np.ndarray, z: np.ndarray) -> float | None:
    """Partial correlation of y and x controlling for columns of z (+intercept)."""
    n = len(y)
    if z.size == 0:
        design = np.ones((n, 1))
    elif z.ndim == 1:
        design = np.column_stack([np.ones(n), z.reshape(-1, 1)])
    else:
        design = np.column_stack([np.ones(n), z])
    if n <= design.shape[1] + 1:
        return None
    try:
        by, _, ry, _ = np.linalg.lstsq(design, y, rcond=None)
        bx, _, rx, _ = np.linalg.lstsq(design, x, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if int(ry) < design.shape[1] or int(rx) < design.shape[1]:
        return None
    ry_ = y - design @ by
    rx_ = x - design @ bx
    if float(np.std(ry_)) < 1e-12 or float(np.std(rx_)) < 1e-12:
        return None
    corr = float(np.corrcoef(ry_, rx_)[0, 1])
    return corr if np.isfinite(corr) else None


def compare_candidate_to_pool(
    panel: pd.DataFrame,
    candidate: pd.Series,
    pool: Mapping[str, pd.Series] | Sequence[PoolMemberSeries] | None,
    protocol: ProtocolSnapshot,
    *,
    formal_before_after: FormalBacktestPair | None = None,
) -> tuple[list[Finding], list[MetricResult], dict[str, Any]]:
    """Compare one candidate to an explicit pool.

    Directional predictive residual IC / conditional correlation / R2 use the
    protocol direction (long_low flips the candidate). Raw Pearson/Spearman
    redundancy correlations remain unsigned absolute-magnitude summaries of the
    raw candidate vs pool members.
    """
    findings: list[Finding] = []
    metrics: list[MetricResult] = []
    tables: dict[str, Any] = {
        "direction_policy": (
            "raw redundancy corr uses unsigned abs; residual IC / conditional "
            "corr / R2 use protocol.direction flip"
        )
    }
    sample_range = "pool"
    unavailable_names = (
        "pool_pearson_corr_max_abs",
        "pool_spearman_corr_max_abs",
        "pool_alignment_loss",
        "pool_finite_alignment_loss",
        "pool_joint_residual_rank_ic_mean",
        "pool_conditional_rank_corr_mean",
        "pool_joint_r2_before",
        "pool_joint_r2_after",
        "pool_joint_r2_delta",
        "pool_portfolio_return_delta",
        "pool_portfolio_drawdown_delta",
        "pool_portfolio_turnover_delta",
    )

    if pool is None or (hasattr(pool, "__len__") and len(pool) == 0):
        findings.append(
            _finding(
                "POOL_UNAVAILABLE",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message="existing factor pool is empty or missing",
                details={"reason": "empty_or_missing_pool"},
            )
        )
        for name in unavailable_names:
            metrics.append(
                _metric(
                    name, None,
                    unit="corr" if "corr" in name else "ic" if "ic" in name
                    else "r2" if "r2" in name else "ratio",
                    sample_range=sample_range,
                    unavailable_reason="pool_unavailable",
                )
            )
        return findings, metrics, tables

    findings_wf, frame = _working_frame(panel, candidate, protocol)
    hard = [
        f for f in findings_wf
        if (not f.passed) and f.severity is FindingSeverity.HARD_FAIL
    ]
    findings.extend(hard)
    if frame is None or hard:
        findings.append(
            _finding(
                "POOL_ALIGNMENT_FAILED",
                passed=False,
                message="candidate could not be aligned for pool comparison",
            )
        )
        return findings, metrics, tables

    cand_raw = frame["fac_val"].copy(deep=True)
    cand_dir = -cand_raw if protocol.direction == "long_low" else cand_raw
    future = execution_aligned_returns(frame["price"], protocol)

    # Normalize pool input to name -> Series.
    aligned_pool: dict[str, pd.Series] = {}
    pool_ref_meta: dict[str, Any] = {}
    if isinstance(pool, Mapping):
        iterable = [(str(k), pool[k], None) for k in sorted(pool)]
    else:
        iterable = []
        for member in pool:
            if not isinstance(member, PoolMemberSeries):
                findings.append(
                    _finding(
                        "POOL_INVALID_MEMBER",
                        passed=False,
                        severity=FindingSeverity.SOFT_FAIL,
                        message="pool member must be PoolMemberSeries when using bound refs",
                    )
                )
                continue
            iterable.append((member.ref_object_id, member.values, member))

    for name, other, meta in iterable:
        if not isinstance(other, pd.Series):
            findings.append(
                _finding(
                    "POOL_INVALID_MEMBER",
                    passed=False,
                    severity=FindingSeverity.SOFT_FAIL,
                    message=f"pool member {name!r} is not a Series",
                )
            )
            continue
        mem_findings, aligned = _align_series_to_protocol(
            other, protocol, member_name=name
        )
        findings.extend(mem_findings)
        if aligned is None:
            continue
        if name in aligned_pool:
            findings.append(
                _finding(
                    "POOL_DUPLICATE_MEMBER",
                    passed=False,
                    message=f"duplicate pool member id {name!r}",
                )
            )
            continue
        aligned_pool[name] = aligned
        if meta is not None:
            pool_ref_meta[name] = {
                "object_type": meta.ref_object_type,
                "object_id": meta.ref_object_id,
                "content_hash": meta.ref_content_hash,
                "namespace": meta.ref_namespace,
                "schema_version": meta.ref_schema_version,
            }

    if not aligned_pool:
        findings.append(
            _finding(
                "POOL_UNAVAILABLE",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message="no valid pool members after type/level checks",
            )
        )
        for name in unavailable_names:
            if name == "pool_alignment_loss":
                continue
            metrics.append(
                _metric(name, None, unit="ratio", sample_range=sample_range,
                        unavailable_reason="pool_unavailable")
            )
        return findings, metrics, tables

    tables["pool_refs"] = pool_ref_meta

    common = cand_raw.index
    for series in aligned_pool.values():
        common = common.intersection(series.index)
    index_alignment_loss = 1.0 - (len(common) / max(len(cand_raw.index), 1))
    metrics.append(
        _metric("pool_alignment_loss", float(index_alignment_loss), unit="ratio",
                sample_range=sample_range)
    )

    # Finite common sample across candidate + pool + future.
    pool_mat_full = pd.DataFrame(
        {name: aligned_pool[name].reindex(common).astype(float) for name in sorted(aligned_pool)}
    )
    cand_c = cand_raw.reindex(common).astype(float)
    fut_c = future.reindex(common).astype(float)
    finite_mask = (
        cand_c.notna()
        & fut_c.notna()
        & np.isfinite(cand_c.to_numpy(dtype=float))
        & np.isfinite(fut_c.to_numpy(dtype=float))
        & np.isfinite(pool_mat_full.to_numpy(dtype=float)).all(axis=1)
    )
    finite_common = cand_c.index[finite_mask.to_numpy()]
    finite_loss = 1.0 - (len(finite_common) / max(len(cand_raw.index), 1))
    metrics.append(
        _metric(
            "pool_finite_alignment_loss",
            float(finite_loss),
            unit="ratio",
            sample_range=sample_range,
        )
    )
    tables["finite_common_n"] = int(len(finite_common))

    if len(finite_common) < protocol.min_cross_section:
        for name in unavailable_names:
            if name in {"pool_alignment_loss", "pool_finite_alignment_loss"}:
                continue
            metrics.append(
                _metric(name, None, unit="ratio", sample_range=sample_range,
                        unavailable_reason="insufficient_common_sample")
            )
        return findings, metrics, tables

    cand_c = cand_raw.reindex(finite_common).astype(float)
    cand_d = cand_dir.reindex(finite_common).astype(float)
    fut_c = future.reindex(finite_common).astype(float)
    pool_mat = pd.DataFrame(
        {name: aligned_pool[name].reindex(finite_common).astype(float)
         for name in sorted(aligned_pool)}
    )

    # Raw redundancy correlations (unsigned max abs of mean daily corr).
    per_member: dict[str, Any] = {}
    pearson_abs = []
    spearman_abs = []
    for name in pool_mat.columns:
        daily_p, daily_s = [], []
        for _dt, group in pd.concat(
            [cand_c.rename("c"), pool_mat[name].rename("p")], axis=1
        ).groupby(level="eob"):
            g = group.dropna()
            if len(g) < protocol.min_cross_section:
                continue
            if g["c"].nunique() < 2 or g["p"].nunique() < 2:
                continue
            daily_p.append(float(g["c"].corr(g["p"], method="pearson")))
            daily_s.append(float(g["c"].corr(g["p"], method="spearman")))
        p_mean = float(np.mean(daily_p)) if daily_p else None
        s_mean = float(np.mean(daily_s)) if daily_s else None
        per_member[name] = {"pearson": p_mean, "spearman": s_mean}
        if p_mean is not None:
            pearson_abs.append(abs(p_mean))
        if s_mean is not None:
            spearman_abs.append(abs(s_mean))
    tables["per_pool_factor"] = per_member
    metrics.append(
        _metric(
            "pool_pearson_corr_max_abs",
            float(max(pearson_abs)) if pearson_abs else None,
            unit="corr", sample_range=sample_range,
            unavailable_reason=None if pearson_abs else "insufficient_overlap",
        )
    )
    metrics.append(
        _metric(
            "pool_spearman_corr_max_abs",
            float(max(spearman_abs)) if spearman_abs else None,
            unit="corr", sample_range=sample_range,
            unavailable_reason=None if spearman_abs else "insufficient_overlap",
        )
    )

    # Joint residualization on directional candidate.
    resid_parts: list[pd.Series] = []
    zero_info_dates = 0
    usable_dates = 0
    for _dt, idx in cand_d.groupby(level="eob").groups.items():
        y = cand_d.loc[idx].to_numpy(dtype=float)
        x = pool_mat.loc[idx].to_numpy(dtype=float)
        mask = np.isfinite(y) & np.isfinite(x).all(axis=1)
        if int(mask.sum()) < protocol.min_cross_section:
            continue
        y = y[mask]
        x = x[mask]
        usable_dates += 1
        design = np.column_stack([np.ones(len(x)), x])
        if len(y) <= design.shape[1]:
            zero_info_dates += 1
            continue
        try:
            beta, _residuals, rank, _s = np.linalg.lstsq(design, y, rcond=None)
            resid = y - design @ beta
        except np.linalg.LinAlgError:
            continue
        if int(rank) < design.shape[1] or float(np.nanstd(resid)) < 1e-12:
            zero_info_dates += 1
            continue
        resid_index = cand_d.loc[idx].index[mask]
        resid_parts.append(pd.Series(resid, index=resid_index))

    if usable_dates == 0:
        metrics.append(
            _metric("pool_joint_residual_rank_ic_mean", None, unit="ic",
                    sample_range=sample_range, unavailable_reason="insufficient_common_sample")
        )
    elif not resid_parts or zero_info_dates == usable_dates:
        metrics.append(
            _metric("pool_joint_residual_rank_ic_mean", None, unit="ic",
                    sample_range=sample_range, unavailable_reason="residual_zero_information")
        )
        tables["joint_residual"] = {"reason": "residual_zero_information"}
    else:
        residual = pd.concat(resid_parts).sort_index()
        resid_ic = _cross_section_corr(
            residual, fut_c.reindex(residual.index),
            rank=True, min_cross_section=protocol.min_cross_section,
        )
        if len(resid_ic) < protocol.min_ic_samples:
            metrics.append(
                _metric("pool_joint_residual_rank_ic_mean", None, unit="ic",
                        sample_range=sample_range, unavailable_reason="insufficient_ic_samples")
            )
        else:
            metrics.append(
                _metric("pool_joint_residual_rank_ic_mean", float(resid_ic.mean()),
                        unit="ic", sample_range=sample_range)
            )

    # Conditional / partial correlation: corr(fut, cand | pool) per date, then mean.
    cond_vals: list[float] = []
    cond_skipped = 0
    for _dt, idx in cand_d.groupby(level="eob").groups.items():
        y = fut_c.loc[idx].to_numpy(dtype=float)
        x = cand_d.loc[idx].to_numpy(dtype=float)
        z = pool_mat.loc[idx].to_numpy(dtype=float)
        mask = np.isfinite(y) & np.isfinite(x) & np.isfinite(z).all(axis=1)
        if int(mask.sum()) < protocol.min_cross_section:
            cond_skipped += 1
            continue
        # Rank-space partial correlation for rank IC analogue.
        y_r = pd.Series(y[mask]).rank(method="average").to_numpy()
        x_r = pd.Series(x[mask]).rank(method="average").to_numpy()
        z_r = np.column_stack([
            pd.Series(z[mask][:, j]).rank(method="average").to_numpy()
            for j in range(z.shape[1])
        ]) if z.ndim == 2 else pd.Series(z[mask]).rank(method="average").to_numpy()
        pc = _partial_corr(y_r, x_r, z_r)
        if pc is None:
            cond_skipped += 1
            continue
        cond_vals.append(pc)
    tables["conditional_corr"] = {
        "definition": (
            "per-date rank-space partial corr of execution-aligned future return "
            "and direction-normalized candidate controlling for full pool; "
            "aggregated as equal-weight mean over dates"
        ),
        "n_dates": len(cond_vals),
        "skipped_dates": cond_skipped,
    }
    if len(cond_vals) < protocol.min_ic_samples:
        metrics.append(
            _metric("pool_conditional_rank_corr_mean", None, unit="corr",
                    sample_range=sample_range, unavailable_reason="insufficient_ic_samples")
        )
    else:
        metrics.append(
            _metric("pool_conditional_rank_corr_mean", float(np.mean(cond_vals)),
                    unit="corr", sample_range=sample_range)
        )

    # Joint R2 with residual degrees of freedom requirement.
    r2_before_list: list[float] = []
    r2_after_list: list[float] = []
    r2_meta_dates = 0
    r2_skip_rank = 0
    for _dt, idx in cand_d.groupby(level="eob").groups.items():
        y = fut_c.loc[idx].to_numpy(dtype=float)
        x_pool = pool_mat.loc[idx].to_numpy(dtype=float)
        x_cand = cand_d.loc[idx].to_numpy(dtype=float)
        mask = np.isfinite(y) & np.isfinite(x_pool).all(axis=1) & np.isfinite(x_cand)
        if int(mask.sum()) < protocol.min_cross_section:
            continue
        y_m = y[mask]
        if np.unique(np.round(y_m, 12)).size < 2:
            continue
        before, rank_b, df_b = _cs_ols(y_m, x_pool[mask])
        x_after = np.column_stack([x_pool[mask], x_cand[mask]])
        after, rank_a, df_a = _cs_ols(y_m, x_after)
        r2_meta_dates += 1
        # Candidate already in pool span ⇒ after design rank-deficient; treat as
        # zero incremental R2 when the before model is identified.
        if after is None and before is not None and df_b >= 1:
            # Residual of candidate on pool(+intercept); near-zero ⇒ in span.
            design = (
                np.column_stack([np.ones(len(x_pool[mask])), x_pool[mask]])
                if x_pool[mask].ndim == 2
                else np.column_stack([np.ones(len(x_pool[mask])), x_pool[mask].reshape(-1, 1)])
            )
            if len(x_cand[mask]) > design.shape[1]:
                try:
                    beta_c, _, rank_c, _ = np.linalg.lstsq(design, x_cand[mask], rcond=None)
                    resid_c = x_cand[mask] - design @ beta_c
                    in_span = (
                        int(rank_c) == design.shape[1]
                        and float(np.nanstd(resid_c)) < 1e-10
                    )
                except np.linalg.LinAlgError:
                    in_span = False
                if in_span:
                    after = before
                    df_a = df_b
        if before is None or after is None or df_a < 1 or df_b < 1:
            r2_skip_rank += 1
            continue
        r2_before_list.append(before)
        r2_after_list.append(after)
    tables["joint_r2"] = {
        "definition": (
            "per-date CS OLS R2 of execution-aligned future ~ pool(+intercept) vs "
            "future ~ pool+candidate(+intercept); requires n > n_params and full rank; "
            "delta = mean(after - before); saturated/rank-deficient dates are skipped "
            "and never report mechanical R2=1"
        ),
        "n_dates_considered": r2_meta_dates,
        "n_dates_used": len(r2_before_list),
        "skipped_rank_or_df": r2_skip_rank,
        "identifiability": "n > n_params and lstsq rank == n_params; residual_df = n - rank",
    }
    if len(r2_before_list) < protocol.min_ic_samples:
        for name in ("pool_joint_r2_before", "pool_joint_r2_after", "pool_joint_r2_delta"):
            reason = (
                "saturated_or_rank_deficient"
                if r2_meta_dates and r2_skip_rank == r2_meta_dates
                else "insufficient_ic_samples"
            )
            metrics.append(
                _metric(name, None, unit="r2", sample_range=sample_range,
                        unavailable_reason=reason)
            )
    else:
        before_mean = float(np.mean(r2_before_list))
        after_mean = float(np.mean(r2_after_list))
        delta = after_mean - before_mean
        # Candidate in pool span => near-zero incremental R2.
        metrics.append(_metric("pool_joint_r2_before", before_mean, unit="r2", sample_range=sample_range))
        metrics.append(_metric("pool_joint_r2_after", after_mean, unit="r2", sample_range=sample_range))
        metrics.append(_metric("pool_joint_r2_delta", delta, unit="r2", sample_range=sample_range))
        tables["joint_r2"].update(
            {"before_mean": before_mean, "after_mean": after_mean, "delta": delta}
        )

    # Portfolio deltas only from issued official FormalBacktestPair.
    if formal_before_after is None:
        for name in (
            "pool_portfolio_return_delta",
            "pool_portfolio_drawdown_delta",
            "pool_portfolio_turnover_delta",
        ):
            metrics.append(
                _metric(name, None, unit="ratio", sample_range=sample_range,
                        unavailable_reason="formal_before_after_artifacts_missing")
            )
    elif not isinstance(formal_before_after, FormalBacktestPair):
        findings.append(
            _finding(
                "POOL_FORMAL_PAIR_INVALID",
                passed=False,
                severity=FindingSeverity.SOFT_FAIL,
                message="formal_before_after must be FormalBacktestPair",
            )
        )
        for name in (
            "pool_portfolio_return_delta",
            "pool_portfolio_drawdown_delta",
            "pool_portfolio_turnover_delta",
        ):
            metrics.append(
                _metric(name, None, unit="ratio", sample_range=sample_range,
                        unavailable_reason="formal_before_after_invalid_type")
            )
    else:
        bind_errs = _formal_pair_binds_current_inputs(
            formal_before_after,
            panel=panel,
            candidate=candidate,
            pool=pool,
            protocol=protocol,
        )
        if bind_errs:
            findings.append(
                _finding(
                    "POOL_FORMAL_RESULT_INVALID",
                    passed=False,
                    severity=FindingSeverity.SOFT_FAIL,
                    message=(
                        "formal pair provenance does not bind to current "
                        "panel/candidate/pool/protocol or is not officially issued"
                    ),
                    details={"errors": tuple(bind_errs)},
                )
            )
            for name in (
                "pool_portfolio_return_delta",
                "pool_portfolio_drawdown_delta",
                "pool_portfolio_turnover_delta",
            ):
                metrics.append(
                    _metric(
                        name,
                        None,
                        unit="ratio",
                        sample_range=sample_range,
                        unavailable_reason="formal_result_unverified",
                    )
                )
        else:
            try:
                b = verified_backtest_metrics(formal_before_after.before)
                a = verified_backtest_metrics(formal_before_after.after)
            except (TypeError, ValueError) as exc:
                findings.append(
                    _finding(
                        "POOL_FORMAL_RESULT_INVALID",
                        passed=False,
                        severity=FindingSeverity.SOFT_FAIL,
                        message="formal BacktestResult metrics could not be recomputed",
                        details={"cause_type": type(exc).__name__},
                    )
                )
                for name in (
                    "pool_portfolio_return_delta",
                    "pool_portfolio_drawdown_delta",
                    "pool_portfolio_turnover_delta",
                ):
                    metrics.append(
                        _metric(name, None, unit="ratio", sample_range=sample_range,
                                unavailable_reason="formal_result_unverified")
                    )
            else:
                metrics.append(
                    _metric(
                        "pool_portfolio_return_delta",
                        float(a["total_return"]) - float(b["total_return"]),
                        unit="return", sample_range=sample_range,
                    )
                )
                metrics.append(
                    _metric(
                        "pool_portfolio_drawdown_delta",
                        float(a["max_drawdown"]) - float(b["max_drawdown"]),
                        unit="ratio", sample_range=sample_range,
                    )
                )
                metrics.append(
                    _metric(
                        "pool_portfolio_turnover_delta",
                        float(a["avg_daily_turnover"]) - float(b["avg_daily_turnover"]),
                        unit="ratio", sample_range=sample_range,
                    )
                )

    findings.append(
        _finding(
            "POOL_COMPARE_COMPLETE",
            passed=True,
            severity=FindingSeverity.INFO,
            message="pool incremental comparison finished",
            details={"n_pool": int(len(aligned_pool))},
        )
    )
    return findings, metrics, tables


__all__ = ["compare_candidate_to_pool", "run_official_formal_backtest_pair"]
