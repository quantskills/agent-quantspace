"""FreezeManifest construction and Human Gate-1 precondition checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from skills.factor_mining.contracts import (
    ArtifactRef,
    CostConstraints,
    FailureCode,
    FailureDetail,
    FreezeManifest,
    ObjectRef,
    PoolDecisionKind,
    Provenance,
    ResearchBrief,
    to_plain_dict,
)
from skills.factor_mining.isolation import IsolationDenied, assert_refs_authorized
from skills.factor_mining.state import CandidateAggregate, RunAggregate


class FreezeGateError(Exception):
    def __init__(self, failure: FailureDetail) -> None:
        super().__init__(failure.message)
        self.failure = failure


def require_gate1_approval(
    run: RunAggregate,
    *,
    store_get,
    candidate_id: str | None = None,
) -> ArtifactRef:
    """Require a persisted Human Gate-1 approval artifact on the run."""
    ref = run.gate1_approval_ref
    if ref is None:
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_STATE,
                message="Human Gate-1 approval required before freeze",
            )
        )
    payload = store_get(ref)
    if not isinstance(payload, Mapping):
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="Gate-1 approval payload missing",
            )
        )
    if payload.get("approved") is not True:
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_STATE,
                message="Gate-1 approval artifact is not approved=true",
            )
        )
    if payload.get("run_id") != run.run_id:
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="Gate-1 approval run_id mismatch",
            )
        )
    if candidate_id is not None and payload.get("candidate_id") != candidate_id:
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="Gate-1 approval candidate_id mismatch",
                details={
                    "expected": candidate_id,
                    "got": payload.get("candidate_id"),
                },
            )
        )
    return ref


def require_pool_accept(
    *,
    candidate: CandidateAggregate,
    store_get,
    require_accept: bool = True,
) -> Mapping[str, Any]:
    if candidate.pool_decision_ref is None:
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_STATE,
                message="PoolDecision required before freeze",
            )
        )
    raw = store_get(candidate.pool_decision_ref)
    if not isinstance(raw, Mapping):
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="PoolDecision payload missing",
            )
        )
    decision_payload = raw.get("pool_decision", raw.get("body", raw))
    if not isinstance(decision_payload, Mapping):
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="PoolDecision payload invalid",
            )
        )
    decision_kind = str(decision_payload.get("decision", ""))
    if require_accept and decision_kind != PoolDecisionKind.ACCEPT.value:
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_STATE,
                message="PoolDecision must be ACCEPT to freeze",
                details={"decision": decision_kind},
            )
        )
    factor_ref_raw = decision_payload.get("factor_ref")
    if not isinstance(factor_ref_raw, Mapping):
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="PoolDecision factor_ref missing",
            )
        )
    # Exact equality of ObjectRef fields — not hash-only.
    cand_plain = to_plain_dict(candidate.factor_ref)
    if dict(factor_ref_raw) != cand_plain:
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="PoolDecision factor_ref must exact-equal candidate factor_ref",
                details={
                    "expected": cand_plain,
                    "got": dict(factor_ref_raw),
                },
            )
        )
    return decision_payload


def require_complete_refs(candidate: CandidateAggregate) -> None:
    missing: list[str] = []
    if candidate.preflight_ref is None:
        missing.append("preflight_ref")
    if candidate.execution_ref is None:
        missing.append("execution_ref")
    if candidate.evaluation_ref is None:
        missing.append("evaluation_ref")
    if candidate.compare_ref is None:
        missing.append("compare_ref")
    if not candidate.review_refs:
        missing.append("review_refs")
    if candidate.pool_decision_ref is None:
        missing.append("pool_decision_ref")
    if missing:
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_STATE,
                message="complete evaluation/review/pool refs required before freeze",
                details={"missing": tuple(missing)},
            )
        )


def _load_typed_object(
    *,
    ref: ObjectRef,
    expected_type: str,
    store_get_object,
    run: RunAggregate,
    candidate: CandidateAggregate,
) -> Mapping[str, Any]:
    if ref.namespace != run.namespace:
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="freeze evidence namespace mismatch",
                details={"ref": to_plain_dict(ref)},
            )
        )
    if ref.object_type != expected_type:
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.SCHEMA_MISMATCH,
                message=f"expected {expected_type}",
                details={"got": ref.object_type},
            )
        )
    try:
        body = store_get_object(ref)
    except Exception as exc:  # noqa: BLE001
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message=f"missing or unreadable {expected_type}",
                details={"cause": str(exc)},
            )
        ) from exc
    if not isinstance(body, Mapping):
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message=f"{expected_type} body missing",
            )
        )
    # Bind to candidate/run where applicable.
    if "factor_ref" in body:
        if dict(body["factor_ref"]) != to_plain_dict(candidate.factor_ref):
            raise FreezeGateError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message=f"{expected_type} factor_ref not bound to candidate",
                )
            )
    if body.get("run_id") not in (None, run.run_id):
        raise FreezeGateError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message=f"{expected_type} run_id mismatch",
            )
        )
    return body


def validate_freeze_evidence_refs(
    *,
    run: RunAggregate,
    candidate: CandidateAggregate,
    store_get_object,
    store: Any,
) -> None:
    """Load and verify evaluation/review/pool/gate1 type/id/hash/schema/namespace binds."""
    require_complete_refs(candidate)
    assert candidate.evaluation_ref is not None
    assert candidate.pool_decision_ref is not None
    try:
        assert_refs_authorized(
            store,
            namespace=run.namespace,
            refs=[
                candidate.evaluation_ref,
                candidate.pool_decision_ref,
                *candidate.review_refs,
                run.gate1_approval_ref,
            ],
            allow_sealed=False,
        )
    except IsolationDenied as exc:
        raise FreezeGateError(exc.failure) from exc

    _load_typed_object(
        ref=candidate.evaluation_ref,
        expected_type="EvaluationReport",
        store_get_object=store_get_object,
        run=run,
        candidate=candidate,
    )
    for review_ref in candidate.review_refs:
        _load_typed_object(
            ref=review_ref,
            expected_type="ReviewReport",
            store_get_object=store_get_object,
            run=run,
            candidate=candidate,
        )
    _load_typed_object(
        ref=candidate.pool_decision_ref,
        expected_type="PoolDecision",
        store_get_object=store_get_object,
        run=run,
        candidate=candidate,
    )
    require_pool_accept(candidate=candidate, store_get=store_get_object)
    require_gate1_approval(run, store_get=store.get)


def build_freeze_manifest(
    *,
    manifest_id: str,
    run: RunAggregate,
    candidate: CandidateAggregate,
    brief: ResearchBrief,
    approval_ref: ArtifactRef,
    compute_engine_version: str,
    analyze_engine_version: str,
    evaluation_protocol_id: str,
    direction: str,
    params: Mapping[str, Any],
    missing_policy: str,
    adjustment_policy: str,
    outlier_policy: str,
    neutralization_policy: str,
    holding_horizon_bars: int,
    rebalance: str,
    cost: CostConstraints,
    pool_baseline_refs: Sequence[ObjectRef],
    oos_thresholds: Mapping[str, float],
    oos_metric_selectors: Mapping[str, Mapping[str, str]],
    provenance: Provenance,
    split_refs: Mapping[str, str] | None = None,
) -> FreezeManifest:
    """Build a content-addressed FreezeManifest after Gate-1 + pool accept checks."""
    require_complete_refs(candidate)
    assert candidate.preflight_ref is not None
    assert candidate.execution_ref is not None
    assert candidate.evaluation_ref is not None
    assert candidate.compare_ref is not None
    assert candidate.pool_decision_ref is not None
    splits = dict(split_refs or {})
    if not splits:
        splits = {
            "train": brief.train.split_id,
            "validation": brief.validation.split_id,
            "sealed": brief.sealed.split_id,
        }
    # Sealed split id is recorded as an identifier only; values are never loaded here.
    return FreezeManifest(
        manifest_id=manifest_id,
        run_id=run.run_id,
        brief_ref=run.brief_ref,
        factor_ref=candidate.factor_ref,
        universe=tuple(brief.universe),
        data_version=brief.data_version,
        split_refs=splits,
        compute_engine_version=compute_engine_version,
        analyze_engine_version=analyze_engine_version,
        evaluation_protocol_id=evaluation_protocol_id,
        direction=direction,
        params=dict(params),
        missing_policy=missing_policy,
        adjustment_policy=adjustment_policy,
        outlier_policy=outlier_policy,
        neutralization_policy=neutralization_policy,
        holding_horizon_bars=holding_horizon_bars,
        rebalance=rebalance,
        cost=cost,
        pool_baseline_refs=tuple(pool_baseline_refs),
        preflight_ref=candidate.preflight_ref,
        execution_ref=candidate.execution_ref,
        evaluation_ref=candidate.evaluation_ref,
        compare_ref=candidate.compare_ref,
        review_refs=tuple(candidate.review_refs),
        pool_decision_ref=candidate.pool_decision_ref,
        approval_ref=approval_ref,
        oos_thresholds=dict(oos_thresholds),
        oos_metric_selectors={key: dict(value) for key, value in oos_metric_selectors.items()},
        provenance=provenance,
    )


def manifest_input_fingerprint(manifest: FreezeManifest) -> str:
    """Stable fingerprint over frozen inputs (for change-detection tests)."""
    from skills.factor_mining.contracts import content_hash

    payload = to_plain_dict(manifest)
    payload.pop("content_hash", None)
    return content_hash(payload)


__all__ = [
    "FreezeGateError",
    "require_gate1_approval",
    "require_pool_accept",
    "require_complete_refs",
    "validate_freeze_evidence_refs",
    "build_freeze_manifest",
    "manifest_input_fingerprint",
]
