"""Adversarial + hand-calculated tests for Phase 03 (round-2 + M1–M12)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from skills.analyze.causality import (
    BoundPrefixRecompute,
    _testing_only_bound_prefix_recompute,
    validate_output_alignment,
    verify_prefix_causality,
)
from skills.analyze.contracts import Finding, FindingSeverity, FormalBacktestPair
from skills.analyze.facade import AnalyzeFacade
from skills.analyze.factor_evaluation import (
    _forward_returns,
    _quantile_labels,
    build_long_short_weights,
    compute_predictive_metrics,
    execution_aligned_returns,
    formal_trading_supported,
    newey_west_mean_tstat,
    run_formal_backtest,
)
from skills.analyze.factor_incremental import (
    compare_candidate_to_pool,
    run_official_formal_backtest_pair,
)
from skills.analyze.factor_robustness import compute_robustness
from skills.analyze.spec_checks import validate_spec
from skills.analyze.validation import validate_panel
from skills.factor_mining.adapters.failure_codes import (
    EXACT_FAILURE_CODES,
    PREFIX_FAILURE_CODES,
    map_hard_fail_code,
)
from skills.factor_mining.contracts import FailureCode
from tests.fixtures.market_data import make_panel
from tests.skills.analyze.conftest_phase03 import make_protocol, make_spec


def _metric_map(metrics):
    return {m.name: m for m in metrics}


def _bound(spec, fn):
    return _testing_only_bound_prefix_recompute(
        spec_content_hash=spec.content_hash,
        formula_fingerprint=spec.formula_fingerprint,
        recompute=fn,
    )


def test_b4_public_arbitrary_issuer_absent() -> None:
    import skills.analyze.causality as causality
    assert "issue_prefix_recompute_capability" not in causality.__all__
    assert not hasattr(causality, "issue_prefix_recompute_capability")


# ---------------------------------------------------------------------------
# M12 / prior: missing-price no fill
# ---------------------------------------------------------------------------


def test_forward_returns_no_fill_across_nan() -> None:
    idx = pd.MultiIndex.from_product(
        [["A"], pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])],
        names=["symbol", "eob"],
    )
    close = pd.Series([100.0, np.nan, 110.0], index=idx)
    fut = _forward_returns(close, 1)
    assert pd.isna(fut.loc[("A", pd.Timestamp("2024-01-01"))])
    assert pd.isna(fut.loc[("A", pd.Timestamp("2024-01-02"))])


# ---------------------------------------------------------------------------
# M3: execution-aligned return labels
# ---------------------------------------------------------------------------


def test_execution_aligned_returns_hand_calc_forward_backward_lag_open_close() -> None:
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    idx = pd.MultiIndex.from_product([["A"], dates], names=["symbol", "eob"])
    close = pd.Series([100.0, 110.0, 121.0, 133.1], index=idx)
    open_ = pd.Series([99.0, 108.0, 120.0, 130.0], index=idx)

    # forward, lag=0, H=1, close: P[t+1]/P[t]-1
    proto = make_protocol(signal_lag=0, horizon_bars=1, return_mode="forward", trade_at="close")
    fut = execution_aligned_returns(close, proto)
    assert fut.loc[("A", dates[0])] == pytest.approx(0.1)
    assert fut.loc[("A", dates[1])] == pytest.approx(0.1)

    # forward, lag=1, H=1: P[t+2]/P[t+1]-1 labeled at t
    proto_l1 = make_protocol(signal_lag=1, horizon_bars=1, return_mode="forward", trade_at="close")
    fut_l1 = execution_aligned_returns(close, proto_l1)
    assert fut_l1.loc[("A", dates[0])] == pytest.approx(0.1)  # 121/110-1
    assert fut_l1.loc[("A", dates[1])] == pytest.approx(133.1 / 121.0 - 1.0)

    # backward, lag=0, H=1: P[t]/P[t-1]-1
    proto_b = make_protocol(signal_lag=0, horizon_bars=1, return_mode="backward", trade_at="close")
    fut_b = execution_aligned_returns(close, proto_b)
    assert fut_b.loc[("A", dates[1])] == pytest.approx(0.1)

    # trade_at=open
    proto_o = make_protocol(signal_lag=0, horizon_bars=1, return_mode="forward", trade_at="open")
    fut_o = execution_aligned_returns(open_, proto_o)
    assert fut_o.loc[("A", dates[0])] == pytest.approx(108.0 / 99.0 - 1.0)


def test_m3_alternating_winner_ic_vs_formal_interval() -> None:
    """Perfect t->t+1 predictor has IC=+1 at lag=0, but lag=1 earns t+1->t+2."""
    dates = pd.to_datetime([f"2024-01-{d:02d}" for d in range(1, 9)])
    symbols = ["A", "B"]
    idx = pd.MultiIndex.from_product([symbols, dates], names=["symbol", "eob"])
    # Alternating winner: odd days A up / B flat; even days B up / A flat.
    close = pd.Series(100.0, index=idx, dtype=float)
    for i, d in enumerate(dates[:-1]):
        nxt = dates[i + 1]
        if i % 2 == 0:
            close.loc[("A", nxt)] = close.loc[("A", d)] * 1.10
            close.loc[("B", nxt)] = close.loc[("B", d)] * 1.00
        else:
            close.loc[("A", nxt)] = close.loc[("A", d)] * 1.00
            close.loc[("B", nxt)] = close.loc[("B", d)] * 1.10
    # Factor at t predicts next-day winner (t->t+1).
    factor = pd.Series(0.0, index=idx, dtype=float)
    for i, d in enumerate(dates[:-1]):
        if i % 2 == 0:
            factor.loc[("A", d)] = 1.0
            factor.loc[("B", d)] = 0.0
        else:
            factor.loc[("A", d)] = 0.0
            factor.loc[("B", d)] = 1.0
    panel = pd.DataFrame({"close": close, "open": close})

    proto0 = make_protocol(
        signal_lag=0, horizon_bars=1, min_ic_samples=2, min_cross_section=2, n_groups=2
    )
    _, metrics0, _, tables0 = compute_predictive_metrics(panel, factor, proto0)
    assert _metric_map(metrics0)["rank_ic_mean"].value == pytest.approx(1.0)
    assert abs(list(tables0["rank_ic"].values())[0] - 1.0) < 1e-9

    # Same factor with lag=1 labels t+1->t+2 which is the *other* winner → IC=-1.
    proto1 = make_protocol(
        signal_lag=1, horizon_bars=1, min_ic_samples=2, min_cross_section=2, n_groups=2
    )
    _, metrics1, _, _ = compute_predictive_metrics(panel, factor, proto1)
    assert _metric_map(metrics1)["rank_ic_mean"].value == pytest.approx(-1.0)


def test_hand_calculated_pearson_and_rank_ic() -> None:
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    idx = pd.MultiIndex.from_product([["A", "B", "C"], dates], names=["symbol", "eob"])
    close = pd.Series(1.0, index=idx, dtype=float)
    close.loc[("A", dates[1])] = 1.1
    close.loc[("B", dates[1])] = 1.2
    close.loc[("C", dates[1])] = 1.3
    close.loc[("A", dates[2])] = 1.1
    close.loc[("B", dates[2])] = 1.2
    close.loc[("C", dates[2])] = 1.3
    factor = pd.Series(0.0, index=idx, dtype=float)
    for d in dates:
        factor.loc[("A", d)] = 1.0
        factor.loc[("B", d)] = 2.0
        factor.loc[("C", d)] = 3.0
    panel = pd.DataFrame({"close": close})
    protocol = make_protocol(
        horizon_bars=1, signal_lag=0, min_ic_samples=1, n_groups=3, min_cross_section=3
    )
    findings, metrics, _, tables = compute_predictive_metrics(panel, factor, protocol)
    assert not any(
        (not f.passed) and f.severity is FindingSeverity.HARD_FAIL for f in findings
    )
    assert abs(tables["pearson_ic"][str(dates[0])] - 1.0) < 1e-9
    mm = _metric_map(metrics)
    assert mm["pearson_ic_mean"].value == pytest.approx(1.0)
    assert mm["pearson_ic_count"].value == 1


def test_overlapping_horizon_rejects_iid_and_reports_hac_p() -> None:
    panel = make_panel(("AAA", "BBB", "CCC"), periods=30)
    values = panel["close"].astype(float)
    protocol = make_protocol(horizon_bars=5, min_ic_samples=2, ic_decay_horizons=(1, 5))
    _, metrics, uncertainty, _ = compute_predictive_metrics(panel, values, protocol)
    mm = _metric_map(metrics)
    assert mm["rank_ic_t_stat"].value is None
    assert mm["rank_ic_t_stat"].unavailable_reason == "overlapping_horizon_iid_unavailable"
    assert mm["rank_ic_p_value"].unavailable_reason == "overlapping_horizon_iid_unavailable"
    # M10: HAC t and asymptotic p present when samples allow.
    assert "rank_ic_hac_t_stat" in mm
    assert "rank_ic_hac_p_value" in mm
    methods = {u.method for u in uncertainty if u.name.startswith("rank_ic")}
    assert "newey_west_hac" in methods
    assert "iid_t_test" not in methods
    t, se, p = newey_west_mean_tstat(pd.Series([0.1, -0.05, 0.2, 0.0, 0.15]), lag=4)
    assert np.isfinite(t) and np.isfinite(se) and 0.0 <= p <= 1.0


def test_quantile_ties_equal_values_not_split() -> None:
    values = pd.Series([1.0, 1.0, 1.0, 2.0], index=list("ABCD"))
    labels, ok = _quantile_labels(values, 2, tie_rule="average")
    assert ok
    assert labels.loc["A"] == labels.loc["B"] == labels.loc["C"]
    all_equal = pd.Series([1.0, 1.0, 1.0, 1.0], index=list("ABCD"))
    labels2, ok2 = _quantile_labels(all_equal, 2, tie_rule="average")
    assert ok2 is False
    assert labels2.isna().all()


# ---------------------------------------------------------------------------
# M2: joint R2 df / saturation
# ---------------------------------------------------------------------------


def test_joint_r2_marginal_hand_calc_with_residual_df() -> None:
    # 5 symbols so n > intercept+2 pool params; candidate = p1+p2 in span ⇒ delta≈0.
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    syms = ["A", "B", "C", "D", "E"]
    idx = pd.MultiIndex.from_product([syms, dates], names=["symbol", "eob"])
    close = pd.Series(1.0, index=idx)
    for _d0, d1, rets in (
        (dates[0], dates[1], (1.10, 1.20, 1.05, 0.95, 1.00)),
        (dates[1], dates[2], (1.10, 1.20, 1.05, 0.95, 1.00)),
        (dates[2], dates[3], (1.10, 1.20, 1.05, 0.95, 1.00)),
    ):
        for sym, px in zip(syms, rets, strict=True):
            close.loc[(sym, d1)] = px
    p1 = pd.Series(0.0, index=idx)
    p2 = pd.Series(0.0, index=idx)
    for d in dates:
        for sym, v1, v2 in zip(syms, (1, 0, -1, 0.5, -0.5), (0, 1, 1, -1, 0), strict=True):
            p1.loc[(sym, d)] = v1
            p2.loc[(sym, d)] = v2
    candidate = p1 + p2
    panel = pd.DataFrame({"close": close})
    protocol = make_protocol(
        horizon_bars=1, signal_lag=0, min_ic_samples=1, n_groups=3, min_cross_section=3
    )
    findings, metrics, tables = compare_candidate_to_pool(
        panel, candidate, {"p1": p1, "p2": p2}, protocol
    )
    assert any(f.name == "POOL_COMPARE_COMPLETE" for f in findings)
    mm = _metric_map(metrics)
    assert "pool_marginal_rank_ic_delta" not in mm
    assert mm["pool_joint_r2_delta"].value is not None
    assert abs(mm["pool_joint_r2_delta"].value) < 1e-9  # in pool span
    assert "identifiability" in tables["joint_r2"]
    assert mm["pool_portfolio_return_delta"].unavailable_reason == (
        "formal_before_after_artifacts_missing"
    )


def test_m2_random_3symbol_saturated_not_claimed() -> None:
    """n=3 with intercept+pool+candidate=3 params must not claim large R2 delta."""
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    syms = ["A", "B", "C"]
    idx = pd.MultiIndex.from_product([syms, dates], names=["symbol", "eob"])
    rng = np.random.default_rng(0)
    close = pd.Series(1.0, index=idx)
    for _i, d in enumerate(dates[1:], start=1):
        for j, sym in enumerate(syms):
            close.loc[(sym, d)] = 1.0 + 0.01 * rng.normal() + 0.05 * j
    pool = pd.Series(rng.normal(size=len(idx)), index=idx)
    cand = pd.Series(rng.normal(size=len(idx)), index=idx)
    panel = pd.DataFrame({"close": close})
    protocol = make_protocol(
        horizon_bars=1, signal_lag=0, min_ic_samples=1, min_cross_section=3, n_groups=3
    )
    _, metrics, tables = compare_candidate_to_pool(
        panel, cand, {"p1": pool}, protocol
    )
    mm = _metric_map(metrics)
    # After model has 3 params on n=3 → all dates skipped as saturated.
    assert mm["pool_joint_r2_delta"].value is None
    assert mm["pool_joint_r2_delta"].unavailable_reason in {
        "saturated_or_rank_deficient",
        "insufficient_ic_samples",
    }
    assert tables["joint_r2"]["n_dates_used"] == 0


def test_pool_unavailable_metrics() -> None:
    panel = make_panel(("AAA", "BBB", "CCC"), periods=20)
    candidate = panel["close"].astype(float)
    protocol = make_protocol(min_ic_samples=2)
    findings, metrics, _ = compare_candidate_to_pool(panel, candidate, None, protocol)
    assert any(f.name == "POOL_UNAVAILABLE" for f in findings)
    mm = _metric_map(metrics)
    assert mm["pool_joint_r2_delta"].unavailable_reason == "pool_unavailable"


# ---------------------------------------------------------------------------
# M1 / R2-2: prefix binding, multi-cut, mutation, late-tail leak
# ---------------------------------------------------------------------------


def test_prefix_causality_bound_formula_and_mismatch() -> None:
    panel = make_panel(("AAA", "BBB"), periods=16)
    spec = make_spec()

    def leak(df: pd.DataFrame) -> pd.Series:
        mu = float(df["close"].mean())
        return df["close"] * 0.0 + mu

    def causal(df: pd.DataFrame) -> pd.Series:
        return df["close"].groupby(level=0).transform(lambda s: s.shift(1))

    def zeros(df: pd.DataFrame) -> pd.Series:
        return df["close"].astype(float) * 0.0

    leak_bound = _bound(spec, leak)
    findings = verify_prefix_causality(
        panel, datetime_pos=1, recompute=leak_bound, spec=spec, min_prefix_rows=4
    )
    assert any(
        (not f.passed) and f.name == "CAUSALITY_PREFIX_RECOMPUTE" for f in findings
    )
    assert findings[0].details["spec_content_hash"] == spec.content_hash
    assert findings[0].details["formula_fingerprint"] == spec.formula_fingerprint

    ok = verify_prefix_causality(
        panel, datetime_pos=1, recompute=_bound(spec, causal), spec=spec
    )
    assert ok[0].passed is True
    assert ok[0].details["n_cuts"] >= 2
    cuts = ok[0].details["cuts"]
    times = sorted(panel.index.get_level_values("eob").unique())
    near_tail = str(times[-2] if hasattr(times[-2], "isoformat") else times[max(1, len(times) - 2)])
    assert any(near_tail[:10] in str(c) for c in cuts), cuts

    # Direct construction forbidden (P0-4).
    with pytest.raises(TypeError, match="cannot be constructed directly"):
        BoundPrefixRecompute(spec.content_hash, spec.formula_fingerprint, zeros)

    # Issued with wrong spec hash / formula fingerprint → mismatch.
    wrong_spec = _testing_only_bound_prefix_recompute(
        spec_content_hash="b" * 64,
        formula_fingerprint=spec.formula_fingerprint,
        recompute=causal,
    )
    mismatch = verify_prefix_causality(
        panel, datetime_pos=1, recompute=wrong_spec, spec=spec
    )
    assert mismatch[0].name == "CAUSALITY_RECOMPUTE_SPEC_MISMATCH"

    wrong_fp = _testing_only_bound_prefix_recompute(
        spec_content_hash=spec.content_hash,
        formula_fingerprint="c" * 64,
        recompute=causal,
    )
    formula_mismatch = verify_prefix_causality(
        panel, datetime_pos=1, recompute=wrong_fp, spec=spec
    )
    assert formula_mismatch[0].name == "CAUSALITY_RECOMPUTE_FORMULA_MISMATCH"

    unbound = verify_prefix_causality(
        panel, datetime_pos=1, recompute=causal, spec=spec
    )
    assert unbound[0].name == "CAUSALITY_RECOMPUTE_UNBOUND"

    missing = verify_prefix_causality(panel, datetime_pos=1, recompute=None, spec=spec)
    assert missing[0].passed is False
    assert missing[0].details["reason"] == "no_recompute_callable"
    assert missing[0].severity is FindingSeverity.SOFT_FAIL


def test_p0_4_issued_zeros_rejected_against_real_values() -> None:
    """Sealed zeros capability cannot satisfy evaluate value-match (P0-4)."""
    panel = make_panel(("AAA", "BBB"), periods=12)
    spec = make_spec()
    protocol = make_protocol(require_prefix_recompute=True)
    values = panel["close"].astype(float)
    mask = pd.Series(True, index=values.index, dtype=bool)

    def zeros(df: pd.DataFrame) -> pd.Series:
        return df["close"].astype(float) * 0.0

    sealed_zeros = _bound(spec, zeros)
    # Prefix causality alone may pass (zeros are causal), but evaluate must reject.
    result = AnalyzeFacade(prefix_recompute=lambda s: sealed_zeros).evaluate(
        panel=panel,
        spec=spec,
        protocol=protocol,
        values=values,
        valid_mask=mask,
    )
    assert result.hard_failed
    assert any(
        f.name == "CAUSALITY_RECOMPUTE_VALUE_MISMATCH"
        for s in result.sections
        for f in s.findings
    )


def test_m1_late_tail_leak_caught_by_near_tail_cut() -> None:
    """Lookahead only contaminates the near-tail cut bar when last future exists.

    Prefix ending at times[-2] is causal (last absent). Full panel includes last,
    so values at times[-2] change — near-tail cut must hard-fail.
    """
    panel = make_panel(("AAA", "BBB"), periods=20)
    spec = make_spec()
    times = list(pd.Index(panel.index.get_level_values("eob")).unique().sort_values())
    last = times[-1]
    near_tail = times[-2]

    def late_only_leak(df: pd.DataFrame) -> pd.Series:
        out = df["close"].groupby(level=0).transform(lambda s: s.shift(1)).astype(float)
        present = set(pd.Index(df.index.get_level_values("eob")).unique())
        # Contaminate only the near-tail bar, and only when the absolute last
        # future timestamp is present (full-panel path after a near-tail cut).
        if last in present:
            leaked = df["close"].groupby(level=0).transform(lambda s: s.shift(-1))
            mask = df.index.get_level_values("eob") == near_tail
            out = out.copy()
            out.loc[mask] = leaked.loc[mask]
        return out

    findings = verify_prefix_causality(
        panel, datetime_pos=1, recompute=_bound(spec, late_only_leak), spec=spec
    )
    hard = [
        f
        for f in findings
        if (not f.passed)
        and f.severity is FindingSeverity.HARD_FAIL
        and f.name == "CAUSALITY_PREFIX_RECOMPUTE"
    ]
    assert hard, findings
    near_tail_str = str(near_tail)
    assert any(near_tail_str in str(f.details.get("cut", "")) for f in hard), hard


def test_prefix_mutation_of_actual_copies_hard_fails() -> None:
    panel = make_panel(("AAA", "BBB"), periods=12)
    snapshot = panel.copy(deep=True)
    spec = make_spec()

    def mutate_prefix(df: pd.DataFrame) -> pd.Series:
        df.iloc[0, df.columns.get_loc("close")] = -999.0
        return df["close"].astype(float)

    findings = verify_prefix_causality(
        panel, datetime_pos=1, recompute=_bound(spec, mutate_prefix), spec=spec
    )
    assert any(f.name == "CAUSALITY_PREFIX_INPUT_MUTATED" for f in findings)
    pd.testing.assert_frame_equal(snapshot, panel)


def test_prefix_keyset_must_be_preserved() -> None:
    panel = make_panel(("AAA", "BBB"), periods=12)
    spec = make_spec()

    def drop_all_but_first(df: pd.DataFrame) -> pd.Series:
        return df["close"].astype(float).iloc[:1]

    findings = verify_prefix_causality(
        panel, datetime_pos=1, recompute=_bound(spec, drop_all_but_first), spec=spec
    )
    assert any((not f.passed) for f in findings)


# ---------------------------------------------------------------------------
# M5 / R2-1: semantic time-order warmup + Inf/NA mask
# ---------------------------------------------------------------------------


def test_m5_unsorted_warmup_uses_semantic_time_order() -> None:
    # Physical order: d2 NaN, d1 finite, d3 finite — must NOT be a leading-warmup pass.
    dates = pd.to_datetime(["2024-01-02", "2024-01-01", "2024-01-03"])
    idx = pd.MultiIndex.from_arrays(
        [["AAA", "AAA", "AAA"], dates], names=["symbol", "eob"]
    )
    values = pd.Series([np.nan, 1.0, 2.0], index=idx)
    panel = pd.DataFrame({"close": values})
    snap = values.copy()
    findings = validate_output_alignment(
        values=values,
        valid_mask=values.notna(),
        panel=panel,
        warmup=0,
        missing_policy="keep_nan",
        symbol_level="symbol",
        datetime_level="eob",
    )
    assert any(f.name == "ALIGNMENT_KEEP_NAN_INTERIOR" and not f.passed for f in findings)
    pd.testing.assert_series_equal(snap, values)


def test_alignment_inf_and_nullable_mask_hard_fail() -> None:
    panel = make_panel(("AAA", "BBB"), periods=6)
    values = panel["close"].astype(float).copy()
    values.iloc[0] = np.inf
    findings = validate_output_alignment(
        values=values,
        valid_mask=np.isfinite(values.to_numpy()),
        panel=panel,
        warmup=2,
        missing_policy="keep_nan",
    )
    # valid_mask as ndarray is wrong type — use Series
    mask = pd.Series(np.isfinite(values.to_numpy()), index=values.index)
    findings = validate_output_alignment(
        values=values, valid_mask=mask, panel=panel, warmup=2, missing_policy="keep_nan"
    )
    assert any(f.name == "ALIGNMENT_NON_FINITE" and not f.passed for f in findings)

    values2 = panel["close"].astype(float).copy()
    mask_na = pd.Series(
        [True, pd.NA] + [True] * (len(values2) - 2),
        index=values2.index,
        dtype="boolean",
    )
    findings2 = validate_output_alignment(
        values=values2,
        valid_mask=mask_na,
        panel=panel,
        warmup=2,
        missing_policy="keep_nan",
    )
    assert any(f.name == "ALIGNMENT_MASK_NULLABLE_NA" and not f.passed for f in findings2)


def test_alignment_require_valid_mask() -> None:
    panel = make_panel(("AAA", "BBB"), periods=6)
    values = panel["close"].astype(float)
    findings = validate_output_alignment(
        values=values,
        valid_mask=None,
        panel=panel,
        warmup=2,
        missing_policy="keep_nan",
        require_valid_mask=True,
    )
    assert any(f.name == "ALIGNMENT_MASK_REQUIRED" and not f.passed for f in findings)


def test_panel_index_misalignment_and_immutability() -> None:
    panel = make_panel(("AAA", "BBB"), periods=8)
    snapshot = panel.copy(deep=True)
    protocol = make_protocol(datetime_level="date")
    findings, _, _ = validate_panel(panel, protocol)
    assert any(
        (not f.passed) and f.severity is FindingSeverity.HARD_FAIL for f in findings
    )
    pd.testing.assert_frame_equal(snapshot, panel)


# ---------------------------------------------------------------------------
# M4: long_low direction in pool residual IC
# ---------------------------------------------------------------------------


def test_m4_long_low_residual_ic_direction_normalized() -> None:
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    syms = ["A", "B", "C", "D", "E"]
    idx = pd.MultiIndex.from_product([syms, dates], names=["symbol", "eob"])
    close = pd.Series(1.0, index=idx)
    # Future returns ranked with A highest … E lowest on each signal day (lag=0).
    for d1, rets in (
        (dates[1], (1.5, 1.4, 1.3, 1.2, 1.1)),
        (dates[2], (1.5, 1.4, 1.3, 1.2, 1.1)),
        (dates[3], (1.5, 1.4, 1.3, 1.2, 1.1)),
    ):
        for sym, px in zip(syms, rets, strict=True):
            close.loc[(sym, d1)] = px
    # Orthogonalish pool noise.
    pool = pd.Series(0.0, index=idx)
    for d in dates:
        for i, sym in enumerate(syms):
            pool.loc[(sym, d)] = float(i % 2)
    # Raw candidate: low on high-return names (long_low predictive pattern).
    cand = pd.Series(0.0, index=idx)
    for d in dates:
        for i, sym in enumerate(syms):
            cand.loc[(sym, d)] = float(i + 1)  # A=1 … E=5; A has highest return
    panel = pd.DataFrame({"close": close})
    protocol = make_protocol(
        direction="long_low",
        signal_lag=0,
        horizon_bars=1,
        min_ic_samples=1,
        min_cross_section=3,
        n_groups=3,
    )
    # Predictive should flip to positive IC.
    _, pred_metrics, _, _ = compute_predictive_metrics(panel, cand, protocol)
    assert _metric_map(pred_metrics)["rank_ic_mean"].value == pytest.approx(1.0)

    _, metrics, tables = compare_candidate_to_pool(
        panel, cand, {"p1": pool}, protocol
    )
    mm = _metric_map(metrics)
    # Directional residual IC should also be positive after the same flip.
    assert mm["pool_joint_residual_rank_ic_mean"].value is not None
    assert mm["pool_joint_residual_rank_ic_mean"].value > 0
    assert "direction_policy" in tables
    assert "raw redundancy" in tables["direction_policy"]


# ---------------------------------------------------------------------------
# M6: exact robustness keysets
# ---------------------------------------------------------------------------


def test_m6_robustness_exact_keysets_forbid_posthoc() -> None:
    panel = make_panel(("AAA", "BBB", "CCC"), periods=24)
    values = panel["close"].astype(float)
    protocol = make_protocol(
        regimes=("bull", "bear"),
        time_subsamples=("early", "late"),
        parameter_neighborhood={"period": (2, 3)},
        min_ic_samples=2,
    )
    # Missing bear; extra posthoc; unregistered_best param.
    regime_masks = {
        "bull": values.notna(),
        "posthoc": values.notna(),
    }
    ts_masks = {"early": values.notna(), "extra_ts": values.notna()}
    param_outputs = {"unregistered_best": values, "period=2": values}
    findings, metrics, _, tables = compute_robustness(
        panel,
        values,
        protocol,
        regime_masks=regime_masks,
        time_subsample_masks=ts_masks,
        parameter_outputs=param_outputs,
    )
    names = {f.name for f in findings}
    assert "ROBUSTNESS_REGIME_POSTHOC_FORBIDDEN" in names
    assert "ROBUSTNESS_REGIME_UNAVAILABLE" in names
    assert "ROBUSTNESS_TIME_SUBSAMPLE_POSTHOC_FORBIDDEN" in names
    assert "ROBUSTNESS_PARAM_POSTHOC_FORBIDDEN" in names
    assert tables["parameter_label_contract"].startswith("key=value")
    mm = _metric_map(metrics)
    assert mm["robustness_regime_bear_rank_ic_mean"].unavailable_reason == (
        "regime_mask_missing"
    )


# ---------------------------------------------------------------------------
# M7: spec params + direction hard-fail
# ---------------------------------------------------------------------------


def test_m7_spec_param_validation_and_direction_hard_fail() -> None:
    for bad in (
        make_spec(params={"period": -2}, window=2),
        make_spec(params={"period": "bad"}, window=2),
        make_spec(params={"period": 2}, window=0),
        make_spec(params={"lag": -1}, window=2, lag=0),
    ):
        findings = validate_spec(bad, allowed_fields=("close",))
        assert any(
            (not f.passed) and f.severity is FindingSeverity.HARD_FAIL for f in findings
        ), bad
    with pytest.raises(ValueError, match="lag"):
        make_spec(params={"period": 2}, window=2, lag=-1)

    panel = make_panel(("AAA", "BBB"), periods=10)
    spec = make_spec(expected_direction="long_high")
    protocol = make_protocol(direction="long_low")
    result = AnalyzeFacade().preflight(panel=panel, spec=spec, protocol=protocol)
    assert result.hard_failed
    assert any(f.name == "SPEC_DIRECTION_MISMATCH" for s in result.sections for f in s.findings)


# ---------------------------------------------------------------------------
# M8: require_prefix_recompute policy
# ---------------------------------------------------------------------------


def test_m8_require_prefix_recompute_hard_fail_when_missing() -> None:
    panel = make_panel(("AAA", "BBB"), periods=12)
    spec = make_spec()
    protocol = make_protocol(require_prefix_recompute=True)
    result = AnalyzeFacade().preflight(panel=panel, spec=spec, protocol=protocol)
    assert result.hard_failed
    caus = next(s for s in result.sections if s.name == "causality")
    assert any(
        f.name == "CAUSALITY_PREFIX_RECOMPUTE" and not f.passed for f in caus.findings
    )

    protocol_soft = make_protocol(require_prefix_recompute=False)
    soft = AnalyzeFacade().preflight(panel=panel, spec=spec, protocol=protocol_soft)
    caus2 = next(s for s in soft.sections if s.name == "causality")
    miss = next(f for f in caus2.findings if f.name == "CAUSALITY_PREFIX_RECOMPUTE")
    assert miss.severity is FindingSeverity.SOFT_FAIL


# ---------------------------------------------------------------------------
# M9: finite common-sample alignment loss
# ---------------------------------------------------------------------------


def test_m9_all_nan_pool_member_finite_alignment_loss() -> None:
    panel = make_panel(("AAA", "BBB", "CCC", "DDD"), periods=16)
    cand = panel["close"].astype(float)
    pool_nan = pd.Series(np.nan, index=cand.index)
    protocol = make_protocol(signal_lag=0, min_ic_samples=1, min_cross_section=2)
    _, metrics, _ = compare_candidate_to_pool(
        panel, cand, {"dead": pool_nan}, protocol
    )
    mm = _metric_map(metrics)
    assert mm["pool_finite_alignment_loss"].value == pytest.approx(1.0)
    assert mm["pool_joint_r2_delta"].unavailable_reason in {
        "insufficient_common_sample",
        "pool_unavailable",
        "insufficient_ic_samples",
        "saturated_or_rank_deficient",
    }


# ---------------------------------------------------------------------------
# M11: canonical group weight turnover
# ---------------------------------------------------------------------------


def test_m11_group_turnover_hand_calc() -> None:
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    syms = ["A", "B", "C", "D"]
    idx = pd.MultiIndex.from_product([syms, dates], names=["symbol", "eob"])
    close = pd.Series(1.0, index=idx)
    # Distinct returns so groups form; factor ranks swap between dates 0 and 1.
    for d1, rets in (
        (dates[1], (1.4, 1.3, 1.2, 1.1)),
        (dates[2], (1.1, 1.2, 1.3, 1.4)),
        (dates[3], (1.4, 1.3, 1.2, 1.1)),
    ):
        for sym, px in zip(syms, rets, strict=True):
            close.loc[(sym, d1)] = px
    factor = pd.Series(0.0, index=idx)
    # Day0: A>B>C>D ; Day1: D>C>B>A ; Day2: A>B>C>D
    ranks = {
        dates[0]: (4, 3, 2, 1),
        dates[1]: (1, 2, 3, 4),
        dates[2]: (4, 3, 2, 1),
        dates[3]: (4, 3, 2, 1),
    }
    for d, rs in ranks.items():
        for sym, r in zip(syms, rs, strict=True):
            factor.loc[(sym, d)] = float(r)
    panel = pd.DataFrame({"close": close})
    protocol = make_protocol(
        signal_lag=0,
        horizon_bars=1,
        n_groups=2,
        allow_short=False,
        min_cross_section=2,
        min_ic_samples=1,
        rebalance="daily",
    )
    _, metrics, _, tables = compute_predictive_metrics(panel, factor, protocol)
    assert tables["group_turnover_definition"].startswith("0.5*sum")
    # Day0 top={A,B} w=0.5 each; Day1 top={C,D} w=0.5 each.
    # delta: A:-0.5,B:-0.5,C:+0.5,D:+0.5 → 0.5*sum|Δ|=1.0
    assert tables["group_turnover"][0] == pytest.approx(1.0)
    assert _metric_map(metrics)["group_turnover_mean"].value == pytest.approx(
        float(np.mean(tables["group_turnover"]))
    )


# ---------------------------------------------------------------------------
# Formal trading / horizon>1
# ---------------------------------------------------------------------------


def test_formal_backtest_horizon_mismatch_unavailable() -> None:
    panel = make_panel(("AAA", "BBB", "CCC"), periods=40)
    values = panel["close"].astype(float)
    protocol = make_protocol(horizon_bars=5, rebalance="daily")
    ok, reason = formal_trading_supported(protocol)
    assert ok is False
    findings, metrics, tables = run_formal_backtest(panel, values, protocol)
    assert any(f.name == "BACKTEST_PROTOCOL_UNSUPPORTED" for f in findings)
    mm = _metric_map(metrics)
    assert mm["backtest_total_return"].unavailable_reason == reason
    assert tables["protocol"]["horizon_bars"] == 5


def test_formal_backtest_daily_vs_weekly_spy() -> None:
    panel = make_panel(("AAA", "BBB", "CCC"), periods=40)
    if "open" not in panel.columns:
        panel = panel.copy()
        panel["open"] = panel["close"]
    values = panel["close"].astype(float)
    calls: list[dict] = []

    class SpyBT:
        def __init__(self, data, **kwargs):
            calls.append(dict(kwargs))
            from skills.backtest import VectorBacktester

            self._inner = VectorBacktester(data, **kwargs)

        def run(self, weights):
            return self._inner.run(weights)

    daily = make_protocol(
        horizon_bars=1, rebalance="daily", trade_at="close", signal_lag=1, n_groups=3
    )
    weekly = make_protocol(
        horizon_bars=1, rebalance="weekly", trade_at="close", signal_lag=1, n_groups=3
    )
    run_formal_backtest(panel, values, daily, backtester_factory=SpyBT)
    run_formal_backtest(panel, values, weekly, backtester_factory=SpyBT)
    assert calls[0]["trade_at"] == "close"
    assert calls[0]["signal_lag"] == 1
    findings_d, _, tables_d = run_formal_backtest(panel, values, daily)
    findings_w, _, tables_w = run_formal_backtest(panel, values, weekly)
    assert any(f.name == "BACKTEST_COMPLETE" for f in findings_d)
    assert any(f.name == "BACKTEST_COMPLETE" for f in findings_w)
    assert len(tables_w["rebalance_weight_dates"]) < len(tables_d["rebalance_weight_dates"])


def test_p0_1_formal_backtest_pair_rejects_forged_metrics_dict() -> None:
    from skills.analyze.contracts import protocol_content_hash, verified_backtest_metrics
    from skills.backtest.vector import BacktestResult

    with pytest.raises(TypeError, match="cannot be constructed directly"):
        FormalBacktestPair(
            before={"total_return": 1.0, "max_drawdown": 0.1, "avg_daily_turnover": 0.1},
            after={"total_return": 99.0, "max_drawdown": 0.1, "avg_daily_turnover": 0.1},
            protocol_content_hash="a" * 64,
        )

    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    weights = pd.DataFrame({"AAA": [1.0, 1.0, 1.0]}, index=idx)
    turnover = weights.diff().fillna(weights).abs().sum(axis=1)
    rets = pd.Series([0.0, 0.1, 0.1], index=idx)
    equity = (1.0 + rets).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    result_df = pd.DataFrame(
        {
            "equity": equity,
            "drawdown": drawdown,
            "turnover": turnover,
            "return": rets,
        },
        index=idx,
    )
    forged_metrics = BacktestResult(
        executed_weights=weights,
        result_df=result_df,
        metrics={"total_return": 99.0, "max_drawdown": 0.0, "avg_daily_turnover": 0.0},
    )
    verified = verified_backtest_metrics(forged_metrics)
    assert verified["total_return"] == pytest.approx(0.21)
    assert verified["total_return"] != 99.0

    # Forged equity with zero returns must not yield total_return=98.
    forged_equity_df = pd.DataFrame(
        {
            "equity": [1.0, 50.0, 99.0],
            "drawdown": [0.0, 0.0, 0.0],
            "turnover": [0.0, 0.0, 0.0],
            "return": [0.0, 0.0, 0.0],
        },
        index=idx,
    )
    with pytest.raises(ValueError, match="equity inconsistent"):
        verified_backtest_metrics(
            BacktestResult(
                executed_weights=weights,
                result_df=forged_equity_df,
                metrics={"total_return": 98.0},
            )
        )

    # Forged drawdown / turnover columns must also fail verification.
    forged_dd = result_df.copy()
    forged_dd["drawdown"] = [-0.5, -0.5, -0.5]
    with pytest.raises(ValueError, match="drawdown inconsistent"):
        verified_backtest_metrics(
            BacktestResult(executed_weights=weights, result_df=forged_dd, metrics={})
        )
    forged_to = result_df.copy()
    forged_to["turnover"] = [9.0, 9.0, 9.0]
    with pytest.raises(ValueError, match="turnover inconsistent"):
        verified_backtest_metrics(
            BacktestResult(executed_weights=weights, result_df=forged_to, metrics={})
        )

    panel = make_panel(("AAA", "BBB", "CCC", "DDD"), periods=20)
    cand = panel["close"].astype(float)
    pool = cand * 0.5
    protocol = make_protocol(
        signal_lag=0, min_ic_samples=1, min_cross_section=2, horizon_bars=1
    )
    # Direct construction of FormalBacktestPair is forbidden (E2).
    with pytest.raises(TypeError, match="cannot be constructed directly"):
        FormalBacktestPair(
            before=forged_metrics,
            after=forged_metrics,
            protocol_content_hash=protocol_content_hash(protocol),
        )

    # Hand-forged unrelated BacktestResult objects must not yield numeric deltas
    # even if internally self-consistent — no caller-supplied verified issuer.
    forged_pair = object.__new__(FormalBacktestPair)
    object.__setattr__(forged_pair, "before", forged_metrics)
    object.__setattr__(forged_pair, "after", forged_metrics)
    object.__setattr__(
        forged_pair, "protocol_content_hash", protocol_content_hash(protocol)
    )
    object.__setattr__(forged_pair, "panel_hash", "0" * 64)
    object.__setattr__(forged_pair, "candidate_hash", "0" * 64)
    object.__setattr__(forged_pair, "ordered_pool_hash", "0" * 64)
    object.__setattr__(forged_pair, "shared_sample_hash", "0" * 64)
    object.__setattr__(forged_pair, "before_weights_hash", "0" * 64)
    object.__setattr__(forged_pair, "after_weights_hash", "0" * 64)
    object.__setattr__(forged_pair, "engine_version", "3.0.0")
    object.__setattr__(forged_pair, "engine_name", "VectorBacktester")
    object.__setattr__(forged_pair, "_frozen", True)
    findings, metrics, _ = compare_candidate_to_pool(
        panel, cand, {"p1": pool}, protocol, formal_before_after=forged_pair
    )
    assert any(f.name == "POOL_FORMAL_RESULT_INVALID" for f in findings)
    mm = _metric_map(metrics)
    assert mm["pool_portfolio_return_delta"].value is None
    assert mm["pool_portfolio_return_delta"].unavailable_reason == "formal_result_unverified"


def test_e2_official_formal_pair_runner_spy_and_deltas(monkeypatch) -> None:
    from skills.analyze.factor_evaluation import _working_frame
    from skills.backtest import VectorBacktester as RealBT

    panel = make_panel(("AAA", "BBB", "CCC", "DDD"), periods=40)
    if "open" not in panel.columns:
        panel = panel.copy()
        panel["open"] = panel["close"]
    cand = panel["close"].astype(float)
    pool = {"p1": cand * 0.5}
    protocol = make_protocol(
        horizon_bars=1,
        rebalance="daily",
        trade_at="close",
        signal_lag=1,
        n_groups=3,
        min_ic_samples=1,
        min_cross_section=2,
    )
    _, frame = _working_frame(panel, cand, protocol)
    assert frame is not None
    before_w = build_long_short_weights(frame["fac_val"], protocol).ffill().fillna(0.0)
    after_w = (before_w * 0.5).fillna(0.0)
    calls: list[dict] = []

    class SpyBT:
        def __init__(self, data, **kwargs):
            calls.append(dict(kwargs))
            self._inner = RealBT(data, **kwargs)

        def run(self, weights):
            return self._inner.run(weights)

    monkeypatch.setattr(
        "skills.analyze.factor_incremental.VectorBacktester", SpyBT
    )
    pair = run_official_formal_backtest_pair(
        panel,
        protocol,
        cand,
        pool,
        before_weights=before_w,
        after_weights=after_w,
    )
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert pair.is_issued()
    findings, metrics, _ = compare_candidate_to_pool(
        panel, cand, pool, protocol, formal_before_after=pair
    )
    assert not any(f.name == "POOL_FORMAL_RESULT_INVALID" for f in findings)
    mm = _metric_map(metrics)
    assert mm["pool_portfolio_return_delta"].value is not None
    assert mm["pool_portfolio_drawdown_delta"].value is not None
    assert mm["pool_portfolio_turnover_delta"].value is not None


def test_f1_formal_pair_immutable_digest_bound_issuance() -> None:
    """Ordinary setattr blocked; object.__setattr__/result mutation clears is_issued."""
    from skills.analyze.factor_evaluation import _working_frame

    panel = make_panel(("AAA", "BBB", "CCC", "DDD"), periods=40)
    if "open" not in panel.columns:
        panel = panel.copy()
        panel["open"] = panel["close"]
    cand = panel["close"].astype(float)
    pool = {"p1": cand * 0.5}
    protocol = make_protocol(
        horizon_bars=1,
        rebalance="daily",
        trade_at="close",
        signal_lag=1,
        n_groups=3,
        min_ic_samples=1,
        min_cross_section=2,
    )
    _, frame = _working_frame(panel, cand, protocol)
    assert frame is not None
    before_w = build_long_short_weights(frame["fac_val"], protocol).ffill().fillna(0.0)
    after_w = (before_w * 0.5).fillna(0.0)
    pair = run_official_formal_backtest_pair(
        panel,
        protocol,
        cand,
        pool,
        before_weights=before_w,
        after_weights=after_w,
    )
    assert pair.is_issued()
    with pytest.raises(AttributeError, match="immutable"):
        pair.before = pair.after
    assert pair.is_issued()

    object.__setattr__(pair, "before", pair.after)
    assert pair.is_issued() is False
    findings, metrics, _ = compare_candidate_to_pool(
        panel, cand, pool, protocol, formal_before_after=pair
    )
    assert any(f.name == "POOL_FORMAL_RESULT_INVALID" for f in findings)
    mm = _metric_map(metrics)
    assert mm["pool_portfolio_return_delta"].value is None
    assert mm["pool_portfolio_return_delta"].unavailable_reason == "formal_result_unverified"

    pair2 = run_official_formal_backtest_pair(
        panel,
        protocol,
        cand,
        pool,
        before_weights=before_w,
        after_weights=after_w,
    )
    assert pair2.is_issued()
    mutated = pair2.before.result_df.copy(deep=True)
    mutated.iloc[0, mutated.columns.get_loc("return")] = 0.42
    object.__setattr__(pair2.before, "result_df", mutated)
    assert pair2.is_issued() is False
    findings2, metrics2, _ = compare_candidate_to_pool(
        panel, cand, pool, protocol, formal_before_after=pair2
    )
    assert any(f.name == "POOL_FORMAL_RESULT_INVALID" for f in findings2)
    assert _metric_map(metrics2)["pool_portfolio_return_delta"].value is None


def test_f2_no_create_issuer_no_factory_param_and_evil_signature() -> None:
    """No caller BacktestResult issuer; public runner has no backtester_factory."""
    import inspect

    import skills.analyze.contracts as contracts_mod

    assert not hasattr(FormalBacktestPair, "_create")
    assert not hasattr(contracts_mod, "_register_formal_pair_seal")
    sig = inspect.signature(run_official_formal_backtest_pair)
    assert "backtester_factory" not in sig.parameters
    with pytest.raises(TypeError):
        run_official_formal_backtest_pair(  # type: ignore[call-arg]
            object(),
            object(),
            object(),
            {},
            before_weights=pd.DataFrame(),
            after_weights=pd.DataFrame(),
            backtester_factory=object,
        )


def test_e1_full_prefix_cuts_catch_day9_lookahead_of_day10() -> None:
    """20 unique days: leak only on day-9 reading day-10 must HARD_FAIL under full cuts."""
    from skills.analyze.causality import _cut_points

    panel = make_panel(("AAA", "BBB"), periods=20)
    times = sorted(panel.index.get_level_values("eob").unique())
    assert len(times) == 20
    day9 = times[8]
    day10 = times[9]
    spec = make_spec()

    def sentinel(df: pd.DataFrame) -> pd.Series:
        out = df["close"].astype(float).copy()
        # Contaminate day-9 only when day-10 is present in the panel copy.
        present = set(df.index.get_level_values("eob").unique())
        if day10 in present:
            mask = df.index.get_level_values("eob") == day9
            out.loc[mask] = float(df.loc[df.index.get_level_values("eob") == day10, "close"].mean())
        return out

    findings = verify_prefix_causality(
        panel,
        datetime_pos=1,
        recompute=_bound(spec, sentinel),
        spec=spec,
        min_prefix_rows=2,
        cut_mode="full",
    )
    hard = [
        f
        for f in findings
        if (not f.passed)
        and f.severity is FindingSeverity.HARD_FAIL
        and f.name == "CAUSALITY_PREFIX_RECOMPUTE"
    ]
    assert hard, findings
    assert any(str(day9) in str(f.details.get("cut", "")) for f in hard), hard
    assert all(f.details.get("n_cuts") == 19 for f in hard), hard[0].details

    # Sampled all-pass is non-proof SOFT_FAIL, never INFO pass.
    sampled_ok = verify_prefix_causality(
        panel,
        datetime_pos=1,
        recompute=_bound(
            spec, lambda df: df["close"].groupby(level=0).transform(lambda s: s.shift(1))
        ),
        spec=spec,
        min_prefix_rows=2,
        cut_mode="sampled",
    )
    assert sampled_ok[0].passed is False
    assert sampled_ok[0].name == "CAUSALITY_PREFIX_SAMPLED_NON_PROOF"
    assert sampled_ok[0].severity is FindingSeverity.SOFT_FAIL
    assert sampled_ok[0].details["cut_mode"] == "sampled"
    assert sampled_ok[0].details["n_cuts"] < 19
    assert sampled_ok[0].details["n_cuts"] >= 2

    # full mode with n=2 timestamps yields exactly one checkable cut.
    two = pd.Index(times[:2])
    assert len(_cut_points(two, mode="full")) == 1


def test_f3_sampled_leak_still_hard_fail_and_n2_cut() -> None:
    """Sampled mode still HARD_FAIL on real leak; n=2 full has one cut."""
    from skills.analyze.causality import _cut_points

    panel = make_panel(("AAA", "BBB"), periods=20)
    times = sorted(panel.index.get_level_values("eob").unique())
    # Place leak on a sampled cut (n//2 == 10 -> times[10]).
    leak_day = times[10]
    future_day = times[11]
    spec = make_spec()

    def sentinel(df: pd.DataFrame) -> pd.Series:
        out = df["close"].astype(float).copy()
        present = set(df.index.get_level_values("eob").unique())
        if future_day in present:
            mask = df.index.get_level_values("eob") == leak_day
            out.loc[mask] = float(
                df.loc[df.index.get_level_values("eob") == future_day, "close"].mean()
            )
        return out

    findings = verify_prefix_causality(
        panel,
        datetime_pos=1,
        recompute=_bound(spec, sentinel),
        spec=spec,
        min_prefix_rows=2,
        cut_mode="sampled",
    )
    hard = [
        f
        for f in findings
        if (not f.passed)
        and f.severity is FindingSeverity.HARD_FAIL
        and f.name == "CAUSALITY_PREFIX_RECOMPUTE"
    ]
    assert hard, findings
    assert all(f.details.get("cut_mode") == "sampled" for f in hard)

    two = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    assert _cut_points(two, mode="full") == [two[0]]
    assert _cut_points(pd.DatetimeIndex(["2024-01-01"]), mode="full") == []


def test_facade_records_recompute_binding_hash() -> None:
    panel = make_panel(("AAA", "BBB"), periods=12)
    spec = make_spec()
    protocol = make_protocol()

    def causal(df: pd.DataFrame) -> pd.Series:
        return df["close"].groupby(level=0).transform(lambda s: s.shift(1))

    bound = _bound(spec, causal)
    facade = AnalyzeFacade(prefix_recompute=lambda s: bound)
    result = facade.preflight(panel=panel, spec=spec, protocol=protocol)
    assert result.input_hashes["recompute_binding"] == (
        f"{spec.content_hash}:{spec.formula_fingerprint}:{bound._seal}"
    )


def test_p1_5_int64_mask_hard_fails() -> None:
    panel = make_panel(("AAA", "BBB"), periods=6)
    values = panel["close"].astype(float)
    mask = pd.Series(1, index=values.index, dtype="int64")
    findings = validate_output_alignment(
        values=values,
        valid_mask=mask,
        panel=panel,
        warmup=2,
        missing_policy="keep_nan",
    )
    assert any(f.name == "ALIGNMENT_MASK_DTYPE" and not f.passed for f in findings)


def test_failure_code_mapping_table() -> None:
    samples = {
        "INPUT_TIME_CONVERSION": FailureCode.TIME_CONVERSION_FAILED,
        "INPUT_UNIQUE_KEYS": FailureCode.DUPLICATE_LOGICAL_KEY,
        "SPEC_INVALID_PARAM": FailureCode.INVALID_PARAMETERS,
        "ALIGNMENT_NON_NUMERIC": FailureCode.INVALID_OUTPUT_DTYPE,
        "CAUSALITY_RECOMPUTE_SPEC_MISMATCH": FailureCode.HASH_MISMATCH,
        "CAUSALITY_RECOMPUTE_FORMULA_MISMATCH": FailureCode.HASH_MISMATCH,
        "ALIGNMENT_NON_FINITE": FailureCode.INVALID_OUTPUT_DTYPE,
        "ALIGNMENT_MASK_NULLABLE_NA": FailureCode.INVALID_OUTPUT_TYPE,
    }
    for name, expected in samples.items():
        finding = Finding(
            name=name,
            severity=FindingSeverity.HARD_FAIL,
            passed=False,
            message="x",
        )
        assert map_hard_fail_code(finding) is expected
    for name, code in EXACT_FAILURE_CODES.items():
        assert isinstance(code, FailureCode), name
    for _prefix, code in PREFIX_FAILURE_CODES:
        assert isinstance(code, FailureCode)


def test_skipped_does_not_mask_root_failure() -> None:
    from skills.factor_mining.adapters.analyze import map_analyze_result_to_report
    from skills.factor_mining.contracts import EvaluationRequest
    from tests.skills.factor_mining.builders import make_object_ref, make_provenance

    panel = make_panel(("AAA", "BBB"), periods=8)
    protocol = make_protocol(datetime_level="date")
    spec = make_spec()
    facade = AnalyzeFacade()
    native = facade.evaluate(
        panel=panel,
        spec=spec,
        protocol=protocol,
        values=panel["close"].astype(float),
    )
    assert native.hard_failed
    req = EvaluationRequest(
        request_id="r1",
        namespace="ns",
        brief_ref=make_object_ref(
            object_type="ResearchBrief",
            object_id="brief-1",
            content_hash="a" * 64,
            namespace="ns",
        ),
        factor_ref=make_object_ref(
            object_type="FactorSpec",
            object_id="factor-1",
            content_hash=spec.content_hash,
            namespace="ns",
        ),
        execution_ref=None,
        protocol_id="p1",
        data_version="data-v1",
        split_id="train",
    )
    report = map_analyze_result_to_report(
        native,
        request=req,
        factor_ref=req.factor_ref,
        provenance=make_provenance(namespace="ns"),
    )
    assert report.failure is not None
    assert "SKIPPED" not in report.failure.details.get("root_native_codes", ["SKIPPED"])
    assert report.failure.code is FailureCode.INVALID_INDEX_SCHEMA


def test_spec_static_checks_ok() -> None:
    findings = validate_spec(make_spec(), allowed_fields=("close",))
    assert any(f.name == "SPEC_STRUCTURE_OK" for f in findings)
