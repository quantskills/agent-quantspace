from __future__ import annotations

import math
from dataclasses import replace
from types import MappingProxyType

import pytest

from skills.factor_mining import (
    SCHEMA_VERSION,
    AgentTaskResult,
    AgentTaskView,
    ArtifactRef,
    CandidateStatus,
    CostConstraints,
    EvaluationReport,
    EvaluationSection,
    FactorComputeRequest,
    FactorExecutionResult,
    FactorSpec,
    FailureCode,
    FailureDetail,
    FormulaKind,
    FreezeManifest,
    FunctionRef,
    IndexSchema,
    MetricFact,
    ObjectRef,
    OOSAttempt,
    OOSResult,
    PoolDecision,
    PoolDecisionKind,
    Provenance,
    ReviewConclusion,
    ReviewReport,
    RobustnessGrid,
    RuleCheck,
    SectionStatus,
    Severity,
    SplitWindow,
    StructuredFormula,
    TaskLease,
    TaskResultStatus,
    canonical_json,
    canonical_value,
    content_hash,
    rebuild_dataclass,
    to_plain_dict,
    validate_agent_task_handoff,
)
from tests.skills.factor_mining.builders import (
    make_artifact_ref,
    make_brief,
    make_evidence_ref,
    make_factor_spec,
    make_object_ref,
    make_provenance,
)


def test_research_brief_requires_explicit_universe_and_sealed_split() -> None:
    brief = make_brief()
    assert brief.schema_version == SCHEMA_VERSION
    assert brief.content_hash == brief.compute_hash()
    brief.validate_hash()

    with pytest.raises(ValueError, match="universe"):
        make_brief(universe=())
    with pytest.raises(ValueError, match="sealed"):
        make_brief(
            sealed=SplitWindow("sealed", "2024-01-01", "2024-12-31", sealed=False)
        )


def test_research_brief_nested_round_trip_restores_typed_objects() -> None:
    brief = make_brief()
    plain = to_plain_dict(brief)
    restored = rebuild_dataclass(type(brief), plain)

    assert isinstance(restored.train, SplitWindow)
    assert isinstance(restored.validation, SplitWindow)
    assert isinstance(restored.sealed, SplitWindow)
    assert restored.sealed.sealed is True
    assert isinstance(restored.robustness.parameter_neighborhood, MappingProxyType)
    assert restored.content_hash == brief.content_hash
    assert content_hash(plain) == content_hash(to_plain_dict(restored))
    restored.validate_hash()


def test_factor_spec_round_trip_restores_formula_provenance_and_refs() -> None:
    factor = make_factor_spec()
    restored = rebuild_dataclass(FactorSpec, to_plain_dict(factor))

    assert isinstance(restored.brief_ref, ObjectRef)
    assert restored.brief_ref.object_id == factor.brief_ref.object_id
    assert isinstance(restored.formula, StructuredFormula)
    assert restored.formula.kind is FormulaKind.FUNCTION_REF
    assert isinstance(restored.formula.function_ref, FunctionRef)
    assert restored.formula.function_ref.name == "trend_score"
    assert isinstance(restored.formula.params, MappingProxyType)
    assert restored.formula.params["period"] == 20
    assert isinstance(restored.provenance, Provenance)
    assert restored.provenance.producer == "generator"
    assert restored.content_hash == factor.content_hash
    restored.validate_hash()


def test_mapping_fields_are_immutable() -> None:
    factor = make_factor_spec()
    with pytest.raises(TypeError):
        factor.formula.params["window"] = 99  # type: ignore[index]

    brief = make_brief(
        robustness=RobustnessGrid(
            parameter_neighborhood={"window": (10, 20)},
            random_seed=1,
        )
    )
    with pytest.raises(TypeError):
        brief.robustness.parameter_neighborhood["window"] = (1, 2)  # type: ignore[index]

    # Hash remains stable because mutation is rejected.
    assert factor.content_hash == factor.compute_hash()
    assert brief.content_hash == brief.compute_hash()


def test_canonical_json_rejects_nan_inf_and_non_string_keys() -> None:
    with pytest.raises(ValueError, match="NaN|Infinity"):
        canonical_json({"v": math.nan})
    with pytest.raises(ValueError, match="NaN|Infinity"):
        canonical_value({"v": math.inf})
    with pytest.raises(ValueError, match="NaN|Infinity"):
        canonical_value({"v": -math.inf})
    with pytest.raises(TypeError, match="str mapping keys"):
        canonical_json({1: "x"})  # type: ignore[dict-item]


def test_factor_spec_rejects_free_text_and_strategies_function_ref() -> None:
    with pytest.raises(ValueError, match="strategies"):
        StructuredFormula(
            kind=FormulaKind.FUNCTION_REF,
            function_ref=FunctionRef(module="strategies.cross_sectional.factors", name="x"),
            params={},
        )
    with pytest.raises(ValueError, match="function_ref"):
        StructuredFormula(kind=FormulaKind.FUNCTION_REF, function_ref=None, params={})
    with pytest.raises(ValueError, match="expression"):
        StructuredFormula(kind=FormulaKind.EXPRESSION, expression={}, params={})


