"""AnalyzePort adapter mapping analyze-native results to Phase 01 reports."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pandas as pd

from skills.analyze.contracts import (
    ENGINE_VERSION,
    AnalyzeResult,
    Finding,
    FindingSeverity,
    PoolMemberSeries,
    ProtocolSnapshot,
    SpecSnapshot,
    protocol_content_hash,
)
from skills.analyze.facade import AnalyzeFacade
from skills.factor_mining.adapters.execution_identity import (
    callable_fingerprint_from_execution,
    execution_envelope_identity,
)
from skills.factor_mining.adapters.failure_codes import map_hard_fail_code
from skills.factor_mining.contracts import (
    EVALUATION_SECTIONS,
    SCHEMA_VERSION,
    ArtifactRef,
    EvaluationReport,
    EvaluationRequest,
    EvaluationSection,
    EvidenceRef,
    FactorExecutionResult,
    FactorSpec,
    FailureCode,
    FailureDetail,
    MetricFact,
    ObjectRef,
    Provenance,
    ResearchBrief,
    RuleCheck,
    SectionStatus,
    Severity,
    TypedPoolMember,
    content_hash,
)

ResolveBrief = Callable[[ObjectRef], ResearchBrief]
ResolveFactor = Callable[[ObjectRef], FactorSpec]
ResolveExecution = Callable[[ObjectRef], FactorExecutionResult]
ResolveProtocol = Callable[[str], ProtocolSnapshot]
LoadSeries = Callable[[ArtifactRef], pd.Series]
LoadPanel = Callable[[EvaluationRequest], pd.DataFrame]
LoadPool = Callable[[EvaluationRequest], Sequence[TypedPoolMember] | None]
PersistArtifact = Callable[[str, Mapping[str, Any]], ArtifactRef | None]

# Gate-1 freezes these official Analyze observations alongside thresholds.  The
# Controller deliberately does not derive coverage or select similarly named
# user-facing facts itself.
_OOS_THRESHOLD_SELECTORS: Mapping[str, Mapping[str, str]] = {
    "min_rank_ic_ir": {"fact_name": "rank_ic_ir", "operator": "gte"},
    "min_coverage": {"fact_name": "coverage_worst", "operator": "gte"},
    "max_turnover": {"fact_name": "group_turnover_mean", "operator": "lte"},
}


def frozen_oos_metric_selectors(
    thresholds: Mapping[str, float],
) -> dict[str, dict[str, str]]:
    """Return the canonical Analyze-native observations for frozen OOS gates."""
    selectors: dict[str, dict[str, str]] = {}
    for threshold_name in thresholds:
        selector = _OOS_THRESHOLD_SELECTORS.get(threshold_name)
        if selector is None:
            raise ValueError(
                f"unsupported OOS threshold without official Analyze selector: {threshold_name}"
            )
        selectors[threshold_name] = dict(selector)
    return selectors


def oos_report_passes_frozen_thresholds(
    report: EvaluationReport,
    *,
    thresholds: Mapping[str, float],
    selectors: Mapping[str, Mapping[str, str]],
) -> bool:
    """Compare a report to Gate-1 frozen official observations only.

    This is an Analyze boundary operation: it never recomputes metrics or
    aggregates per-field coverage in the Controller.
    """
    if report.failure is not None or any(
        (not check.passed) and check.severity is Severity.HARD_FAIL
        for section in report.sections
        for check in section.checks
    ):
        return False
    if set(selectors) != set(thresholds):
        return False
    facts_by_name: dict[str, list[MetricFact]] = {}
    for section in report.sections:
        for fact in section.facts:
            facts_by_name.setdefault(fact.name, []).append(fact)
    for threshold_name, threshold in thresholds.items():
        selector = selectors.get(threshold_name)
        if not isinstance(selector, Mapping):
            return False
        if set(selector) != {"fact_name", "operator"}:
            return False
        fact_name = selector.get("fact_name")
        operator = selector.get("operator")
        if not isinstance(fact_name, str) or operator not in {"gte", "lte"}:
            return False
        matches = facts_by_name.get(fact_name, [])
        if len(matches) != 1:
            return False
        fact = matches[0]
        if (
            fact.engine_version != report.engine_version
            or fact.data_version != report.data_version
        ):
            return False
        value = fact.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if operator == "gte" and float(value) < float(threshold):
            return False
        if operator == "lte" and float(value) > float(threshold):
            return False
    return True


def _execution_provenance_has_exact_refs(
    execution: FactorExecutionResult,
    *,
    brief_ref: ObjectRef | None = None,
    factor_ref: ObjectRef | None = None,
) -> list[str]:
    """Require exact ObjectRef matches in provenance (not type placeholders).

    Semantics: at least one exact match for each required core ref. Extra refs
    of other types are allowed. Duplicate exact copies of the same core ref are
    allowed; a wrong-hash ResearchBrief/FactorSpec does not satisfy the core.
    """
    errors: list[str] = []
    refs = tuple(execution.provenance.input_refs)
    if brief_ref is not None:
        if not any(
            isinstance(r, ObjectRef) and _object_refs_equal(r, brief_ref) for r in refs
        ):
            errors.append("provenance missing exact brief_ref")
    if factor_ref is not None:
        if not any(
            isinstance(r, ObjectRef) and _object_refs_equal(r, factor_ref) for r in refs
        ):
            errors.append("provenance missing exact factor_ref")
    return errors


def _typed_member_to_pool_series(
    item: TypedPoolMember,
    ref: ObjectRef,
    *,
    request: EvaluationRequest,
) -> tuple[PoolMemberSeries | None, list[str], FailureCode | None]:
    """Validate TypedPoolMember against one pool_ref; build facade member.

    Returns (member, errors, failure_code). failure_code is set when a single
    dominant code applies (HASH_MISMATCH for content, INVALID_PARAMETERS for
    split, HASH_MISMATCH for data_version, INVALID_REFERENCE otherwise).
    """
    from skills.factor_mining.adapters.series_codec import series_content_hash

    errors: list[str] = []
    code: FailureCode | None = None
    execution = item.execution
    values = item.values
    if not isinstance(values, pd.Series):
        return None, ["pool member values must be a Series"], FailureCode.INVALID_REFERENCE
    if ref.object_type != "FactorExecutionResult":
        errors.append("pool_ref.object_type must be FactorExecutionResult")
    if ref.object_id != execution.execution_id:
        errors.append("pool_ref.object_id must equal execution.execution_id")
    if ref.namespace != execution.provenance.namespace:
        errors.append("pool_ref.namespace mismatch vs execution")
    if ref.schema_version != execution.schema_version:
        errors.append("pool_ref.schema_version mismatch vs execution")
    envelope = execution_envelope_identity(execution)
    if ref.content_hash != envelope or execution.fingerprint != envelope:
        errors.append("pool_ref/execution envelope content_hash mismatch")
        code = FailureCode.HASH_MISMATCH
    if execution.data_version != request.data_version:
        errors.append("pool member data_version mismatch vs request")
        code = FailureCode.HASH_MISMATCH
    if execution.split_id != request.split_id:
        errors.append("pool member split_id mismatch vs request")
        code = FailureCode.INVALID_PARAMETERS
    if execution.provenance.data_version != request.data_version:
        errors.append("pool member provenance.data_version mismatch")
        code = FailureCode.HASH_MISMATCH
    if execution.provenance.namespace != request.namespace:
        errors.append("pool member provenance.namespace mismatch")
    if not _object_refs_equal(execution.brief_ref, request.brief_ref):
        errors.append(
            "pool member execution.brief_ref must equal request.brief_ref "
            "in all ObjectRef fields"
        )
        code = FailureCode.INVALID_REFERENCE
    if execution.values_ref is None:
        errors.append("pool member missing values_ref")
    else:
        vref = execution.values_ref
        if vref.kind != "factor_values":
            errors.append("values_ref.kind must be factor_values")
        if vref.artifact_id != f"{execution.execution_id}:values":
            errors.append("values_ref.artifact_id mismatch")
        if vref.namespace != request.namespace:
            errors.append("values_ref.namespace mismatch")
        if vref.schema_version != SCHEMA_VERSION:
            errors.append("values_ref.schema_version mismatch")
        if not vref.content_hash:
            errors.append("values_ref.content_hash must be non-empty")
    # Provenance must exact-include execution.brief_ref + execution.factor_ref.
    prov_errs = _execution_provenance_has_exact_refs(
        execution,
        brief_ref=execution.brief_ref,
        factor_ref=execution.factor_ref,
    )
    errors.extend(prov_errs)
    if execution.values_content_hash is None:
        errors.append("pool member missing values_content_hash")
        code = FailureCode.HASH_MISMATCH
    else:
        try:
            actual = series_content_hash(values)
        except Exception:  # noqa: BLE001
            return None, ["pool member values could not be hashed"], FailureCode.HASH_MISMATCH
        if actual != execution.values_content_hash:
            errors.append("pool member values content hash mismatch")
            code = FailureCode.HASH_MISMATCH
    if errors:
        return None, errors, code or FailureCode.INVALID_REFERENCE
    assert execution.values_ref is not None
    member = PoolMemberSeries(
        ref_object_type=ref.object_type,
        ref_object_id=ref.object_id,
        ref_content_hash=ref.content_hash,
        ref_namespace=ref.namespace,
        ref_schema_version=ref.schema_version,
        values=values,
        data_version=execution.data_version,
        split_id=execution.split_id,
        execution_id=execution.execution_id,
        experiment_id=execution.experiment_id,
        callable_fingerprint=execution.callable_fingerprint,
        values_artifact_kind=execution.values_ref.kind,
        values_artifact_id=execution.values_ref.artifact_id,
        values_artifact_hash=execution.values_ref.content_hash,
        values_artifact_namespace=execution.values_ref.namespace,
        values_artifact_schema=execution.values_ref.schema_version,
    )
    return member, [], None


def _bind_pool_members(
    request: EvaluationRequest,
    loaded: Sequence[TypedPoolMember] | Mapping[str, Any] | None,
    *,
    producer: str,
) -> tuple[list[PoolMemberSeries] | None, EvaluationReport | None]:
    """Exact one-to-one bind of ``request.pool_refs`` to typed pool members.

    Mapping[str, Series] self-attestation is rejected (no compatibility path).
    """
    declared = tuple(request.pool_refs)
    if not declared:
        if loaded is None or (hasattr(loaded, "__len__") and len(loaded) == 0):
            return None, None
        return None, _identity_failure(
            request=request,
            factor_ref=request.factor_ref,
            message="load_pool returned members but request.pool_refs is empty",
            code=FailureCode.INVALID_REFERENCE,
            details={"cause_type": "pool_refs_empty_but_loaded_nonempty"},
            producer=producer,
        )
    if loaded is None:
        return None, _identity_failure(
            request=request,
            factor_ref=request.factor_ref,
            message="pool_refs declared but load_pool returned nothing",
            code=FailureCode.INVALID_REFERENCE,
            producer=producer,
        )
    if isinstance(loaded, Mapping):
        return None, _identity_failure(
            request=request,
            factor_ref=request.factor_ref,
            message=(
                "Mapping[str, Series] pool loader is not accepted; "
                "return Sequence[TypedPoolMember]"
            ),
            code=FailureCode.INVALID_REFERENCE,
            details={"cause_type": "mapping_pool_loader_rejected"},
            producer=producer,
        )

    for ref in declared:
        errs = _validate_object_ref(
            ref,
            expected_type="FactorExecutionResult",
            expected_namespace=request.namespace,
        )
        if errs:
            return None, _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="pool_refs identity validation failed",
                code=FailureCode.INVALID_REFERENCE,
                details={"errors": errs, "object_id": ref.object_id},
                producer=producer,
            )
    declared_ids = [r.object_id for r in declared]
    if len(set(declared_ids)) != len(declared_ids):
        return None, _identity_failure(
            request=request,
            factor_ref=request.factor_ref,
            message="pool_refs contain duplicate object_ids",
            code=FailureCode.DUPLICATE_LOGICAL_KEY,
            details={"object_ids": declared_ids},
            producer=producer,
        )

    if not isinstance(loaded, Sequence):
        return None, _identity_failure(
            request=request,
            factor_ref=request.factor_ref,
            message="load_pool must return Sequence[TypedPoolMember]",
            code=FailureCode.INVALID_REFERENCE,
            producer=producer,
        )
    if len(loaded) != len(declared):
        return None, _identity_failure(
            request=request,
            factor_ref=request.factor_ref,
            message="loaded pool size must equal pool_refs size",
            code=FailureCode.INVALID_REFERENCE,
            details={"declared_n": len(declared), "loaded_n": len(loaded)},
            producer=producer,
        )
    seen: set[str] = set()
    by_id: dict[str, TypedPoolMember] = {}
    for item in loaded:
        if not isinstance(item, TypedPoolMember):
            return None, _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="pool members must be TypedPoolMember",
                code=FailureCode.INVALID_REFERENCE,
                details={"cause_type": "invalid_pool_member_type"},
                producer=producer,
            )
        exec_id = item.execution.execution_id
        if exec_id in seen:
            return None, _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="duplicate pool member execution_id",
                code=FailureCode.DUPLICATE_LOGICAL_KEY,
                details={"object_id": exec_id},
                producer=producer,
            )
        seen.add(exec_id)
        by_id[exec_id] = item

    members: list[PoolMemberSeries] = []
    for ref in declared:
        item = by_id.get(ref.object_id)
        if item is None:
            return None, _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="declared pool_ref missing from loaded members",
                code=FailureCode.INVALID_REFERENCE,
                details={"object_id": ref.object_id},
                producer=producer,
            )
        member, member_errs, member_code = _typed_member_to_pool_series(
            item, ref, request=request
        )
        if member is None or member_errs:
            return None, _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="typed pool member failed envelope/lineage validation",
                code=member_code or FailureCode.INVALID_REFERENCE,
                details={"object_id": ref.object_id, "errors": member_errs},
                producer=producer,
            )
        members.append(member)
    extra = sorted(seen - {r.object_id for r in declared})
    if extra:
        return None, _identity_failure(
            request=request,
            factor_ref=request.factor_ref,
            message="loaded pool has members not declared in pool_refs",
            code=FailureCode.INVALID_REFERENCE,
            details={"extra": extra},
            producer=producer,
        )
    return members, None


def _map_hard_fail_code(finding: Finding) -> FailureCode:
    return map_hard_fail_code(finding)


def _map_severity(severity: FindingSeverity) -> Severity:
    return Severity(severity.value)


def _map_section_status(status: str) -> SectionStatus:
    if status == "unavailable":
        return SectionStatus.PARTIAL
    return SectionStatus(status)


def _phase01_section_name(name: str) -> str:
    if name == "causality":
        return "formula_safety"
    if name in EVALUATION_SECTIONS:
        return name
    return "data_quality"


def _spec_snapshot(spec: FactorSpec, *, formula_fingerprint: str = "") -> SpecSnapshot:
    formula = spec.formula
    return SpecSnapshot(
        factor_id=spec.factor_id,
        formula_kind=formula.kind.value
        if hasattr(formula.kind, "value")
        else str(formula.kind),
        function_module=(
            None if formula.function_ref is None else formula.function_ref.module
        ),
        function_name=(
            None if formula.function_ref is None else formula.function_ref.name
        ),
        expression=None if formula.expression is None else dict(formula.expression),
        params=dict(formula.params),
        required_fields=tuple(spec.required_fields),
        window=spec.window,
        lag=spec.lag,
        warmup=spec.warmup,
        missing_policy=spec.missing_policy,
        output_dtype=spec.output_dtype,
        expected_direction=spec.expected_direction,
        content_hash=spec.content_hash,
        formula_fingerprint=formula_fingerprint,
    )


def _object_refs_equal(left: ObjectRef, right: ObjectRef) -> bool:
    return (
        left.object_type == right.object_type
        and left.object_id == right.object_id
        and left.content_hash == right.content_hash
        and left.namespace == right.namespace
        and left.schema_version == right.schema_version
    )


def _identity_failure(
    *,
    request: EvaluationRequest,
    factor_ref: ObjectRef,
    message: str,
    code: FailureCode,
    details: Mapping[str, Any] | None = None,
    producer: str,
) -> EvaluationReport:
    return EvaluationReport(
        report_id=f"eval-{request.request_id}",
        request_id=request.request_id,
        brief_ref=request.brief_ref,
        factor_ref=factor_ref,
        execution_ref=request.execution_ref,
        protocol_id=request.protocol_id,
        data_version=request.data_version,
        split_id=request.split_id,
        pool_refs=tuple(request.pool_refs),
        sections=tuple(
            EvaluationSection(name=name, status=SectionStatus.FAILED)
            for name in request.include_sections
        ),
        provenance=Provenance(
            producer=producer,
            data_version=request.data_version,
            code_version=ENGINE_VERSION,
            experiment_version=request.protocol_id,
            namespace=request.namespace,
            input_refs=(request.brief_ref, request.factor_ref),
        ),
        engine_version=ENGINE_VERSION,
        failure=FailureDetail(
            code=code,
            message=message,
            severity=Severity.HARD_FAIL,
            details=dict(details or {}),
        ),
    )


def _validate_object_ref(
    ref: ObjectRef,
    *,
    expected_type: str,
    expected_id: str | None = None,
    expected_hash: str | None = None,
    expected_namespace: str | None = None,
    expected_schema: str | None = SCHEMA_VERSION,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(ref, ObjectRef):
        return ["ref is not an ObjectRef"]
    if not ref.content_hash:
        errors.append("content_hash must be non-empty")
    if ref.object_type != expected_type:
        errors.append(
            f"object_type expected {expected_type!r}, got {ref.object_type!r}"
        )
    if expected_id is not None and ref.object_id != expected_id:
        errors.append(f"object_id expected {expected_id!r}, got {ref.object_id!r}")
    if expected_hash is not None:
        if not expected_hash:
            errors.append("expected_hash must be non-empty")
        elif ref.content_hash != expected_hash:
            errors.append("content_hash mismatch against resolved object")
    if expected_namespace is not None and ref.namespace != expected_namespace:
        errors.append(
            f"namespace expected {expected_namespace!r}, got {ref.namespace!r}"
        )
    if expected_schema is not None and ref.schema_version != expected_schema:
        errors.append(
            f"schema_version expected {expected_schema!r}, got {ref.schema_version!r}"
        )
    return errors


def _validate_artifact_ref(
    ref: ArtifactRef,
    *,
    expected_kind: str,
    expected_id: str | None = None,
    expected_namespace: str | None = None,
    expected_schema: str | None = SCHEMA_VERSION,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(ref, ArtifactRef):
        return ["ref is not an ArtifactRef"]
    if not ref.content_hash:
        errors.append("content_hash must be non-empty")
    if ref.kind != expected_kind:
        errors.append(f"kind expected {expected_kind!r}, got {ref.kind!r}")
    if expected_id is not None and ref.artifact_id != expected_id:
        errors.append(f"artifact_id expected {expected_id!r}, got {ref.artifact_id!r}")
    if expected_namespace is not None and ref.namespace != expected_namespace:
        errors.append(
            f"namespace expected {expected_namespace!r}, got {ref.namespace!r}"
        )
    if expected_schema is not None and ref.schema_version != expected_schema:
        errors.append(
            f"schema_version expected {expected_schema!r}, got {ref.schema_version!r}"
        )
    return errors


def _validate_protocol_against_brief_spec(
    protocol: ProtocolSnapshot,
    brief: ResearchBrief,
    spec: FactorSpec,
) -> list[str]:
    errors: list[str] = []
    if protocol.horizon_bars != brief.horizon_bars:
        errors.append("horizon_bars mismatch")
    if protocol.rebalance != brief.rebalance:
        errors.append("rebalance mismatch")
    if brief.trading.rebalance != brief.rebalance:
        errors.append("brief.rebalance != brief.trading.rebalance")
    if protocol.rebalance != brief.trading.rebalance:
        errors.append("protocol.rebalance != brief.trading.rebalance")
    if protocol.timezone != brief.timezone:
        errors.append("timezone mismatch")
    if protocol.symbol_level != brief.symbol_level:
        errors.append("symbol_level mismatch")
    if protocol.datetime_level != brief.datetime_level:
        errors.append("datetime_level mismatch")
    if float(protocol.commission) != float(brief.cost.commission):
        errors.append("commission mismatch")
    if float(protocol.slippage) != float(brief.cost.slippage):
        errors.append("slippage mismatch")
    if int(protocol.random_seed) != int(brief.robustness.random_seed):
        errors.append("random_seed mismatch")
    if int(protocol.multiple_testing_budget) != int(brief.multiple_testing_budget):
        errors.append("multiple_testing_budget mismatch")
    if protocol.direction != spec.expected_direction:
        errors.append("direction != expected_direction")
    # trade_at / return_mode: Brief has no authoritative fields for these.
    # Protocol owns them; do not invent Brief counterparts or silent defaults here.
    if bool(protocol.allow_short) != bool(brief.trading.allow_short):
        errors.append("allow_short mismatch vs brief.trading")
    if int(protocol.signal_lag) != int(brief.trading.execution_delay_bars):
        errors.append("signal_lag != brief.trading.execution_delay_bars")
    if tuple(protocol.universe) != tuple(brief.universe):
        errors.append("universe must exactly equal brief.universe")
    if tuple(protocol.regimes) != tuple(brief.robustness.regime_slices):
        errors.append("regimes != brief.robustness.regime_slices")
    if tuple(protocol.time_subsamples) != tuple(brief.robustness.time_subsamples):
        errors.append("time_subsamples != brief.robustness.time_subsamples")
    brief_nb = {
        str(k): tuple(v) for k, v in dict(brief.robustness.parameter_neighborhood).items()
    }
    proto_nb = {str(k): tuple(v) for k, v in dict(protocol.parameter_neighborhood).items()}
    if proto_nb != brief_nb:
        errors.append("parameter_neighborhood mismatch vs brief.robustness")
    # Acceptance thresholds mapped into protocol.thresholds when present.
    if brief.acceptance.min_coverage is not None:
        if protocol.thresholds.get("min_coverage") != brief.acceptance.min_coverage:
            errors.append("thresholds.min_coverage mismatch")
    if brief.acceptance.min_rank_ic_ir is not None:
        if protocol.thresholds.get("min_rank_ic_ir") != brief.acceptance.min_rank_ic_ir:
            errors.append("thresholds.min_rank_ic_ir mismatch")
    if brief.acceptance.max_turnover is not None:
        if protocol.thresholds.get("max_turnover") != brief.acceptance.max_turnover:
            errors.append("thresholds.max_turnover mismatch")
    missing = [f for f in protocol.required_fields if f not in brief.allowed_fields]
    if missing:
        errors.append(f"required_fields outside allowed_fields: {missing}")
    spec_missing = [f for f in spec.required_fields if f not in protocol.required_fields]
    if spec_missing:
        errors.append(f"spec.required_fields not ⊆ protocol.required_fields: {spec_missing}")
    return errors


def map_analyze_result_to_report(
    result: AnalyzeResult,
    *,
    request: EvaluationRequest,
    factor_ref: ObjectRef,
    provenance: Provenance,
    persist_artifact: PersistArtifact | None = None,
) -> EvaluationReport:
    """Map analyze-native AnalyzeResult into a Phase 01 EvaluationReport."""
    report_id = f"eval-{request.request_id}"
    checks_by_name: dict[str, list[RuleCheck]] = {name: [] for name in EVALUATION_SECTIONS}
    facts_by_name: dict[str, list[MetricFact]] = {name: [] for name in EVALUATION_SECTIONS}
    mapping_loss: list[str] = []
    persisted: list[str] = []

    # Persist native material losslessly; only attach fully valid ArtifactRefs.
    native_extra = result.to_public_dict()
    native_extra["protocol_content_hash"] = protocol_content_hash(result.protocol)
    persisted_ref: ArtifactRef | None = None
    attachable_ref: ArtifactRef | None = None
    if persist_artifact is not None:
        try:
            persisted_ref = persist_artifact(
                f"analyze-native/{request.request_id}",
                native_extra,
            )
        except Exception as exc:  # noqa: BLE001
            mapping_loss.append(f"persist_artifact_failed:{type(exc).__name__}")
            persisted_ref = None
        if persisted_ref is None and "persist_artifact_failed" not in str(mapping_loss):
            mapping_loss.append("persist_artifact_returned_none")
        elif persisted_ref is not None:
            expected_hash = content_hash(native_extra)
            valid = True
            if not isinstance(persisted_ref, ArtifactRef):
                mapping_loss.append("persist_artifact_invalid_type")
                valid = False
            else:
                if persisted_ref.kind != "analyze_native":
                    mapping_loss.append("persist_artifact_kind_mismatch")
                    valid = False
                if persisted_ref.namespace != request.namespace:
                    mapping_loss.append("persist_artifact_namespace_mismatch")
                    valid = False
                if persisted_ref.schema_version != SCHEMA_VERSION:
                    mapping_loss.append("persist_artifact_schema_mismatch")
                    valid = False
                if not persisted_ref.content_hash:
                    mapping_loss.append("persist_artifact_content_hash_missing")
                    valid = False
                elif persisted_ref.content_hash != expected_hash:
                    mapping_loss.append("persist_artifact_content_hash_mismatch")
                    valid = False
            if valid:
                attachable_ref = persisted_ref
                persisted.append(persisted_ref.uri or persisted_ref.artifact_id)
            else:
                persisted_ref = None
    else:
        mapping_loss.append("native_result_not_persisted")

    for section in result.sections:
        target = _phase01_section_name(section.name)
        for finding in section.findings:
            # Evidence hash from Phase01-visible RuleCheck fields only.
            visible = {
                "name": finding.name,
                "passed": finding.passed,
                "severity": finding.severity.value,
                "message": finding.message,
                "code": (
                    _map_hard_fail_code(finding).value
                    if (not finding.passed)
                    and finding.severity is FindingSeverity.HARD_FAIL
                    else None
                ),
            }
            evidence = EvidenceRef(
                evidence_id=f"{finding.name}:{content_hash(visible)[:12]}",
                source_report_id=report_id,
                section=target,
                namespace=request.namespace,
                content_hash=content_hash(visible),
            )
            if finding.details:
                # details not in Phase01 RuleCheck; either persisted above or loss.
                if persist_artifact is None:
                    mapping_loss.append(f"finding_details_omitted:{finding.name}")
            code = None
            if (not finding.passed) and finding.severity is FindingSeverity.HARD_FAIL:
                code = _map_hard_fail_code(finding)
            checks_by_name[target].append(
                RuleCheck(
                    name=finding.name,
                    passed=finding.passed,
                    severity=_map_severity(finding.severity),
                    code=code,
                    message=finding.message,
                    evidence=evidence,
                )
            )
        for metric in section.metrics:
            visible_m = {
                "name": metric.name,
                "value": metric.value,
                "unit": metric.unit,
                "sample_range": metric.sample_range,
                "unavailable_reason": metric.unavailable_reason,
                "engine_version": ENGINE_VERSION,
                "data_version": request.data_version,
            }
            evidence = EvidenceRef(
                evidence_id=f"metric:{metric.name}:{content_hash(visible_m)[:12]}",
                source_report_id=report_id,
                section=target,
                namespace=request.namespace,
                content_hash=content_hash(visible_m),
            )
            facts_by_name[target].append(
                MetricFact(
                    name=metric.name,
                    value=metric.value,
                    unit=metric.unit,
                    sample_range=metric.sample_range,
                    engine_version=ENGINE_VERSION,
                    data_version=request.data_version,
                    evidence=evidence,
                    unavailable_reason=metric.unavailable_reason,
                )
            )

    if mapping_loss:
        loss_payload = {
            "mapping_loss": sorted(set(mapping_loss)),
            "persisted": persisted,
            "protocol_content_hash": protocol_content_hash(result.protocol),
        }
        loss_evidence = EvidenceRef(
            evidence_id=f"mapping-loss:{content_hash(loss_payload)[:12]}",
            source_report_id=report_id,
            section="data_quality",
            namespace=request.namespace,
            content_hash=content_hash(loss_payload),
            artifact=attachable_ref,  # only fully valid refs; never attach invalid
        )
        loss_check = RuleCheck(
            name="ADAPTER_MAPPING_LOSS",
            passed=False,
            severity=Severity.WARNING,
            code=None,
            message="some analyze-native fields are not representable in Phase01 report shapes",
            evidence=loss_evidence,
        )
        checks_by_name["data_quality"].append(loss_check)
    elif attachable_ref is not None:
        # Attach native artifact to a Phase01-visible info check for resolvability.
        attach_payload = {
            "name": "ADAPTER_NATIVE_ARTIFACT",
            "artifact_id": attachable_ref.artifact_id,
            "content_hash": attachable_ref.content_hash,
            "protocol_content_hash": protocol_content_hash(result.protocol),
        }
        checks_by_name["data_quality"].append(
            RuleCheck(
                name="ADAPTER_NATIVE_ARTIFACT",
                passed=True,
                severity=Severity.INFO,
                code=None,
                message="full AnalyzeResult persisted for lossless reconstruction",
                evidence=EvidenceRef(
                    evidence_id=f"native-artifact:{content_hash(attach_payload)[:12]}",
                    source_report_id=report_id,
                    section="data_quality",
                    namespace=request.namespace,
                    content_hash=content_hash(attach_payload),
                    artifact=attachable_ref,
                ),
            )
        )

    status_by_target: dict[str, SectionStatus] = dict.fromkeys(
        EVALUATION_SECTIONS, SectionStatus.NOT_RUN
    )
    for section in result.sections:
        target = _phase01_section_name(section.name)
        mapped = _map_section_status(section.status.value)
        current = status_by_target[target]
        rank = {
            SectionStatus.FAILED: 3,
            SectionStatus.PARTIAL: 2,
            SectionStatus.COMPLETE: 1,
            SectionStatus.NOT_RUN: 0,
        }
        if rank[mapped] >= rank[current]:
            status_by_target[target] = mapped

    include = set(request.include_sections)
    built: list[EvaluationSection] = []
    for name in EVALUATION_SECTIONS:
        if name not in include:
            continue
        built.append(
            EvaluationSection(
                name=name,
                status=status_by_target[name],
                facts=tuple(sorted(facts_by_name[name], key=lambda item: item.name)),
                checks=tuple(sorted(checks_by_name[name], key=lambda item: item.name)),
            )
        )

    failure = None
    if result.hard_failed:
        hard = [
            f
            for f in result.findings
            if (not f.passed) and f.severity is FindingSeverity.HARD_FAIL
        ]
        # Skipped cascade findings must not mask the root hard failure.
        root = [
            f
            for f in hard
            if not f.name.endswith("_SKIPPED")
            and not dict(f.details).get("root_hard_failed")
        ]
        # Explicit phase priority rather than incidental alphabetical order.
        phase_rank = {
            "INPUT_": 0,
            "SPEC_": 1,
            "CAUSALITY_": 2,
            "ALIGNMENT_": 3,
            "IDENTITY_": 0,
            "PROTOCOL_": 0,
            "EVALUATION_": 4,
            "ROBUSTNESS_": 5,
            "BACKTEST_": 6,
            "POOL_": 7,
        }

        def _root_key(item: Finding) -> tuple[int, str]:
            rank = 99
            for prefix, value in phase_rank.items():
                if item.name.startswith(prefix):
                    rank = min(rank, value)
            return (rank, item.name)

        chosen = sorted(root or hard, key=_root_key)
        top = chosen[0] if chosen else None
        failure = FailureDetail(
            code=_map_hard_fail_code(top) if top is not None else FailureCode.UNKNOWN,
            message=top.message if top is not None else "hard failed",
            severity=Severity.HARD_FAIL,
            details={
                "native_codes": [f.name for f in hard],
                "root_native_codes": [f.name for f in root],
                "operation": result.operation,
                "mapping_loss": sorted(set(mapping_loss)),
                "protocol_content_hash": protocol_content_hash(result.protocol),
            },
        )

    return EvaluationReport(
        report_id=report_id,
        request_id=request.request_id,
        brief_ref=request.brief_ref,
        factor_ref=factor_ref,
        execution_ref=request.execution_ref,
        protocol_id=request.protocol_id,
        data_version=request.data_version,
        split_id=request.split_id,
        pool_refs=tuple(request.pool_refs),
        sections=tuple(built),
        provenance=provenance,
        engine_version=ENGINE_VERSION,
        schema_version=SCHEMA_VERSION,
        failure=failure,
    )


def build_prefix_recompute_capability(
    *,
    factor: FactorSpec,
    execution: FactorExecutionResult | None = None,
):
    """Official Phase02 issuer: compile exact FactorSpec and seal the closure.

    Public signature accepts only ``FactorSpec`` and an optional verified
    ``FactorExecutionResult``. When ``execution`` is provided (evaluate path),
    the compiled fingerprint must exact-match ``execution.callable_fingerprint``.
    Preflight (no execution yet) still uses this exact-spec compile path.
    Arbitrary callables / hash-string self-attestation are not accepted.
    """
    import secrets

    from skills.analyze.causality import _issue_prefix_recompute_capability
    from skills.compute.wrappers import Factor
    from skills.factor_mining.adapters.compute import _apply_lag
    from skills.factor_mining.adapters.formula import compile_formula
    from skills.factor_mining.adapters.panel import (
        ADAPTER_SCHEMA_VERSION,
        normalize_panel,
        restore_series,
    )

    if not isinstance(factor, FactorSpec):
        raise TypeError("factor must be a FactorSpec")
    if execution is not None and not isinstance(execution, FactorExecutionResult):
        raise TypeError("execution must be FactorExecutionResult or None")

    func, fingerprint, _bound = compile_formula(
        factor.formula,
        required_fields=tuple(factor.required_fields),
        adapter_schema_version=ADAPTER_SCHEMA_VERSION,
    )
    if execution is not None:
        expected = callable_fingerprint_from_execution(execution)
        if fingerprint != expected or fingerprint != execution.callable_fingerprint:
            raise ValueError(
                "compiled fingerprint mismatch vs execution.callable_fingerprint"
            )

    def _recompute(df: pd.DataFrame) -> pd.Series:
        normalized = normalize_panel(
            df, required_fields=tuple(factor.required_fields)
        )
        work = normalized.frame.loc[:, list(factor.required_fields)]
        out = Factor(func).calculate(work, dropna=False)
        out = _apply_lag(out, factor.lag)
        return restore_series(out.astype("float64"), normalized)

    seal = secrets.token_hex(32)
    return _issue_prefix_recompute_capability(
        spec_content_hash=factor.content_hash,
        formula_fingerprint=fingerprint,
        recompute=_recompute,
        seal=seal,
    )


class AnalyzeAdapter:
    """Thin AnalyzePort implementation over AnalyzeFacade + injected loaders."""

    def __init__(
        self,
        *,
        facade: AnalyzeFacade,
        resolve_brief: ResolveBrief,
        resolve_factor: ResolveFactor,
        resolve_protocol: ResolveProtocol,
        resolve_execution: ResolveExecution | None = None,
        load_series: LoadSeries | None = None,
        load_panel: LoadPanel,
        load_pool: LoadPool | None = None,
        persist_artifact: PersistArtifact | None = None,
        provenance_producer: str = "analyze_adapter",
    ) -> None:
        self._facade = facade
        self._resolve_brief = resolve_brief
        self._resolve_factor = resolve_factor
        self._resolve_protocol = resolve_protocol
        self._resolve_execution = resolve_execution
        self._load_series = load_series
        self._load_panel = load_panel
        self._load_pool = load_pool
        self._persist_artifact = persist_artifact
        self._producer = provenance_producer

    def _resolve_context(
        self, request: EvaluationRequest
    ) -> tuple[ResearchBrief, FactorSpec, ProtocolSnapshot] | EvaluationReport:
        try:
            brief = self._resolve_brief(request.brief_ref)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="brief resolution failed",
                code=FailureCode.INVALID_REFERENCE,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        if brief is None or not isinstance(brief, ResearchBrief):
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="resolve_brief must return ResearchBrief",
                code=FailureCode.INVALID_REFERENCE,
                details={
                    "got_type": type(brief).__name__ if brief is not None else "NoneType"
                },
                producer=self._producer,
            )
        try:
            factor = self._resolve_factor(request.factor_ref)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="factor resolution failed",
                code=FailureCode.INVALID_REFERENCE,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        if factor is None or not isinstance(factor, FactorSpec):
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="resolve_factor must return FactorSpec",
                code=FailureCode.INVALID_REFERENCE,
                details={
                    "got_type": type(factor).__name__ if factor is not None else "NoneType"
                },
                producer=self._producer,
            )
        try:
            brief.validate_hash()
        except ValueError as exc:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="ResearchBrief content_hash mismatch",
                code=FailureCode.HASH_MISMATCH,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        try:
            factor.validate_hash()
        except ValueError as exc:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="FactorSpec content_hash mismatch",
                code=FailureCode.HASH_MISMATCH,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        if request.brief_ref.schema_version != SCHEMA_VERSION:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="brief_ref schema_version mismatch",
                code=FailureCode.SCHEMA_MISMATCH,
                producer=self._producer,
            )
        if request.factor_ref.schema_version != SCHEMA_VERSION:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="factor_ref schema_version mismatch",
                code=FailureCode.SCHEMA_MISMATCH,
                producer=self._producer,
            )
        brief_errs = _validate_object_ref(
            request.brief_ref,
            expected_type="ResearchBrief",
            expected_id=brief.brief_id,
            expected_hash=brief.content_hash,
            expected_namespace=request.namespace,
        )
        factor_errs = _validate_object_ref(
            request.factor_ref,
            expected_type="FactorSpec",
            expected_id=factor.factor_id,
            expected_hash=factor.content_hash,
            expected_namespace=request.namespace,
        )
        if brief_errs or factor_errs:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="resolver identity validation failed",
                code=FailureCode.INVALID_REFERENCE,
                details={"brief": brief_errs, "factor": factor_errs},
                producer=self._producer,
            )
        if not _object_refs_equal(factor.brief_ref, request.brief_ref):
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="FactorSpec.brief_ref must equal request.brief_ref in all fields",
                code=FailureCode.SCHEMA_MISMATCH,
                producer=self._producer,
            )
        if request.data_version != brief.data_version:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="request.data_version must equal brief.data_version",
                code=FailureCode.HASH_MISMATCH,
                producer=self._producer,
            )
        if request.data_version != factor.provenance.data_version:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="request.data_version must equal factor provenance data_version",
                code=FailureCode.HASH_MISMATCH,
                producer=self._producer,
            )
        split_ids = {
            brief.train.split_id,
            brief.validation.split_id,
            brief.sealed.split_id,
        }
        if request.split_id not in split_ids:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="split_id must name one of the Brief split IDs",
                code=FailureCode.INVALID_PARAMETERS,
                details={"allowed": sorted(split_ids)},
                producer=self._producer,
            )
        try:
            protocol = self._resolve_protocol(request.protocol_id)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="protocol resolution failed",
                code=FailureCode.INVALID_REFERENCE,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        if not isinstance(protocol, ProtocolSnapshot):
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="resolve_protocol must return ProtocolSnapshot",
                code=FailureCode.INVALID_PARAMETERS,
                producer=self._producer,
            )
        proto_errs = _validate_protocol_against_brief_spec(protocol, brief, factor)
        if proto_errs:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="protocol inconsistent with brief/spec",
                code=FailureCode.INVALID_PARAMETERS,
                details={"errors": proto_errs},
                producer=self._producer,
            )
        return brief, factor, protocol

    def _validate_execution(
        self,
        request: EvaluationRequest,
        execution: FactorExecutionResult,
        factor: FactorSpec,
        protocol: ProtocolSnapshot,
    ) -> EvaluationReport | None:
        if request.execution_ref is None:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution_ref required",
                code=FailureCode.INVALID_REFERENCE,
                producer=self._producer,
            )
        if request.execution_ref.object_type != "FactorExecutionResult":
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution_ref.object_type must be FactorExecutionResult",
                code=FailureCode.INVALID_REFERENCE,
                producer=self._producer,
            )
        if request.execution_ref.schema_version != SCHEMA_VERSION:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution_ref schema_version mismatch",
                code=FailureCode.SCHEMA_MISMATCH,
                producer=self._producer,
            )
        if request.execution_ref.namespace != request.namespace:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution_ref namespace mismatch",
                code=FailureCode.INVALID_REFERENCE,
                producer=self._producer,
            )
        if not request.execution_ref.content_hash:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution_ref.content_hash must be non-empty",
                code=FailureCode.HASH_MISMATCH,
                producer=self._producer,
            )
        if request.execution_ref.object_id != execution.execution_id:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution_ref.object_id must equal execution.execution_id",
                code=FailureCode.INVALID_REFERENCE,
                details={
                    "expected": execution.execution_id,
                    "got": request.execution_ref.object_id,
                },
                producer=self._producer,
            )
        envelope = execution_envelope_identity(execution)
        if request.execution_ref.content_hash != envelope:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution_ref.content_hash does not match execution envelope identity",
                code=FailureCode.HASH_MISMATCH,
                details={
                    "expected": envelope,
                    "got": request.execution_ref.content_hash,
                    "note": "fingerprint is envelope identity, not formula-only",
                },
                producer=self._producer,
            )
        if execution.fingerprint != envelope:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution.fingerprint does not match recomputed envelope identity",
                code=FailureCode.HASH_MISMATCH,
                producer=self._producer,
            )
        if not execution.callable_fingerprint:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution.callable_fingerprint must be non-empty",
                code=FailureCode.HASH_MISMATCH,
                producer=self._producer,
            )
        if execution.failure is not None:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution result is not successful",
                code=FailureCode.INVALID_REFERENCE,
                details={"execution_failure": execution.failure.code.value},
                producer=self._producer,
            )
        if execution.values_ref is None or execution.valid_mask_ref is None:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="successful execution requires values and mask refs",
                code=FailureCode.INVALID_REFERENCE,
                producer=self._producer,
            )
        values_errs = _validate_artifact_ref(
            execution.values_ref,
            expected_kind="factor_values",
            expected_id=f"{execution.execution_id}:values",
            expected_namespace=request.namespace,
        )
        mask_errs = _validate_artifact_ref(
            execution.valid_mask_ref,
            expected_kind="valid_mask",
            expected_id=f"{execution.execution_id}:mask",
            expected_namespace=request.namespace,
        )
        if values_errs or mask_errs:
            code = FailureCode.INVALID_REFERENCE
            joined = " ".join(values_errs + mask_errs)
            if "schema_version" in joined:
                code = FailureCode.SCHEMA_MISMATCH
            elif "content_hash must be non-empty" in joined:
                code = FailureCode.HASH_MISMATCH
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution values/mask artifact refs failed validation",
                code=code,
                details={"values": values_errs, "mask": mask_errs},
                producer=self._producer,
            )
        if not _object_refs_equal(execution.brief_ref, request.brief_ref):
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution.brief_ref must equal request.brief_ref",
                code=FailureCode.INVALID_REFERENCE,
                producer=self._producer,
            )
        # Provenance must include exact request.brief_ref and request.factor_ref.
        prov_errs = _execution_provenance_has_exact_refs(
            execution,
            brief_ref=request.brief_ref,
            factor_ref=request.factor_ref,
        )
        if prov_errs:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution provenance must include exact brief_ref and factor_ref",
                code=FailureCode.INVALID_REFERENCE,
                details={"errors": prov_errs},
                producer=self._producer,
            )
        if execution.data_version != request.data_version:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution.data_version mismatch vs request",
                code=FailureCode.HASH_MISMATCH,
                producer=self._producer,
            )
        if execution.split_id != request.split_id:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution.split_id mismatch vs request",
                code=FailureCode.INVALID_PARAMETERS,
                producer=self._producer,
            )
        if not _object_refs_equal(execution.factor_ref, request.factor_ref):
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution.factor_ref must equal request.factor_ref",
                code=FailureCode.SCHEMA_MISMATCH,
                producer=self._producer,
            )
        if execution.factor_ref.object_id != factor.factor_id or (
            execution.factor_ref.content_hash != factor.content_hash
        ):
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution.factor_ref does not match resolved FactorSpec",
                code=FailureCode.SCHEMA_MISMATCH,
                producer=self._producer,
            )
        if execution.provenance.data_version != request.data_version:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution provenance data_version mismatch",
                code=FailureCode.HASH_MISMATCH,
                producer=self._producer,
            )
        if execution.provenance.namespace != request.namespace:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution provenance namespace mismatch",
                code=FailureCode.INVALID_REFERENCE,
                producer=self._producer,
            )
        schema = execution.index_schema
        if schema.symbol_level != protocol.symbol_level:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution index_schema.symbol_level mismatch vs protocol",
                code=FailureCode.INVALID_INDEX_SCHEMA,
                producer=self._producer,
            )
        if schema.datetime_level != protocol.datetime_level:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution index_schema.datetime_level mismatch vs protocol",
                code=FailureCode.INVALID_INDEX_SCHEMA,
                producer=self._producer,
            )
        if schema.timezone != protocol.timezone:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution index_schema.timezone mismatch vs protocol",
                code=FailureCode.TIME_CONVERSION_FAILED,
                producer=self._producer,
            )
        return None

    def preflight(self, request: EvaluationRequest) -> EvaluationReport:
        resolved = self._resolve_context(request)
        if isinstance(resolved, EvaluationReport):
            return resolved
        brief, factor, protocol = resolved
        try:
            panel = self._load_panel(request)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="panel load failed",
                code=FailureCode.INVALID_REFERENCE,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        try:
            capability = build_prefix_recompute_capability(factor=factor)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="official prefix capability compile failed",
                code=FailureCode.UNSUPPORTED_FORMULA,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )

        def _factory(spec_snap: SpecSnapshot):
            return build_prefix_recompute_capability(factor=factor)

        try:
            native = self._facade.preflight(
                panel=panel,
                spec=_spec_snapshot(
                    factor, formula_fingerprint=capability.formula_fingerprint
                ),
                protocol=protocol,
                allowed_fields=tuple(brief.allowed_fields),
                prefix_recompute=_factory,
            )
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="preflight facade failed",
                code=FailureCode.FACTOR_RUNTIME_FAILED,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        return map_analyze_result_to_report(
            native,
            request=request,
            factor_ref=request.factor_ref,
            provenance=Provenance(
                producer=self._producer,
                data_version=request.data_version,
                code_version=ENGINE_VERSION,
                experiment_version=request.protocol_id,
                namespace=request.namespace,
                input_refs=(request.brief_ref, request.factor_ref),
                created_at="",
            ),
            persist_artifact=self._persist_artifact,
        )

    def evaluate(self, request: EvaluationRequest) -> EvaluationReport:
        if request.execution_ref is None:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="evaluate requires execution_ref",
                code=FailureCode.INVALID_REFERENCE,
                producer=self._producer,
            )
        if self._resolve_execution is None or self._load_series is None:
            raise TypeError("evaluate requires resolve_execution and load_series")
        resolved = self._resolve_context(request)
        if isinstance(resolved, EvaluationReport):
            return resolved
        brief, factor, protocol = resolved
        try:
            execution = self._resolve_execution(request.execution_ref)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution resolution failed",
                code=FailureCode.INVALID_REFERENCE,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        if execution is None or not isinstance(execution, FactorExecutionResult):
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="resolve_execution must return FactorExecutionResult",
                code=FailureCode.INVALID_REFERENCE,
                details={
                    "got_type": (
                        type(execution).__name__ if execution is not None else "NoneType"
                    )
                },
                producer=self._producer,
            )
        exec_fail = self._validate_execution(request, execution, factor, protocol)
        if exec_fail is not None:
            return exec_fail
        try:
            panel = self._load_panel(request)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="panel load failed",
                code=FailureCode.INVALID_REFERENCE,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        try:
            values = self._load_series(execution.values_ref)  # type: ignore[arg-type]
            mask = self._load_series(execution.valid_mask_ref)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            code = FailureCode.INVALID_REFERENCE
            if hasattr(exc, "code") and isinstance(exc.code, FailureCode):
                code = exc.code
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="series load failed",
                code=code,
                details={"cause_type": type(exc).__name__, "cause": str(exc)},
                producer=self._producer,
            )
        from skills.factor_mining.adapters.series_codec import series_content_hash

        try:
            values_hash = series_content_hash(values)
            mask_hash = series_content_hash(mask)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="loaded series content hash failed",
                code=FailureCode.HASH_MISMATCH,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        if values_hash != execution.values_content_hash:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="loaded values content hash mismatch vs execution",
                code=FailureCode.HASH_MISMATCH,
                producer=self._producer,
            )
        if mask_hash != execution.valid_mask_content_hash:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="loaded valid_mask content hash mismatch vs execution",
                code=FailureCode.HASH_MISMATCH,
                producer=self._producer,
            )
        formula_fp = callable_fingerprint_from_execution(execution)

        def _factory(spec_snap: SpecSnapshot):
            return build_prefix_recompute_capability(
                factor=factor,
                execution=execution,
            )

        try:
            native = self._facade.evaluate(
                panel=panel,
                spec=_spec_snapshot(factor, formula_fingerprint=formula_fp),
                protocol=protocol,
                values=values,
                valid_mask=mask,
                execution_fingerprint=execution.fingerprint,
                data_version=request.data_version,
                allowed_fields=tuple(brief.allowed_fields),
                prefix_recompute=_factory,
            )
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="evaluate failed",
                code=FailureCode.FACTOR_RUNTIME_FAILED,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        return map_analyze_result_to_report(
            native,
            request=request,
            factor_ref=request.factor_ref,
            provenance=Provenance(
                producer=self._producer,
                data_version=request.data_version,
                code_version=ENGINE_VERSION,
                experiment_version=request.protocol_id,
                namespace=request.namespace,
                input_refs=(request.brief_ref, request.factor_ref, request.execution_ref),
            ),
            persist_artifact=self._persist_artifact,
        )

    def compare_to_pool(self, request: EvaluationRequest) -> EvaluationReport:
        if request.execution_ref is None:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="compare_to_pool requires execution_ref",
                code=FailureCode.INVALID_REFERENCE,
                producer=self._producer,
            )
        if self._resolve_execution is None or self._load_series is None:
            raise TypeError("compare_to_pool requires resolve_execution and load_series")
        resolved = self._resolve_context(request)
        if isinstance(resolved, EvaluationReport):
            return resolved
        _brief, factor, protocol = resolved
        try:
            execution = self._resolve_execution(request.execution_ref)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="execution resolution failed",
                code=FailureCode.INVALID_REFERENCE,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        if execution is None or not isinstance(execution, FactorExecutionResult):
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="resolve_execution must return FactorExecutionResult",
                code=FailureCode.INVALID_REFERENCE,
                details={
                    "got_type": (
                        type(execution).__name__ if execution is not None else "NoneType"
                    )
                },
                producer=self._producer,
            )
        exec_fail = self._validate_execution(request, execution, factor, protocol)
        if exec_fail is not None:
            return exec_fail
        try:
            panel = self._load_panel(request)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="panel load failed",
                code=FailureCode.INVALID_REFERENCE,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        try:
            values = self._load_series(execution.values_ref)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            code = FailureCode.INVALID_REFERENCE
            if hasattr(exc, "code") and isinstance(exc.code, FailureCode):
                code = exc.code
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="series load failed",
                code=code,
                details={"cause_type": type(exc).__name__, "cause": str(exc)},
                producer=self._producer,
            )
        from skills.factor_mining.adapters.series_codec import series_content_hash

        try:
            values_hash = series_content_hash(values)
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="candidate values content hash failed",
                code=FailureCode.HASH_MISMATCH,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        if values_hash != execution.values_content_hash:
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="candidate values content hash mismatch vs execution",
                code=FailureCode.HASH_MISMATCH,
                producer=self._producer,
            )
        try:
            pool_loaded = None if self._load_pool is None else self._load_pool(request)
        except Exception as exc:  # noqa: BLE001
            code = FailureCode.INVALID_REFERENCE
            if hasattr(exc, "code") and isinstance(exc.code, FailureCode):
                code = exc.code
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="pool load failed",
                code=code,
                details={"cause_type": type(exc).__name__, "cause": str(exc)},
                producer=self._producer,
            )
        members, pool_fail = _bind_pool_members(
            request, pool_loaded, producer=self._producer
        )
        if pool_fail is not None:
            return pool_fail
        try:
            native = self._facade.compare_to_pool(
                panel=panel,
                protocol=protocol,
                candidate=values,
                pool=members,
            )
        except Exception as exc:  # noqa: BLE001
            return _identity_failure(
                request=request,
                factor_ref=request.factor_ref,
                message="compare_to_pool facade failed",
                code=FailureCode.FACTOR_RUNTIME_FAILED,
                details={"cause_type": type(exc).__name__},
                producer=self._producer,
            )
        input_refs = (
            request.brief_ref,
            request.factor_ref,
            request.execution_ref,
            *request.pool_refs,
        )
        return map_analyze_result_to_report(
            native,
            request=request,
            factor_ref=request.factor_ref,
            provenance=Provenance(
                producer=self._producer,
                data_version=request.data_version,
                code_version=ENGINE_VERSION,
                experiment_version=request.protocol_id,
                namespace=request.namespace,
                input_refs=input_refs,
            ),
            persist_artifact=self._persist_artifact,
        )


__all__ = [
    "AnalyzeAdapter",
    "ResolveProtocol",
    "build_prefix_recompute_capability",
    "frozen_oos_metric_selectors",
    "map_analyze_result_to_report",
    "oos_report_passes_frozen_thresholds",
    "_map_hard_fail_code",
]
