"""Minimal-authorization task views; sealed refs/values fail closed."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from skills.factor_mining.contracts import (
    AgentTaskView,
    ArtifactRef,
    EvidenceRef,
    FailureCode,
    FailureDetail,
    ObjectRef,
    TaskLease,
    content_hash,
    to_plain_dict,
)
from skills.factor_mining.objects import KIND_OBJECT, load_formal_payload
from skills.factor_mining.state import RunAggregate, TaskAggregate

VIS_TRAIN = "train"
VIS_VALIDATION = "validation"
VIS_BRIEF = "brief"
VIS_FACTOR = "factor"
VIS_EVALUATION = "evaluation"
VIS_REVIEW = "review"
VIS_POOL = "pool"
VIS_SEALED = "sealed"

DEFAULT_RESEARCH_VISIBILITY = (
    VIS_TRAIN,
    VIS_VALIDATION,
    VIS_BRIEF,
    VIS_FACTOR,
    VIS_EVALUATION,
    VIS_REVIEW,
    VIS_POOL,
)

# Visibility token → allowed formal object types / artifact kind prefixes.
VISIBILITY_OBJECT_TYPES: dict[str, frozenset[str]] = {
    VIS_BRIEF: frozenset({"ResearchBrief"}),
    VIS_FACTOR: frozenset({"FactorSpec", "FactorExecutionResult"}),
    VIS_EVALUATION: frozenset({"EvaluationReport"}),
    VIS_REVIEW: frozenset({"ReviewReport"}),
    VIS_POOL: frozenset({"PoolDecision"}),
    VIS_TRAIN: frozenset(),
    VIS_VALIDATION: frozenset(),
}


class IsolationDenied(Exception):
    def __init__(self, failure: FailureDetail) -> None:
        super().__init__(failure.message)
        self.failure = failure


def _ref_namespace(ref: ObjectRef | ArtifactRef | EvidenceRef) -> str:
    return str(ref.namespace)


def assert_same_namespace(
    namespace: str, refs: Iterable[ObjectRef | ArtifactRef | EvidenceRef]
) -> None:
    for ref in refs:
        if _ref_namespace(ref) != namespace:
            raise IsolationDenied(
                FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message="cross-namespace reference rejected",
                    details={
                        "expected_namespace": namespace,
                        "got_namespace": _ref_namespace(ref),
                    },
                )
            )


def is_sealed_marker(value: Any) -> bool:
    """Heuristic sealed markers (never sole authority — store meta required)."""
    if value is None:
        return False
    if isinstance(value, dict):
        if value.get("sealed") is True:
            return True
        if str(value.get("visibility", "")).lower() == VIS_SEALED:
            return True
        split_id = value.get("split_id")
        if isinstance(split_id, str) and split_id.lower().startswith("sealed"):
            return True
        kind = str(value.get("kind", "")).lower()
        if "sealed" in kind or kind == "oos_result":
            return True
        object_type = str(value.get("object_type", "")).lower()
        if object_type.startswith("oos") or "sealed" in object_type:
            return True
        body = value.get("body")
        if isinstance(body, Mapping) and is_sealed_marker(body):
            return True
        for nested in value.values():
            if isinstance(nested, (Mapping, list, tuple)):
                if is_sealed_marker(nested):
                    return True
            elif isinstance(nested, (ObjectRef, ArtifactRef, EvidenceRef)):
                if is_sealed_marker(to_plain_dict(nested)):
                    return True
    if isinstance(value, (list, tuple)):
        return any(is_sealed_marker(item) for item in value)
    return getattr(value, "sealed", None) is True


def _envelope_sealed(store: Any, art: ArtifactRef) -> bool:
    envelope_get = getattr(store, "get_envelope", None)
    if not callable(envelope_get):
        raise IsolationDenied(
            FailureDetail(
                code=FailureCode.FORBIDDEN_INPUT,
                message="store cannot verify sealed capability (missing get_envelope)",
            )
        )
    try:
        envelope = envelope_get(art)
    except Exception as exc:  # noqa: BLE001
        raise IsolationDenied(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="artifact envelope unreadable; sealed check fail-closed",
                details={"cause": str(exc), "ref": to_plain_dict(art)},
            )
        ) from exc
    if not isinstance(envelope, Mapping):
        raise IsolationDenied(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="artifact envelope invalid",
            )
        )
    meta = envelope.get("meta")
    if isinstance(meta, Mapping) and meta.get("sealed") is True:
        return True
    payload = envelope.get("payload")
    return is_sealed_marker(payload) or is_sealed_marker(envelope)


def _verify_artifact(store: Any, ref: ArtifactRef) -> None:
    try:
        store.get(ref)
    except Exception as exc:  # noqa: BLE001
        raise IsolationDenied(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="artifact ref failed existence/hash verification",
                details={"ref": to_plain_dict(ref), "cause": str(exc)},
            )
        ) from exc


def _verify_object(store: Any, ref: ObjectRef) -> Mapping[str, Any]:
    try:
        return load_formal_payload(store, ref, allow_staging=False)
    except Exception as exc:  # noqa: BLE001
        failure = getattr(exc, "failure", None)
        if isinstance(failure, FailureDetail):
            raise IsolationDenied(failure) from exc
        raise IsolationDenied(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="object ref failed existence/hash verification",
                details={"ref": to_plain_dict(ref), "cause": str(exc)},
            )
        ) from exc


def is_research_brief_sealed_split_window(value: Mapping[str, Any]) -> bool:
    """Narrow schema-aware exception for ResearchBrief.sealed SplitWindow only.

    A SplitWindow description records the sealed OOS window id; it is not itself
    a sealed research artifact payload.
    """
    if not isinstance(value, Mapping):
        return False
    required = {"split_id", "start", "end", "sealed"}
    if not required.issubset(set(value)):
        return False
    # Reject unexpected payload keys beyond SplitWindow schema (+ optional hash/schema).
    allowed = required | {"schema_version", "content_hash"}
    if set(value) - allowed:
        return False
    if value.get("sealed") is not True:
        return False
    split_id = value.get("split_id")
    return isinstance(split_id, str) and split_id.lower().startswith("sealed")


def _object_sealed(store: Any, ref: ObjectRef, body: Mapping[str, Any]) -> bool:
    """Sealed capability for formal objects — envelope meta is authoritative.

    ResearchBrief's sealed SplitWindow field is schema metadata, not a sealed
    artifact. Any other object with sealed meta, top-level sealed=True, or
    sealed split_id is sealed.
    """
    peek = getattr(store, "get_envelope_by_identity", None)
    if not callable(peek):
        raise IsolationDenied(
            FailureDetail(
                code=FailureCode.FORBIDDEN_INPUT,
                message="store cannot verify object sealed meta; fail closed",
            )
        )
    try:
        envelope = peek(
            namespace=ref.namespace,
            kind=KIND_OBJECT,
            artifact_id=f"{ref.object_type}-{ref.object_id}",
        )
    except Exception as exc:  # noqa: BLE001
        raise IsolationDenied(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="object envelope unreadable; sealed check fail-closed",
                details={"cause": str(exc)},
            )
        ) from exc
    meta = envelope.get("meta") if isinstance(envelope, Mapping) else None
    if isinstance(meta, Mapping) and meta.get("sealed") is True:
        return True
    if ref.object_type == "ResearchBrief":
        # Brief artifact itself is not sealed; nested SplitWindow checked in walk
        # via the schema-aware exception.
        return False
    if body.get("sealed") is True:
        return True
    split_id = body.get("split_id")
    if isinstance(split_id, str) and split_id.lower().startswith("sealed"):
        return True
    # Nested sealed markers inside non-Brief bodies are also sealed.
    return bool(is_sealed_marker(body))


def assert_ref_authorized(
    store: Any,
    *,
    namespace: str,
    ref: ObjectRef | ArtifactRef | EvidenceRef,
    allow_sealed: bool,
    visibility: Sequence[str] | None = None,
) -> None:
    """Fail-closed recursive authorization for one ref."""
    assert_same_namespace(namespace, [ref])
    vis = set(visibility or ())

    if isinstance(ref, ArtifactRef):
        _verify_artifact(store, ref)
        sealed = _envelope_sealed(store, ref)
        if sealed and not allow_sealed:
            raise IsolationDenied(
                FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="sealed artifact not authorized",
                    details={"ref": to_plain_dict(ref)},
                )
            )
        return

    if isinstance(ref, EvidenceRef):
        # Evidence always requires resolving nested artifact when present.
        if ref.artifact is not None:
            assert_ref_authorized(
                store,
                namespace=namespace,
                ref=ref.artifact,
                allow_sealed=allow_sealed,
                visibility=visibility,
            )
            if _envelope_sealed(store, ref.artifact) and not allow_sealed:
                raise IsolationDenied(
                    FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="sealed evidence artifact not authorized",
                        details={"ref": to_plain_dict(ref)},
                    )
                )
        if is_sealed_marker(to_plain_dict(ref)) and not allow_sealed:
            raise IsolationDenied(
                FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="sealed evidence marker not authorized",
                    details={"ref": to_plain_dict(ref)},
                )
            )
        return

    if isinstance(ref, ObjectRef):
        body = _verify_object(store, ref)
        if visibility is not None:
            allowed_types: set[str] = set()
            for token in vis:
                allowed_types |= set(VISIBILITY_OBJECT_TYPES.get(token, frozenset()))
            if VIS_SEALED not in vis and ref.object_type not in allowed_types:
                # train/validation tokens alone don't grant object types
                if not allowed_types or ref.object_type not in allowed_types:
                    raise IsolationDenied(
                        FailureDetail(
                            code=FailureCode.FORBIDDEN_INPUT,
                            message="object type not allowed by visibility",
                            details={
                                "object_type": ref.object_type,
                                "visibility": tuple(vis),
                            },
                        )
                    )
        sealed = _object_sealed(store, ref, body)
        if sealed and not allow_sealed:
            raise IsolationDenied(
                FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="sealed object not authorized",
                    details={"ref": to_plain_dict(ref)},
                )
            )
        # Recurse into nested refs inside body (factor_ref, evaluation_ref, evidence, etc.).
        _walk_nested_refs(
            store,
            namespace=namespace,
            value=body,
            allow_sealed=allow_sealed,
            visibility=visibility,
            skip_root=True,
        )
        return

    raise IsolationDenied(
        FailureDetail(
            code=FailureCode.INVALID_REFERENCE,
            message="unsupported ref type",
        )
    )


def _walk_nested_refs(
    store: Any,
    *,
    namespace: str,
    value: Any,
    allow_sealed: bool,
    visibility: Sequence[str] | None,
    skip_root: bool = False,
) -> None:
    if isinstance(value, ObjectRef):
        assert_ref_authorized(
            store,
            namespace=namespace,
            ref=value,
            allow_sealed=allow_sealed,
            visibility=visibility,
        )
        return
    if isinstance(value, ArtifactRef):
        assert_ref_authorized(
            store,
            namespace=namespace,
            ref=value,
            allow_sealed=allow_sealed,
            visibility=visibility,
        )
        return
    if isinstance(value, EvidenceRef):
        assert_ref_authorized(
            store,
            namespace=namespace,
            ref=value,
            allow_sealed=allow_sealed,
            visibility=visibility,
        )
        return
    if isinstance(value, Mapping):
        # Mapping that looks like a ref.
        if "object_type" in value and "object_id" in value and "content_hash" in value:
            assert_ref_authorized(
                store,
                namespace=namespace,
                ref=ObjectRef(**dict(value)),
                allow_sealed=allow_sealed,
                visibility=visibility,
            )
            return
        if "kind" in value and "artifact_id" in value and "content_hash" in value:
            assert_ref_authorized(
                store,
                namespace=namespace,
                ref=ArtifactRef(**dict(value)),
                allow_sealed=allow_sealed,
                visibility=visibility,
            )
            return
        if "evidence_id" in value and "content_hash" in value:
            art = value.get("artifact")
            evidence = EvidenceRef(
                **{
                    k: v
                    for k, v in dict(value).items()
                    if k != "artifact"
                },
                artifact=(ArtifactRef(**dict(art)) if isinstance(art, Mapping) else art),
            )
            assert_ref_authorized(
                store,
                namespace=namespace,
                ref=evidence,
                allow_sealed=allow_sealed,
                visibility=visibility,
            )
            return
        # Local sealed markers at this mapping (recursive walk covers children).
        # Only ResearchBrief's sealed SplitWindow schema is exempt.
        if not allow_sealed:
            if is_research_brief_sealed_split_window(value):
                return
            if value.get("sealed") is True:
                raise IsolationDenied(
                    FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="nested sealed marker not authorized",
                    )
                )
            split_id = value.get("split_id")
            if isinstance(split_id, str) and split_id.lower().startswith("sealed"):
                raise IsolationDenied(
                    FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="nested sealed split_id not authorized",
                    )
                )
            kind = str(value.get("kind", "")).lower()
            if "sealed" in kind or kind == "oos_result":
                raise IsolationDenied(
                    FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="nested sealed kind not authorized",
                    )
                )
            object_type = str(value.get("object_type", "")).lower()
            if object_type.startswith("oos") or "sealed" in object_type:
                raise IsolationDenied(
                    FailureDetail(
                        code=FailureCode.FORBIDDEN_INPUT,
                        message="nested sealed object_type not authorized",
                    )
                )
        for nested in value.values():
            _walk_nested_refs(
                store,
                namespace=namespace,
                value=nested,
                allow_sealed=allow_sealed,
                visibility=visibility,
            )
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _walk_nested_refs(
                store,
                namespace=namespace,
                value=nested,
                allow_sealed=allow_sealed,
                visibility=visibility,
            )


def assert_refs_authorized(
    store: Any,
    *,
    namespace: str,
    refs: Sequence[ObjectRef | ArtifactRef | EvidenceRef | None],
    allow_sealed: bool = False,
    visibility: Sequence[str] | None = None,
) -> None:
    cleaned = [ref for ref in refs if ref is not None]
    assert_same_namespace(namespace, cleaned)
    for ref in cleaned:
        assert_ref_authorized(
            store,
            namespace=namespace,
            ref=ref,
            allow_sealed=allow_sealed,
            visibility=visibility,
        )


def project_authorized_refs(
    *,
    namespace: str,
    refs: Sequence[ObjectRef | ArtifactRef | EvidenceRef],
    visibility: Sequence[str],
    store: Any | None = None,
) -> tuple[ObjectRef | ArtifactRef | EvidenceRef, ...]:
    if store is None:
        raise IsolationDenied(
            FailureDetail(
                code=FailureCode.FORBIDDEN_INPUT,
                message="authorized projection requires a trusted store",
            )
        )
    allow_sealed = VIS_SEALED in set(visibility)
    assert_refs_authorized(
        store,
        namespace=namespace,
        refs=refs,
        allow_sealed=allow_sealed,
        visibility=visibility,
    )
    return tuple(refs)


def build_task_lease(
    *,
    lease_id: str,
    run: RunAggregate,
    task: TaskAggregate,
    remaining: Mapping[str, int] | None = None,
) -> TaskLease:
    rem = dict(remaining) if remaining is not None else dict(run.budget_remaining)
    return TaskLease(
        lease_id=lease_id,
        run_id=run.run_id,
        task_id=task.task_id,
        role_id=task.role_id,
        candidates_remaining=int(rem.get("candidates", 0)),
        experiments_remaining=int(rem.get("experiments", 0)),
        revisions_remaining=int(rem.get("revisions", 0)),
        debate_rounds_remaining=int(rem.get("debate_rounds", 0)),
    )


def build_agent_task_view(
    *,
    run: RunAggregate,
    task: TaskAggregate,
    goal: str,
    input_refs: Sequence[ObjectRef | ArtifactRef | EvidenceRef],
    expected_output_type: str,
    lease_id: str,
    visibility: Sequence[str] | None = None,
    candidate_ref: ObjectRef | None = None,
    forbidden_actions: Sequence[str] = (),
    must_check: Sequence[str] = (),
    stop_conditions: Sequence[str] = (),
    store: Any | None = None,
) -> AgentTaskView:
    vis = tuple(visibility or DEFAULT_RESEARCH_VISIBILITY)
    if VIS_SEALED in vis:
        raise IsolationDenied(
            FailureDetail(
                code=FailureCode.FORBIDDEN_INPUT,
                message="sealed visibility is not grantable before Phase 06 OOS",
            )
        )
    if store is None:
        raise IsolationDenied(
            FailureDetail(
                code=FailureCode.FORBIDDEN_INPUT,
                message="task view requires trusted store for ref verification",
            )
        )
    check_refs: list[ObjectRef | ArtifactRef | EvidenceRef] = list(input_refs)
    if candidate_ref is not None:
        check_refs.append(candidate_ref)
    authorized = project_authorized_refs(
        namespace=run.namespace,
        refs=tuple(check_refs),
        visibility=vis,
        store=store,
    )
    # candidate_ref already validated; input_refs subset without duplicating candidate
    # when it was only in candidate_ref.
    input_only = tuple(input_refs)
    assert_refs_authorized(
        store,
        namespace=run.namespace,
        refs=input_only,
        allow_sealed=False,
        visibility=vis,
    )
    hashes = {
        f"ref:{idx}": getattr(ref, "content_hash", "") or content_hash(to_plain_dict(ref))
        for idx, ref in enumerate(input_only)
    }
    lease = build_task_lease(lease_id=lease_id, run=run, task=task)
    _ = authorized
    return AgentTaskView(
        task_id=task.task_id,
        run_id=run.run_id,
        parent_task_id=task.parent_task_id,
        role_id=task.role_id,
        goal=goal,
        input_refs=input_only,
        input_hashes=hashes,
        visibility=vis,
        lease=lease,
        attempt=task.attempt,
        debate_round=task.debate_round,
        expected_output_type=expected_output_type,
        candidate_ref=candidate_ref,
        forbidden_actions=tuple(forbidden_actions),
        must_check=tuple(must_check),
        stop_conditions=tuple(stop_conditions),
    )


__all__ = [
    "VIS_TRAIN",
    "VIS_VALIDATION",
    "VIS_BRIEF",
    "VIS_FACTOR",
    "VIS_EVALUATION",
    "VIS_REVIEW",
    "VIS_POOL",
    "VIS_SEALED",
    "DEFAULT_RESEARCH_VISIBILITY",
    "VISIBILITY_OBJECT_TYPES",
    "IsolationDenied",
    "assert_same_namespace",
    "assert_refs_authorized",
    "assert_ref_authorized",
    "is_sealed_marker",
    "is_research_brief_sealed_split_window",
    "project_authorized_refs",
    "build_task_lease",
    "build_agent_task_view",
]