def test_factor_spec_hash_changes_when_params_change() -> None:
    base = make_factor_spec()
    changed = make_factor_spec(
        formula=StructuredFormula(
            kind=FormulaKind.FUNCTION_REF,
            function_ref=FunctionRef(
                module="skills.compute.indicators",
                name="trend_score",
            ),
            params={"window": 40},
        ),
        content_hash="",
    )
    assert base.content_hash != changed.content_hash
    base.validate_hash()
    changed.validate_hash()


def test_refs_require_namespace_and_exact_hex_hash() -> None:
    with pytest.raises(ValueError, match="content_hash"):
        ObjectRef(object_type="FactorSpec", object_id="f1", content_hash="", namespace="ns")
    with pytest.raises(ValueError, match="64-character hex"):
        ObjectRef(
            object_type="FactorSpec",
            object_id="f1",
            content_hash="a" * 63,
            namespace="ns",
        )
    with pytest.raises(ValueError, match="namespace"):
        ObjectRef(
            object_type="FactorSpec",
            object_id="f1",
            content_hash="a" * 64,
            namespace="",
        )
    ok_upper = ObjectRef(
        object_type="FactorSpec",
        object_id="f1",
        content_hash="A" * 64,
        namespace="ns.demo",
    )
    assert ok_upper.content_hash == "A" * 64
    with pytest.raises(ValueError, match="namespace"):
        make_evidence_ref(namespace="")
    with pytest.raises(ValueError, match="64-character hex"):
        make_evidence_ref(content_hash="zz" * 32)
    with pytest.raises(ValueError, match="data_version"):
        Provenance(
            producer="test",
            data_version="",
            code_version="code-v1",
            experiment_version="exp-v1",
            namespace="ns.demo",
        )
    with pytest.raises(ValueError, match="namespace mismatch"):
        Provenance(
            producer="test",
            data_version="data-v1",
            code_version="code-v1",
            experiment_version="exp-v1",
            namespace="ns.demo",
            input_refs=(make_object_ref(namespace="other.ns"),),
        )
    with pytest.raises(ValueError, match="data_version must match"):
        make_brief(data_version="data-other")


def test_evaluation_report_is_isolated_from_agent_decisions() -> None:
    factor = make_factor_spec()
    evidence = make_evidence_ref()
    section = EvaluationSection(
        name="predictive",
        status=SectionStatus.COMPLETE,
        facts=(
            MetricFact(
                name="rank_ic_ir",
                value=0.5,
                unit="ratio",
                sample_range="validation",
                engine_version="analyze-1.0",
                data_version="data-v1",
                evidence=evidence,
            ),
        ),
        checks=(
            RuleCheck(
                name="coverage_ok",
                passed=True,
                severity=Severity.INFO,
                code=None,
                message="coverage above threshold",
                evidence=evidence,
            ),
        ),
    )
    report = EvaluationReport(
        report_id="eval-1",
        request_id="req-1",
        brief_ref=make_object_ref(
            object_type="ResearchBrief",
            object_id="brief-1",
            content_hash="a" * 64,
        ),
        factor_ref=make_object_ref(
            object_type="FactorSpec",
            object_id=factor.factor_id,
            content_hash=factor.content_hash,
        ),
        execution_ref=None,
        protocol_id="proto-1",
        data_version="data-v1",
        split_id="train",
        pool_refs=(),
        sections=(section,),
        provenance=make_provenance(producer="analyze", data_version="data-v1"),
        engine_version="analyze-1.0",
    )
    assert not hasattr(report, "interpretation")
    assert "interpretation" not in to_plain_dict(report)

    review = ReviewReport(
        report_id="rev-1",
        role_id="methodology_critic",
        factor_ref=report.factor_ref,
        evaluation_ref=make_object_ref(object_type="EvaluationReport", object_id="eval-1"),
        conclusion=ReviewConclusion.PASS,
        issues=(),
        allow_revision=False,
        requires_full_rerun=False,
        provenance=make_provenance(producer="methodology_critic"),
        rationale="mechanism looks coherent",
    )
    decision = PoolDecision(
        decision_id="pool-1",
        factor_ref=report.factor_ref,
        decision=PoolDecisionKind.WATCH,
        incremental_evidence=(make_evidence_ref(section="pool_incremental"),),
        residual_risks=("capacity_uncertain",),
        role_id="pool_synthesizer",
        provenance=make_provenance(producer="pool_synthesizer"),
        rationale="marginal diversification only",
    )
    assert review.rationale
    assert decision.rationale
    report.validate_hash()


def test_rule_check_hard_fail_requires_code() -> None:
    with pytest.raises(ValueError, match="failure code"):
        RuleCheck(
            name="lookahead",
            passed=False,
            severity=Severity.HARD_FAIL,
            code=None,
            message="future function",
        )


