"""Integration: custom panel → Phase 02 execution → Analyze → EvaluationReport."""

from __future__ import annotations

import pandas as pd
import pytest

from skills.analyze import AnalyzeFacade
from skills.analyze.causality import BoundPrefixRecompute
from skills.analyze.contracts import ProtocolSnapshot
from skills.factor_mining import (
    AnalyzeAdapter,
    EvaluationRequest,
    FactorComputeRequest,
    FormulaKind,
    FunctionRef,
    StructuredFormula,
)
from skills.factor_mining.adapters import (
    DataManagerArtifactStore,
    FactorExecutionAdapter,
    load_execution_series,
)
from skills.factor_mining.adapters.execution_identity import (
    callable_fingerprint_from_execution,
)
from skills.store.data_manager import DataManager
from tests.fixtures.market_data import make_panel
from tests.skills.factor_mining.builders import (
    make_brief,
    make_factor_spec,
    make_object_ref,
)


def _protocol_for(brief, spec) -> ProtocolSnapshot:
    thresholds: dict = {}
    if brief.acceptance.min_coverage is not None:
        thresholds["min_coverage"] = brief.acceptance.min_coverage
    if brief.acceptance.min_rank_ic_ir is not None:
        thresholds["min_rank_ic_ir"] = brief.acceptance.min_rank_ic_ir
    if brief.acceptance.max_turnover is not None:
        thresholds["max_turnover"] = brief.acceptance.max_turnover
    return ProtocolSnapshot(
        horizon_bars=brief.horizon_bars,
        direction=spec.expected_direction,
        n_groups=3,
        tie_rule="average",
        rebalance=brief.rebalance,
        commission=float(brief.cost.commission),
        slippage=float(brief.cost.slippage),
        parameter_neighborhood={
            str(k): tuple(v)
            for k, v in dict(brief.robustness.parameter_neighborhood).items()
        },
        regimes=tuple(brief.robustness.regime_slices),
        time_subsamples=tuple(brief.robustness.time_subsamples),
        random_seed=int(brief.robustness.random_seed),
        multiple_testing_budget=int(brief.multiple_testing_budget),
        thresholds=thresholds,
        symbol_level=brief.symbol_level,
        datetime_level=brief.datetime_level,
        timezone=brief.timezone,
        required_fields=tuple(spec.required_fields),
        min_cross_section=2,
        min_ic_samples=3,
        bootstrap_samples=20,
        bootstrap_block_size=3,
        ic_decay_horizons=(1,),
        trade_at="close",
        signal_lag=int(brief.trading.execution_delay_bars),
        return_mode="forward",
        allow_short=bool(brief.trading.allow_short),
        require_prefix_recompute=True,
        universe=tuple(brief.universe),
    )




def test_phase03_custom_panel_to_evaluation_report(tmp_path) -> None:
    panel = make_panel(("AAA", "BBB", "CCC"), periods=40)
    panel = panel.copy()
    panel.index = panel.index.reorder_levels(["eob", "symbol"]).set_names(
        ["date", "symbol"]
    )
    snapshot = panel.copy(deep=True)

    from skills.factor_mining.contracts import TradingConstraints

    brief = make_brief(
        datetime_level="date",
        timezone="naive",
        horizon_bars=1,
        rebalance="daily",
        universe=("AAA", "BBB", "CCC"),
        trading=TradingConstraints(
            long_only=False,
            allow_short=True,
            rebalance="daily",
            execution_delay_bars=1,
        ),
    )
    spec = make_factor_spec(
        brief=brief,
        formula=StructuredFormula(
            kind=FormulaKind.FUNCTION_REF,
            function_ref=FunctionRef(
                module="skills.compute.indicators",
                name="roc",
            ),
            params={"period": 2},
        ),
        required_fields=("close",),
        window=2,
        warmup=2,
        lag=0,
    )
    protocol = _protocol_for(brief, spec)

    dm = DataManager(data_root=str(tmp_path))
    store = DataManagerArtifactStore(dm)
    persisted: list = []

    def _persist(key, payload):
        from skills.factor_mining.contracts import ArtifactRef, content_hash

        ref = ArtifactRef(
            kind="analyze_native",
            artifact_id=key.replace("/", "_"),
            namespace="ns.demo",
            content_hash=content_hash(payload),
            uri=f"mem://{key}",
        )
        persisted.append(ref)
        return ref

    exec_adapter = FactorExecutionAdapter(
        resolve_factor_spec=lambda ref: spec,
        resolve_panel=lambda request: panel,
        artifact_store=store,
    )
    compute_req = FactorComputeRequest(
        request_id="p3-exec",
        namespace="ns.demo",
        experiment_id="exp-p3",
        execution_id="exec-p3",
        brief_ref=spec.brief_ref,
        factor_ref=make_object_ref(
            object_type="FactorSpec",
            object_id=spec.factor_id,
            content_hash=spec.content_hash,
            namespace=spec.provenance.namespace,
        ),
        data_version="data-v1",
        split_id="train",
    )
    execution = exec_adapter.execute(compute_req)
    assert execution.failure is None
    formula_fp = callable_fingerprint_from_execution(execution)
    assert formula_fp == execution.callable_fingerprint
    assert execution.fingerprint != formula_fp
    assert execution.execution_id == "exec-p3"
    assert execution.experiment_id == "exp-p3"

    # Official issuer is AnalyzeAdapter.build_prefix_recompute_capability (evaluate path).
    facade = AnalyzeFacade()
    adapter = AnalyzeAdapter(
        facade=facade,
        resolve_brief=lambda ref: brief,
        resolve_factor=lambda ref: spec,
        resolve_protocol=lambda protocol_id: protocol,
        resolve_execution=lambda ref: execution,
        load_series=lambda ref: load_execution_series(store, ref),
        load_panel=lambda request: panel,
        load_pool=lambda request: None,
        persist_artifact=_persist,
    )
    eval_req = EvaluationRequest(
        request_id="p3-eval",
        namespace="ns.demo",
        brief_ref=spec.brief_ref,
        factor_ref=make_object_ref(
            object_type="FactorSpec",
            object_id=spec.factor_id,
            content_hash=spec.content_hash,
            namespace=spec.provenance.namespace,
        ),
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id=execution.execution_id,
            content_hash=execution.fingerprint,
            namespace=spec.provenance.namespace,
        ),
        protocol_id="protocol-1",
        data_version="data-v1",
        split_id="train",
    )

    report = adapter.evaluate(eval_req)
    assert report.schema_version == "1.4.0"
    assert report.failure is None, report.failure
    assert persisted, "native AnalyzeResult must be persisted"
    assert {s.name for s in report.sections} <= {
        "data_quality",
        "formula_safety",
        "alignment",
        "predictive",
        "robustness",
        "trading",
        "pool_incremental",
    }
    native_fact_names = {fact.name for section in report.sections for fact in section.facts}
    assert {"rank_ic_ir", "coverage_worst", "group_turnover_mean"} <= native_fact_names
    values = load_execution_series(store, execution.values_ref)
    assert list(values.index.names) == ["date", "symbol"]
    pd.testing.assert_frame_equal(snapshot, panel)

    # P0-4: direct forge must fail.
    with pytest.raises(TypeError):
        BoundPrefixRecompute(spec.content_hash, formula_fp, lambda df: values * 0)

    pool_report = adapter.compare_to_pool(eval_req)
    pool_section = next(s for s in pool_report.sections if s.name == "pool_incremental")
    assert any(check.name == "POOL_UNAVAILABLE" for check in pool_section.checks) or any(
        fact.unavailable_reason == "pool_unavailable" for fact in pool_section.facts
    )
