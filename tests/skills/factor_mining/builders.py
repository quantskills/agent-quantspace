"""Shared builders for factor_mining contract tests."""

from __future__ import annotations

from skills.factor_mining import (
    SCHEMA_VERSION,
    AcceptanceCriteria,
    ArtifactRef,
    CostConstraints,
    EvidenceRef,
    FactorSpec,
    FormulaKind,
    FunctionRef,
    ObjectRef,
    Provenance,
    ResearchBrief,
    ResearchBudget,
    RiskConstraints,
    RobustnessGrid,
    SplitWindow,
    StructuredFormula,
    TradingConstraints,
)


def make_object_ref(
    object_type: str = "ResearchBrief",
    object_id: str = "brief-1",
    content_hash: str = "a" * 64,
    namespace: str = "ns.demo",
) -> ObjectRef:
    return ObjectRef(
        object_type=object_type,
        object_id=object_id,
        content_hash=content_hash,
        namespace=namespace,
    )


def make_artifact_ref(
    kind: str = "panel",
    artifact_id: str = "panel-1",
    namespace: str = "ns.demo",
    content_hash: str = "b" * 64,
) -> ArtifactRef:
    return ArtifactRef(
        kind=kind,
        artifact_id=artifact_id,
        namespace=namespace,
        content_hash=content_hash,
    )


def make_evidence_ref(
    evidence_id: str = "ev-1",
    source_report_id: str = "eval-1",
    section: str = "predictive",
    namespace: str = "ns.demo",
    content_hash: str = "c" * 64,
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        source_report_id=source_report_id,
        section=section,
        namespace=namespace,
        content_hash=content_hash,
    )


def make_provenance(
    producer: str = "test",
    namespace: str = "ns.demo",
    input_refs: tuple = (),
    data_version: str = "data-v1",
) -> Provenance:
    return Provenance(
        producer=producer,
        data_version=data_version,
        code_version="code-v1",
        experiment_version="exp-v1",
        namespace=namespace,
        input_refs=tuple(input_refs),
        created_at="2026-08-04T00:00:00",
    )


def make_brief(**overrides: object) -> ResearchBrief:
    payload = {
        "brief_id": "brief-1",
        "market": "CN",
        "asset_class": "etf",
        "universe": ("SHSE.510300", "SHSE.510500"),
        "frequency": "1d",
        "allowed_fields": ("open", "high", "low", "close", "volume"),
        "symbol_level": "symbol",
        "datetime_level": "eob",
        "timezone": "Asia/Shanghai",
        "adjustment": "post",
        "data_version": "data-v1",
        "train": SplitWindow("train", "2020-01-01", "2022-12-31", sealed=False),
        "validation": SplitWindow("validation", "2023-01-01", "2023-12-31", sealed=False),
        "sealed": SplitWindow("sealed", "2024-01-01", "2024-12-31", sealed=True),
        "horizon_bars": 5,
        "rebalance": "weekly",
        "cost": CostConstraints(commission=0.0003, slippage=0.0001),
        "risk": RiskConstraints(max_weight=0.2),
        "trading": TradingConstraints(long_only=True, rebalance="weekly"),
        "robustness": RobustnessGrid(random_seed=7),
        "multiple_testing_budget": 20,
        "budget": ResearchBudget(
            max_candidates=12,
            max_experiments=40,
            max_revisions=2,
            max_debate_rounds=2,
        ),
        "acceptance": AcceptanceCriteria(min_rank_ic_ir=0.3),
        "freeze_criteria": AcceptanceCriteria(require_pool_incremental=True),
        "oos_criteria": AcceptanceCriteria(min_rank_ic_ir=0.2),
        "provenance": make_provenance(),
        "schema_version": SCHEMA_VERSION,
    }
    payload.update(overrides)
    return ResearchBrief(**payload)  # type: ignore[arg-type]


def make_factor_spec(brief: ResearchBrief | None = None, **overrides: object) -> FactorSpec:
    brief = brief or make_brief()
    brief_ref = make_object_ref(
        object_type="ResearchBrief",
        object_id=brief.brief_id,
        content_hash=brief.content_hash,
        namespace=brief.provenance.namespace,
    )
    payload = {
        "factor_id": "factor-mom-1",
        "revision": 1,
        "brief_ref": brief_ref,
        "family": "trend_momentum",
        "hypothesis": "Medium-horizon momentum persists after costs.",
        "expected_direction": "long_high",
        "required_fields": ("close",),
        "formula": StructuredFormula(
            kind=FormulaKind.FUNCTION_REF,
            function_ref=FunctionRef(
                module="skills.compute.indicators",
                name="trend_score",
            ),
            params={"period": 20},
        ),
        "window": 20,
        "lag": 1,
        "warmup": 20,
        "missing_policy": "keep_nan",
        "availability_rule": "point_in_time",
        "output_dtype": "float64",
        "index_restore_policy": "restore_original_names_and_order",
        "applicable_regimes": ("trend",),
        "known_relations": ("related_to_mom_skip",),
        "falsification_tests": ("shuffle_labels_should_kill_ic",),
        "provenance": make_provenance(producer="generator"),
    }
    payload.update(overrides)
    return FactorSpec(**payload)  # type: ignore[arg-type]