def test_factor_execution_result_success_and_failure_are_exclusive() -> None:
    factor = make_factor_spec()
    factor_ref = make_object_ref(
        object_type="FactorSpec",
        object_id=factor.factor_id,
        content_hash=factor.content_hash,
    )
    index_schema = IndexSchema(
        names=("symbol", "eob"),
        symbol_level="symbol",
        datetime_level="eob",
        level_order=(0, 1),
        timezone="Asia/Shanghai",
    )
    with pytest.raises(ValueError, match="values and mask"):
        FactorExecutionResult(
            request_id="exec-1",
            experiment_id="exp-1",
            execution_id="exec-1",
            brief_ref=make_object_ref(object_type="ResearchBrief"),
            factor_ref=factor_ref,
            values_ref=None,
            valid_mask_ref=None,
            index_schema=index_schema,
            provenance=make_provenance(producer="compute"),
            fingerprint="fp-1",
            callable_fingerprint="cf-1",
            data_version="data-v1",
            split_id="train",
            values_content_hash="a" * 64,
            valid_mask_content_hash="b" * 64,
        )
    with pytest.raises(ValueError, match="must not carry"):
        FactorExecutionResult(
            request_id="exec-1",
            experiment_id="exp-1",
            execution_id="exec-1",
            brief_ref=make_object_ref(object_type="ResearchBrief"),
            factor_ref=factor_ref,
            values_ref=make_artifact_ref(kind="factor_values", artifact_id="v1"),
            valid_mask_ref=None,
            index_schema=index_schema,
            provenance=make_provenance(producer="compute"),
            fingerprint="fp-1",
            callable_fingerprint="cf-1",
            data_version="data-v1",
            split_id="train",
            values_content_hash=None,
            valid_mask_content_hash=None,
            failure=FailureDetail(
                code=FailureCode.FACTOR_RUNTIME_FAILED,
                message="boom",
            ),
        )

    failed = FactorExecutionResult(
        request_id="exec-1",
        experiment_id="exp-1",
        execution_id="exec-1",
        brief_ref=make_object_ref(object_type="ResearchBrief"),
        factor_ref=factor_ref,
        values_ref=None,
        valid_mask_ref=None,
        index_schema=index_schema,
        provenance=make_provenance(producer="compute"),
        fingerprint="fp-1",
        callable_fingerprint="cf-1",
        data_version="data-v1",
        split_id="train",
        values_content_hash=None,
        valid_mask_content_hash=None,
        failure=FailureDetail(
            code=FailureCode.INVALID_INDEX_SCHEMA,
            message="bad index",
        ),
    )
    assert failed.failure is not None
    assert failed.failure.code is FailureCode.INVALID_INDEX_SCHEMA


def test_index_schema_symbol_and_datetime_level_semantics() -> None:
    custom = IndexSchema(
        names=("symbol", "trade_date"),
        symbol_level="symbol",
        datetime_level="trade_date",
        level_order=(0, 1),
        timezone="UTC",
    )
    assert custom.datetime_level == "trade_date"
    none_dt = IndexSchema(
        names=("symbol", None),
        symbol_level="symbol",
        datetime_level=None,
        level_order=(0, 1),
        timezone="UTC",
    )
    assert none_dt.names == ("symbol", None)
    reversed_ok = IndexSchema(
        names=("eob", "symbol"),
        symbol_level="symbol",
        datetime_level="eob",
        level_order=(1, 0),
        timezone="UTC",
    )
    assert reversed_ok.level_order == (1, 0)
    with pytest.raises(ValueError, match="level_order"):
        IndexSchema(
            names=("symbol", "eob"),
            symbol_level="symbol",
            datetime_level="eob",
            level_order=(0, 0),
            timezone="UTC",
        )
    with pytest.raises(ValueError, match="symbol_level"):
        IndexSchema(
            names=("sym", "eob"),
            symbol_level="sym",
            datetime_level="eob",
            level_order=(0, 1),
            timezone="UTC",
        )
    with pytest.raises(ValueError, match="symbol name"):
        IndexSchema(
            names=("eob", "symbol"),
            symbol_level="symbol",
            datetime_level="eob",
            level_order=(0, 1),
            timezone="UTC",
        )
    with pytest.raises(ValueError, match="datetime_level"):
        IndexSchema(
            names=("symbol", "eob"),
            symbol_level="symbol",
            datetime_level="trade_date",
            level_order=(0, 1),
            timezone="UTC",
        )
    with pytest.raises(ValueError, match="datetime_level None"):
        IndexSchema(
            names=("symbol", "eob"),
            symbol_level="symbol",
            datetime_level=None,
            level_order=(0, 1),
            timezone="UTC",
        )


def test_oos_attempt_lifecycle_defaults_to_running() -> None:
    manifest_ref = make_object_ref(object_type="FreezeManifest", object_id="m1")
    common = {
        "run_id": "run-1",
        "candidate_id": "candidate-1",
        "one_shot_key": "one-shot-1",
    }
    running = OOSAttempt(
        **common,
        attempt_id="a1",
        authorization_id="auth-1",
        manifest_ref=manifest_ref,
        sealed_split_id="sealed",
        started_at="2026-01-01T00:00:00",
    )
    assert running.status is TaskResultStatus.RUNNING
    assert running.finished_at == ""
    assert running.failure is None
    with pytest.raises(ValueError, match="empty finished_at"):
        OOSAttempt(
            **common,
            attempt_id="a1",
            authorization_id="auth-1",
            manifest_ref=manifest_ref,
            sealed_split_id="sealed",
            started_at="2026-01-01T00:00:00",
            finished_at="2026-01-01T01:00:00",
            status=TaskResultStatus.RUNNING,
        )
    with pytest.raises(ValueError, match="must not include failure"):
        OOSAttempt(
            **common,
            attempt_id="a1",
            authorization_id="auth-1",
            manifest_ref=manifest_ref,
            sealed_split_id="sealed",
            started_at="2026-01-01T00:00:00",
            status=TaskResultStatus.RUNNING,
            failure=FailureDetail(code=FailureCode.UNKNOWN, message="x"),
        )
    succeeded = OOSAttempt(
        **common,
        attempt_id="a1",
        authorization_id="auth-1",
        manifest_ref=manifest_ref,
        sealed_split_id="sealed",
        started_at="2026-01-01T00:00:00",
        finished_at="2026-01-01T01:00:00",
        status=TaskResultStatus.SUCCEEDED,
    )
    assert succeeded.finished_at
    with pytest.raises(ValueError, match="finished_at"):
        OOSAttempt(
            **common,
            attempt_id="a1",
            authorization_id="auth-1",
            manifest_ref=manifest_ref,
            sealed_split_id="sealed",
            started_at="2026-01-01T00:00:00",
            status=TaskResultStatus.SUCCEEDED,
        )
    with pytest.raises(ValueError, match="must not include failure"):
        OOSAttempt(
            **common,
            attempt_id="a1",
            authorization_id="auth-1",
            manifest_ref=manifest_ref,
            sealed_split_id="sealed",
            started_at="2026-01-01T00:00:00",
            finished_at="2026-01-01T01:00:00",
            status=TaskResultStatus.SUCCEEDED,
            failure=FailureDetail(code=FailureCode.UNKNOWN, message="x"),
        )
    with pytest.raises(ValueError, match="failure"):
        OOSAttempt(
            **common,
            attempt_id="a1",
            authorization_id="auth-1",
            manifest_ref=manifest_ref,
            sealed_split_id="sealed",
            started_at="2026-01-01T00:00:00",
            finished_at="2026-01-01T01:00:00",
            status=TaskResultStatus.FAILED,
            failure=None,
        )
    failed = OOSAttempt(
        **common,
        attempt_id="a1",
        authorization_id="auth-1",
        manifest_ref=manifest_ref,
        sealed_split_id="sealed",
        started_at="2026-01-01T00:00:00",
        finished_at="2026-01-01T01:00:00",
        status=TaskResultStatus.FAILED,
        failure=FailureDetail(code=FailureCode.UNKNOWN, message="x"),
    )
    assert failed.status is TaskResultStatus.FAILED
    restored = rebuild_dataclass(OOSAttempt, to_plain_dict(failed))
    assert restored.content_hash == failed.content_hash
    restored.validate_hash()
    tampered = to_plain_dict(failed)
    tampered["one_shot_key"] = "different-key"
    with pytest.raises(ValueError, match="content_hash"):
        rebuild_dataclass(OOSAttempt, tampered).validate_hash()


def test_oos_result_rejects_mismatched_evidence_namespace() -> None:
    ns = "ns.demo"
    manifest_ref = make_object_ref(
        object_type="FreezeManifest", object_id="m1", namespace=ns
    )
    evaluation_ref = make_object_ref(
        object_type="EvaluationReport", object_id="eval-1", namespace=ns
    )
    provenance = make_provenance(producer="oos", namespace=ns)
    common = {
        "authorization_id": "auth-1",
        "run_id": "run-1",
        "candidate_id": "candidate-1",
        "sealed_split_id": "sealed",
    }
    ok = OOSResult(
        **common,
        result_id="oos-1",
        attempt_id="a1",
        manifest_ref=manifest_ref,
        evaluation_ref=evaluation_ref,
        passed=True,
        evidence_refs=(make_evidence_ref(namespace=ns),),
        provenance=provenance,
        artifact_refs=(
            ArtifactRef(
                kind="analyze_native",
                artifact_id="native-oos-1",
                namespace=ns,
                content_hash="a" * 64,
            ),
        ),
    )
    restored = rebuild_dataclass(OOSResult, to_plain_dict(ok))
    assert restored.content_hash == ok.content_hash
    assert restored.evidence_refs[0].namespace == ns
    assert restored.artifact_refs[0].kind == "analyze_native"
    restored.validate_hash()
    with pytest.raises(ValueError, match="namespace mismatch"):
        OOSResult(
            **common,
            result_id="oos-1",
            attempt_id="a1",
            manifest_ref=manifest_ref,
            evaluation_ref=evaluation_ref,
            passed=True,
            evidence_refs=(make_evidence_ref(namespace="other.ns"),),
            provenance=provenance,
        )


def test_agent_task_view_uses_plain_role_id_and_optional_candidate_ref() -> None:
    lease = TaskLease(
        lease_id="lease-1",
        run_id="run-1",
        task_id="task-1",
        role_id="role.alpha",
        candidates_remaining=3,
        experiments_remaining=10,
        revisions_remaining=1,
        debate_rounds_remaining=2,
    )
    candidate_ref = make_object_ref(object_type="FactorSpec", object_id="factor-1")
    view = AgentTaskView(
        task_id="task-1",
        run_id="run-1",
        parent_task_id=None,
        role_id="role.alpha",
        goal="propose momentum factors",
        input_refs=(make_object_ref(),),
        input_hashes={"ref:0": "a" * 64},
        visibility=("brief",),
        lease=lease,
        attempt=1,
        debate_round=0,
        expected_output_type="FactorSpec",
        candidate_ref=candidate_ref,
        forbidden_actions=("metric_calculation", "sealed_oos"),
        must_check=("required_fields",),
        stop_conditions=("budget_exhausted",),
    )
    assert view.role_id == "role.alpha"
    assert view.candidate_ref is candidate_ref
    with pytest.raises(TypeError):
        view.input_hashes["x"] = "y"  # type: ignore[index]
    run_level = AgentTaskView(
        task_id="task-1",
        run_id="run-1",
        parent_task_id=None,
        role_id="role.alpha",
        goal="coordinate",
        input_refs=(),
        input_hashes={},
        visibility=(),
        lease=lease,
        attempt=1,
        debate_round=0,
        expected_output_type="ResearchDecision",
        candidate_ref=None,
    )
    assert run_level.candidate_ref is None
    with pytest.raises(ValueError, match="namespace mismatch"):
        AgentTaskView(
            task_id="task-1",
            run_id="run-1",
            parent_task_id=None,
            role_id="role.alpha",
            goal="propose",
            input_refs=(make_object_ref(namespace="other.ns"),),
            input_hashes={"ref:0": "a" * 64},
            visibility=(),
            lease=lease,
            attempt=1,
            debate_round=0,
            expected_output_type="FactorSpec",
            candidate_ref=candidate_ref,
        )
    with pytest.raises(ValueError, match="run_id"):
        AgentTaskView(
            task_id="task-1",
            run_id="run-1",
            parent_task_id=None,
            role_id="role.alpha",
            goal="propose",
            input_refs=(),
            input_hashes={},
            visibility=(),
            lease=TaskLease(
                lease_id="lease-1",
                run_id="other-run",
                task_id="task-1",
                role_id="role.alpha",
                candidates_remaining=1,
                experiments_remaining=1,
                revisions_remaining=1,
                debate_rounds_remaining=1,
            ),
            attempt=1,
            debate_round=0,
            expected_output_type="FactorSpec",
            candidate_ref=candidate_ref,
        )


def test_agent_task_result_status_envelope() -> None:
    with pytest.raises(ValueError, match="RUNNING"):
        AgentTaskResult(
            task_id="t1",
            run_id="r1",
            role_id="role.alpha",
            status=TaskResultStatus.RUNNING,
            output_type="ResearchDecision",
            output_ref=None,
            handoff_to="Controller",
        )
    with pytest.raises(ValueError, match="output_ref"):
        AgentTaskResult(
            task_id="t1",
            run_id="r1",
            role_id="role.alpha",
            status=TaskResultStatus.SUCCEEDED,
            output_type="ResearchDecision",
            output_ref=None,
            handoff_to="Controller",
        )
    with pytest.raises(ValueError, match="must not include failure"):
        AgentTaskResult(
            task_id="t1",
            run_id="r1",
            role_id="role.alpha",
            status=TaskResultStatus.SUCCEEDED,
            output_type="ResearchDecision",
            output_ref=make_object_ref(object_type="ResearchDecision", object_id="d1"),
            failure=FailureDetail(code=FailureCode.UNKNOWN, message="x"),
            handoff_to="Controller",
        )
    succeeded = AgentTaskResult(
        task_id="t1",
        run_id="r1",
        role_id="role.alpha",
        status=TaskResultStatus.SUCCEEDED,
        output_type="ResearchDecision",
        output_ref=make_object_ref(object_type="ResearchDecision", object_id="d1"),
        handoff_to="Controller",
    )
    assert succeeded.output_ref is not None
    with pytest.raises(ValueError, match="one ObjectRef"):
        AgentTaskResult(
            task_id="t1",
            run_id="r1",
            role_id="role.alpha",
            status=TaskResultStatus.SUCCEEDED,
            output_type="ResearchDecision",
            output_ref=[
                make_object_ref(object_type="ResearchDecision", object_id="d1")
            ],  # type: ignore[arg-type]
            handoff_to="Controller",
        )
    with pytest.raises(ValueError, match="handoff_to"):
        AgentTaskResult(
            task_id="t1",
            run_id="r1",
            role_id="role.alpha",
            status=TaskResultStatus.SUCCEEDED,
            output_type="ResearchDecision",
            output_ref=make_object_ref(object_type="ResearchDecision", object_id="d1"),
            handoff_to=" ",
        )
    with pytest.raises(ValueError, match="must not include output_ref"):
        AgentTaskResult(
            task_id="t1",
            run_id="r1",
            role_id="role.alpha",
            status=TaskResultStatus.FAILED,
            output_type="ResearchDecision",
            output_ref=make_object_ref(object_type="ResearchDecision", object_id="d1"),
            failure=FailureDetail(code=FailureCode.BUDGET_EXCEEDED, message="no budget"),
            handoff_to="Controller",
        )
    failed = AgentTaskResult(
        task_id="t1",
        run_id="r1",
        role_id="role.alpha",
        status=TaskResultStatus.FAILED,
        output_type="ResearchDecision",
        output_ref=None,
        failure=FailureDetail(code=FailureCode.BUDGET_EXCEEDED, message="no budget"),
        handoff_to="Controller",
    )
    assert failed.status is TaskResultStatus.FAILED
    assert failed.output_ref is None


def test_phase05_task_handoff_round_trip_and_neutral_rejections() -> None:
    """Phase 05 binds a return to a Controller-issued view without role registry."""
    factor_ref = make_object_ref(object_type="FactorSpec", object_id="factor-1")
    lease = TaskLease(
        lease_id="lease-1",
        run_id="run-1",
        task_id="task-1",
        role_id="role.alpha",
        candidates_remaining=2,
        experiments_remaining=3,
        revisions_remaining=1,
        debate_rounds_remaining=2,
    )
    view = AgentTaskView(
        task_id="task-1",
        run_id="run-1",
        parent_task_id="parent-1",
        role_id="role.alpha",
        goal="produce one candidate",
        input_refs=(make_object_ref(),),
        input_hashes={"ref:0": "a" * 64},
        visibility=("brief",),
        lease=lease,
        attempt=1,
        debate_round=0,
        expected_output_type="FactorSpec",
        candidate_ref=factor_ref,
    )
    result = AgentTaskResult(
        task_id="task-1",
        run_id="run-1",
        role_id="role.alpha",
        status=TaskResultStatus.SUCCEEDED,
        output_type="FactorSpec",
        output_ref=factor_ref,
        budget_consumed={"candidates": 1},
        handoff_to="Controller",
        parent_task_id="parent-1",
    )
    restored_view = rebuild_dataclass(AgentTaskView, to_plain_dict(view))
    restored_result = rebuild_dataclass(AgentTaskResult, to_plain_dict(result))
    assert restored_view == view
    assert restored_result == result
    validate_agent_task_handoff(restored_view, restored_result)

    with pytest.raises(ValueError, match="input_hashes"):
        replace(view, input_hashes={"ref:0": "f" * 64})
    with pytest.raises(ValueError, match="role_id"):
        validate_agent_task_handoff(view, replace(result, role_id="role.beta"))
    with pytest.raises(ValueError, match="parent_task_id"):
        validate_agent_task_handoff(view, replace(result, parent_task_id="other-parent"))
    with pytest.raises(ValueError, match="output_type"):
        validate_agent_task_handoff(
            view, replace(result, output_type="ResearchDecision")
        )
    with pytest.raises(ValueError, match="output_ref.object_type"):
        validate_agent_task_handoff(
            view,
            replace(
                result,
                output_ref=make_object_ref(
                    object_type="ResearchDecision", object_id="decision-1"
                ),
            ),
        )
    with pytest.raises(ValueError, match="unknown budget"):
        validate_agent_task_handoff(
            view, replace(result, budget_consumed={"other": 1})
        )
    with pytest.raises(ValueError, match="exceeds"):
        validate_agent_task_handoff(
            view, replace(result, budget_consumed={"candidates": 3})
        )

    foreign_namespace = "ns.foreign"
    foreign_success = replace(
        result,
        output_ref=make_object_ref(
            object_type="FactorSpec", object_id="foreign-factor", namespace=foreign_namespace
        ),
        evidence_refs=(make_evidence_ref(namespace=foreign_namespace),),
        artifact_refs=(make_artifact_ref(namespace=foreign_namespace),),
    )
    with pytest.raises(ValueError, match="authorized namespace"):
        validate_agent_task_handoff(view, foreign_success)

    foreign_failure = AgentTaskResult(
        task_id=view.task_id,
        run_id=view.run_id,
        role_id=view.role_id,
        status=TaskResultStatus.FAILED,
        output_type=view.expected_output_type,
        output_ref=None,
        evidence_refs=(make_evidence_ref(namespace=foreign_namespace),),
        artifact_refs=(make_artifact_ref(namespace=foreign_namespace),),
        failure=FailureDetail(code=FailureCode.RECOVERY_REQUIRED, message="failed"),
        handoff_to="Controller",
        parent_task_id=view.parent_task_id,
    )
    with pytest.raises(ValueError, match="authorized namespace"):
        validate_agent_task_handoff(view, foreign_failure)

    unscoped_view = replace(
        view,
        candidate_ref=None,
        input_refs=(),
        input_hashes={},
    )
    with pytest.raises(ValueError, match="authorized namespace"):
        validate_agent_task_handoff(unscoped_view, result)


def test_pool_and_review_contracts_round_trip() -> None:
    factor = make_factor_spec()
    factor_ref = make_object_ref(
        object_type="FactorSpec",
        object_id=factor.factor_id,
        content_hash=factor.content_hash,
    )
    review = ReviewReport(
        report_id="rev-1",
        role_id="methodology_critic",
        factor_ref=factor_ref,
        evaluation_ref=make_object_ref(object_type="EvaluationReport", object_id="eval-1"),
        conclusion=ReviewConclusion.PASS,
        issues=(),
        allow_revision=False,
        requires_full_rerun=False,
        provenance=make_provenance(producer="methodology_critic"),
    )
    decision = PoolDecision(
        decision_id="pool-1",
        factor_ref=factor_ref,
        decision=PoolDecisionKind.WATCH,
        incremental_evidence=(make_evidence_ref(section="pool_incremental"),),
        residual_risks=("capacity_uncertain",),
        role_id="pool_synthesizer",
        provenance=make_provenance(producer="pool_synthesizer"),
        rationale="marginal diversification only",
    )
    assert rebuild_dataclass(ReviewReport, to_plain_dict(review)).content_hash == (
        review.content_hash
    )
    assert rebuild_dataclass(PoolDecision, to_plain_dict(decision)).decision is (
        PoolDecisionKind.WATCH
    )


def test_factor_compute_request_is_execution_envelope_only() -> None:
    factor = make_factor_spec()
    request = FactorComputeRequest(
        request_id="req-1",
        namespace="ns.demo",
        experiment_id="exp-1",
        execution_id="exec-1",
        brief_ref=factor.brief_ref,
        factor_ref=make_object_ref(
            object_type="FactorSpec",
            object_id=factor.factor_id,
            content_hash=factor.content_hash,
        ),
        data_version="data-v1",
        split_id="validation",
        panel_artifact=make_artifact_ref(),
    )
    assert request.schema_version == SCHEMA_VERSION
    assert isinstance(factor.status, CandidateStatus)


def test_enum_fields_serialize_to_json_primitives() -> None:
    factor = make_factor_spec()
    plain = to_plain_dict(factor)
    assert plain["status"] == "proposed"
    assert type(plain["status"]) is str
    assert plain["formula"]["kind"] == "function_ref"
    assert type(plain["formula"]["kind"]) is str


def test_rebuild_rejects_unknown_fields_and_lossy_primitives() -> None:
    factor = make_factor_spec()
    plain = to_plain_dict(factor)
    with pytest.raises(ValueError, match="unknown fields"):
        rebuild_dataclass(FactorSpec, {**plain, "extra": 1})
    with pytest.raises(TypeError, match="int"):
        rebuild_dataclass(FactorSpec, {**plain, "revision": True})
    with pytest.raises(TypeError, match="int"):
        rebuild_dataclass(FactorSpec, {**plain, "revision": "1"})
    with pytest.raises(TypeError, match="bool"):
        rebuild_dataclass(
            type(make_brief().trading),
            {**to_plain_dict(make_brief().trading), "long_only": "yes"},
        )
    with pytest.raises(TypeError, match="mapping keys must be str"):
        rebuild_dataclass(
            FactorSpec,
            {
                **plain,
                "formula": {
                    **plain["formula"],
                    "params": {20: 1},  # type: ignore[dict-item]
                },
            },
        )


def test_research_brief_datetime_level_allows_custom_name_and_none() -> None:
    named = make_brief(datetime_level="trade_date")
    assert named.datetime_level == "trade_date"
    unnamed = make_brief(datetime_level=None, content_hash="")
    assert unnamed.datetime_level is None
    restored = rebuild_dataclass(type(unnamed), to_plain_dict(unnamed))
    assert restored.datetime_level is None
    assert restored.data_version == "data-v1"
    assert isinstance(restored.provenance, Provenance)


def test_namespace_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="namespace"):
        make_factor_spec(
            brief_ref=make_object_ref(namespace="other.ns"),
            provenance=make_provenance(namespace="ns.demo"),
            content_hash="",
        )


def test_content_hash_tamper_is_rejected_on_construction() -> None:
    with pytest.raises(ValueError, match="content_hash mismatch"):
        make_brief(content_hash="0" * 64)
    factor = make_factor_spec()
    with pytest.raises(ValueError, match="content_hash mismatch"):
        make_factor_spec(content_hash="1" * 64)
    review = ReviewReport(
        report_id="rev-1",
        role_id="methodology_critic",
        factor_ref=make_object_ref(
            object_type="FactorSpec",
            object_id=factor.factor_id,
            content_hash=factor.content_hash,
        ),
        evaluation_ref=make_object_ref(
            object_type="EvaluationReport", object_id="eval-1"
        ),
        conclusion=ReviewConclusion.PASS,
        issues=(),
        allow_revision=False,
        requires_full_rerun=False,
        provenance=make_provenance(producer="methodology_critic"),
    )
    review.validate_hash()
    with pytest.raises(ValueError, match="content_hash mismatch"):
        ReviewReport(
            report_id="rev-1",
            role_id="methodology_critic",
            factor_ref=review.factor_ref,
            evaluation_ref=review.evaluation_ref,
            conclusion=ReviewConclusion.PASS,
            issues=(),
            allow_revision=False,
            requires_full_rerun=False,
            provenance=review.provenance,
            content_hash="f" * 64,
        )


def _make_freeze_manifest(factor: FactorSpec | None = None) -> FreezeManifest:
    factor = factor or make_factor_spec()
    ns = factor.provenance.namespace
    factor_ref = make_object_ref(
        object_type="FactorSpec",
        object_id=factor.factor_id,
        content_hash=factor.content_hash,
        namespace=ns,
    )
    return FreezeManifest(
        manifest_id="fm-1",
        run_id="run-1",
        brief_ref=factor.brief_ref,
        factor_ref=factor_ref,
        universe=("SHSE.510300",),
        data_version="data-v1",
        split_refs={"train": "train", "validation": "validation", "sealed": "sealed"},
        compute_engine_version="compute-1",
        analyze_engine_version="analyze-1",
        evaluation_protocol_id="protocol-1",
        direction="long_high",
        params={"window": 20},
        missing_policy="keep_nan",
        adjustment_policy="post",
        outlier_policy="winsorize_1_99",
        neutralization_policy="none",
        holding_horizon_bars=5,
        rebalance="weekly",
        cost=CostConstraints(commission=0.0003),
        pool_baseline_refs=(),
        preflight_ref=make_object_ref(
            object_type="EvaluationReport", object_id="pre-1", namespace=ns
        ),
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult", object_id="exec-1", namespace=ns
        ),
        evaluation_ref=make_object_ref(
            object_type="EvaluationReport", object_id="eval-1", namespace=ns
        ),
        compare_ref=make_object_ref(
            object_type="EvaluationReport", object_id="cmp-1", namespace=ns
        ),
        review_refs=(
            make_object_ref(
                object_type="ReviewReport", object_id="rev-1", namespace=ns
            ),
        ),
        pool_decision_ref=make_object_ref(
            object_type="PoolDecision", object_id="pool-1", namespace=ns
        ),
        approval_ref=make_artifact_ref(
            kind="human_gate_1", artifact_id="approve-1", namespace=ns
        ),
        oos_thresholds={"min_rank_ic_ir": 0.2},
        oos_metric_selectors={
            "min_rank_ic_ir": {"fact_name": "rank_ic_ir", "operator": "gte"}
        },
        provenance=make_provenance(producer="controller", namespace=ns),
    )


def test_freeze_manifest_is_complete_immutable_and_round_trips() -> None:
    manifest = _make_freeze_manifest()
    assert manifest.adjustment_policy == "post"
    assert manifest.outlier_policy == "winsorize_1_99"
    assert manifest.neutralization_policy == "none"
    assert isinstance(manifest.approval_ref, ArtifactRef)
    assert isinstance(manifest.oos_thresholds, MappingProxyType)
    assert isinstance(manifest.oos_metric_selectors, MappingProxyType)
    with pytest.raises(TypeError):
        manifest.oos_thresholds["min_rank_ic_ir"] = 0.9  # type: ignore[index]
    restored = rebuild_dataclass(FreezeManifest, to_plain_dict(manifest))
    assert restored.content_hash == manifest.content_hash
    assert restored.approval_ref.artifact_id == "approve-1"
    assert restored.oos_thresholds["min_rank_ic_ir"] == 0.2
    restored.validate_hash()
    with pytest.raises(ValueError, match="oos_thresholds"):
        FreezeManifest(
            **{
                **{
                    k: getattr(manifest, k)
                    for k in (
                        "manifest_id",
                        "run_id",
                        "brief_ref",
                        "factor_ref",
                        "universe",
                        "data_version",
                        "split_refs",
                        "compute_engine_version",
                        "analyze_engine_version",
                        "evaluation_protocol_id",
                        "direction",
                        "params",
                        "missing_policy",
                        "adjustment_policy",
                        "outlier_policy",
                        "neutralization_policy",
                        "holding_horizon_bars",
                        "rebalance",
                        "cost",
                        "pool_baseline_refs",
                        "preflight_ref",
                        "execution_ref",
                        "evaluation_ref",
                        "compare_ref",
                        "review_refs",
                        "pool_decision_ref",
                        "approval_ref",
                        "oos_metric_selectors",
                        "provenance",
                    )
                },
                "oos_thresholds": {},
                "content_hash": "",
            }
        )
