"""Canonical formal-object persistence and ObjectRef resolution.

ObjectRef.content_hash is the object's own content_hash (Phase 01 contract).
ArtifactRef.content_hash is the store envelope hash. Never mix the two.

Event-gated types (FreezeManifest, FailureKnowledgeEntry): ordinary getters
require a committed controller_event whose outputs exact-bind the staging
ref/hash, then read the immutable staging body. The event is the sole publish
marker — no post-event formal copy.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from skills.factor_mining.contracts import (
    SCHEMA_VERSION,
    ArtifactRef,
    EvaluationReport,
    FactorExecutionResult,
    FactorSpec,
    FailureCode,
    FailureDetail,
    FailureKnowledgeEntry,
    FreezeManifest,
    ObjectRef,
    OOSAuthorization,
    OOSResult,
    PoolDecision,
    ResearchBrief,
    ReviewReport,
    content_hash,
    rebuild_dataclass,
    to_plain_dict,
)
from skills.factor_mining.event_chain import (
    EventChainError,
    load_run_event_payloads,
    verify_event_chain,
)

KIND_OBJECT = "controller_object"
KIND_STAGING = "controller_staging"
KIND_EVENT = "controller_event"

# Types whose ordinary visibility is gated by a committed controller event.
EVENT_GATED_TYPES = frozenset({"FreezeManifest", "FailureKnowledgeEntry"})

# output key in event.outputs that exact-binds the staging ObjectRef
_GATED_REF_OUTPUT_KEYS: dict[str, str] = {
    "FreezeManifest": "manifest_ref",
    "FailureKnowledgeEntry": "failure_knowledge_ref",
}

_TYPE_BUILDERS: dict[str, type] = {
    "ResearchBrief": ResearchBrief,
    "FactorSpec": FactorSpec,
    "EvaluationReport": EvaluationReport,
    "FactorExecutionResult": FactorExecutionResult,
    "ReviewReport": ReviewReport,
    "PoolDecision": PoolDecision,
    "FreezeManifest": FreezeManifest,
    "OOSAuthorization": OOSAuthorization,
    "OOSResult": OOSResult,
    "FailureKnowledgeEntry": FailureKnowledgeEntry,
}


class ObjectStoreError(Exception):
    def __init__(self, failure: FailureDetail) -> None:
        super().__init__(failure.message)
        self.failure = failure


def object_artifact_id(object_type: str, object_id: str) -> str:
    return f"{object_type}-{object_id}"


def formal_payload(
    *,
    object_type: str,
    object_id: str,
    body: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "object_type": object_type,
        "object_id": object_id,
        "body": dict(body),
        "content_hash": str(body.get("content_hash") or ""),
    }


def canonical_object_ref(
    *,
    object_type: str,
    object_id: str,
    content_hash_hex: str,
    namespace: str,
) -> ObjectRef:
    return ObjectRef(
        object_type=object_type,
        object_id=object_id,
        content_hash=content_hash_hex,
        namespace=namespace,
        schema_version=SCHEMA_VERSION,
    )


def _put_if_absent(
    store: Any,
    *,
    namespace: str,
    kind: str,
    artifact_id: str,
    payload: Mapping[str, Any],
    input_refs: tuple = (),
    meta: Mapping[str, Any] | None = None,
) -> Any:
    putter = getattr(store, "put_if_absent", None)
    if not callable(putter):
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.ARTIFACT_PERSIST_FAILED,
                message="store missing put_if_absent",
            )
        )
    return putter(
        namespace=namespace,
        kind=kind,
        artifact_id=artifact_id,
        payload=payload,
        input_refs=input_refs,
        meta=dict(meta or {}),
    )


def put_staging_object(
    store: Any,
    *,
    namespace: str,
    object_type: str,
    object_id: str,
    body: Mapping[str, Any],
    input_refs: tuple = (),
) -> ObjectRef:
    """Write immutable staging artifact; not visible until Frozen event commits."""
    digest = str(body.get("content_hash") or "")
    if len(digest) != 64:
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="object body missing canonical content_hash",
            )
        )
    payload = formal_payload(
        object_type=object_type, object_id=object_id, body=body
    )
    _put_if_absent(
        store,
        namespace=namespace,
        kind=KIND_STAGING,
        artifact_id=object_artifact_id(object_type, object_id),
        payload=payload,
        input_refs=input_refs,
        meta={"staging": True, "sealed": False},
    )
    # Verify staging is readable and hash-stable before callers append the event.
    loaded = load_staging_payload(
        store, namespace=namespace, object_type=object_type, object_id=object_id
    )
    if str(loaded.get("content_hash") or "") != digest:
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="staging verification hash mismatch",
            )
        )
    return canonical_object_ref(
        object_type=object_type,
        object_id=object_id,
        content_hash_hex=digest,
        namespace=namespace,
    )


def put_formal_object(
    store: Any,
    *,
    namespace: str,
    object_type: str,
    object_id: str,
    body: Mapping[str, Any],
    input_refs: tuple = (),
    meta: Mapping[str, Any] | None = None,
    staging: bool = False,
) -> ObjectRef:
    """Persist a non-gated formal object (or staging when staging=True)."""
    digest = str(body.get("content_hash") or "")
    if len(digest) != 64:
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="formal object body missing canonical content_hash",
            )
        )
    if staging or object_type in EVENT_GATED_TYPES:
        return put_staging_object(
            store,
            namespace=namespace,
            object_type=object_type,
            object_id=object_id,
            body=body,
            input_refs=input_refs,
        )
    _put_if_absent(
        store,
        namespace=namespace,
        kind=KIND_OBJECT,
        artifact_id=object_artifact_id(object_type, object_id),
        payload=formal_payload(
            object_type=object_type, object_id=object_id, body=body
        ),
        input_refs=input_refs,
        meta=dict(meta or {"sealed": False}),
    )
    return canonical_object_ref(
        object_type=object_type,
        object_id=object_id,
        content_hash_hex=digest,
        namespace=namespace,
    )


def load_staging_payload(
    store: Any, *, namespace: str, object_type: str, object_id: str
) -> Mapping[str, Any]:
    getter = getattr(store, "get_by_identity", None)
    if not callable(getter):
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="store missing get_by_identity",
            )
        )
    try:
        payload = getter(
            namespace=namespace,
            kind=KIND_STAGING,
            artifact_id=object_artifact_id(object_type, object_id),
        )
    except Exception as exc:  # noqa: BLE001
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="staging object not found",
            )
        ) from exc
    if not isinstance(payload, Mapping):
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="staging payload missing",
            )
        )
    body = payload.get("body")
    if not isinstance(body, Mapping):
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="staging body missing",
            )
        )
    return body


def find_freeze_commit_event(
    events: Sequence[Mapping[str, Any]],
    *,
    manifest_ref: ObjectRef,
) -> Mapping[str, Any] | None:
    """Return the Frozen commit event whose outputs bind exact manifest_ref."""
    return find_gated_publish_event(events, manifest_ref)


def find_gated_publish_event(
    events: Sequence[Mapping[str, Any]],
    ref: ObjectRef,
) -> Mapping[str, Any] | None:
    """Return the commit event whose outputs exact-bind an event-gated staging ref.

    Caller MUST pass a fully verified event chain for the correct namespace/run.
    Unverified / forged event lists are not accepted for publication decisions.
    """
    ref_key = _GATED_REF_OUTPUT_KEYS.get(ref.object_type)
    if ref_key is None:
        return None
    target = to_plain_dict(ref)
    for raw in events:
        if ref.object_type == "FreezeManifest":
            if str(raw.get("command")) != "freeze":
                continue
            if str(raw.get("to_status")) != "frozen":
                continue
            if str(raw.get("result_status")) != "ok":
                continue
        elif ref.object_type == "FailureKnowledgeEntry":
            # Terminal outcomes only — pipeline_started never publishes knowledge.
            if str(raw.get("result_status")) not in {"ok", "failed"}:
                continue
            if "failure_knowledge_ref" not in dict(raw.get("outputs") or {}):
                continue
        else:
            continue
        outputs = raw.get("outputs") or {}
        if not isinstance(outputs, Mapping):
            continue
        event_ref = outputs.get(ref_key)
        if not isinstance(event_ref, Mapping):
            continue
        if dict(event_ref) != target:
            continue
        staging_hash = outputs.get("staging_content_hash") or event_ref.get(
            "content_hash"
        )
        if staging_hash != ref.content_hash:
            continue
        return raw
    return None


def list_kind_payloads(
    store: Any, *, namespace: str, kind: str
) -> list[Mapping[str, Any]]:
    """List all payloads for a namespace/kind; unreadable listed ids fail closed."""
    lister = getattr(store, "list_artifact_ids", None)
    getter = getattr(store, "get_by_identity", None)
    if not callable(lister) or not callable(getter):
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.ARTIFACT_PERSIST_FAILED,
                message="store missing list/get for kind payloads",
            )
        )
    out: list[Mapping[str, Any]] = []
    for artifact_id in lister(namespace=namespace, kind=kind):
        try:
            payload = getter(
                namespace=namespace, kind=kind, artifact_id=str(artifact_id)
            )
        except Exception as exc:  # noqa: BLE001
            raise ObjectStoreError(
                FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="listed artifact is unreadable/corrupt",
                    details={
                        "kind": kind,
                        "artifact_id": str(artifact_id),
                        "cause_type": type(exc).__name__,
                    },
                )
            ) from exc
        if not isinstance(payload, Mapping):
            raise ObjectStoreError(
                FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="listed artifact payload is not a mapping",
                    details={"kind": kind, "artifact_id": str(artifact_id)},
                )
            )
        out.append(dict(payload))
    return out


def load_verified_run_events(
    store: Any, *, namespace: str, run_id: str
) -> list[Mapping[str, Any]]:
    """Load the verified controller_event chain for one run (fail closed)."""
    try:
        return load_run_event_payloads(store, namespace=namespace, run_id=run_id)
    except EventChainError as exc:
        raise ObjectStoreError(exc.failure) from exc


def load_formal_payload(
    store: Any,
    ref: ObjectRef,
    *,
    allow_staging: bool = False,
    freeze_events: Sequence[Mapping[str, Any]] | None = None,
    load_events: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
) -> Mapping[str, Any]:
    """Load object body after identity/hash checks.

    Event-gated types require a fully verified committed event chain for the
    object's run/namespace whose outputs exact-bind ``ref``, then return the
    verified staging body. Unverified / forged events never publish.
    """
    if ref.object_type in EVENT_GATED_TYPES and not allow_staging:
        body = load_staging_payload(
            store,
            namespace=ref.namespace,
            object_type=ref.object_type,
            object_id=ref.object_id,
        )
        if str(body.get("content_hash") or "") != ref.content_hash:
            raise ObjectStoreError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message=f"staging body hash mismatch vs {ref.object_type} ref",
                )
            )
        run_id = str(body.get("run_id") or "")
        if not run_id:
            raise ObjectStoreError(
                FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message=f"{ref.object_type} staging missing run_id",
                )
            )
        if freeze_events is not None:
            try:
                events = verify_event_chain(
                    list(freeze_events), namespace=ref.namespace, run_id=run_id
                )
            except EventChainError as exc:
                raise ObjectStoreError(exc.failure) from exc
        elif load_events is not None:
            try:
                events = verify_event_chain(
                    list(load_events()), namespace=ref.namespace, run_id=run_id
                )
            except EventChainError as exc:
                raise ObjectStoreError(exc.failure) from exc
        else:
            events = load_verified_run_events(
                store, namespace=ref.namespace, run_id=run_id
            )
        commit = find_gated_publish_event(events, ref)
        if commit is None:
            raise ObjectStoreError(
                FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message=(
                        f"{ref.object_type} not published "
                        "(no verified commit event binding staging ref)"
                    ),
                    details={"ref": to_plain_dict(ref), "run_id": run_id},
                )
            )
        return body

    getter = getattr(store, "get_by_identity", None)
    if not callable(getter):
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="store missing get_by_identity",
            )
        )
    artifact_id = object_artifact_id(ref.object_type, ref.object_id)
    try:
        payload = getter(
            namespace=ref.namespace, kind=KIND_OBJECT, artifact_id=artifact_id
        )
    except Exception as exc:  # noqa: BLE001
        if not allow_staging:
            raise ObjectStoreError(
                FailureDetail(
                    code=FailureCode.INVALID_REFERENCE,
                    message="formal object not found",
                    details={"ref": to_plain_dict(ref)},
                )
            ) from exc
        body = load_staging_payload(
            store,
            namespace=ref.namespace,
            object_type=ref.object_type,
            object_id=ref.object_id,
        )
        if str(body.get("content_hash") or "") != ref.content_hash:
            raise ObjectStoreError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="staging body hash mismatch",
                )
            ) from None
        return body

    if not isinstance(payload, Mapping):
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="object payload missing",
            )
        )
    if payload.get("object_type") != ref.object_type:
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.SCHEMA_MISMATCH,
                message="object_type mismatch",
            )
        )
    if payload.get("object_id") != ref.object_id:
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="object_id mismatch",
            )
        )
    body = payload.get("body")
    if not isinstance(body, Mapping):
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.INVALID_REFERENCE,
                message="object body missing",
            )
        )
    body_hash = str(body.get("content_hash") or payload.get("content_hash") or "")
    if body_hash != ref.content_hash:
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="ObjectRef content_hash does not match canonical object hash",
                details={"expected": ref.content_hash, "got": body_hash},
            )
        )
    return body


def resolve_typed_object(
    store: Any,
    ref: ObjectRef,
    *,
    allow_staging: bool = False,
    freeze_events: Sequence[Mapping[str, Any]] | None = None,
    load_events: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
) -> Any:
    body = load_formal_payload(
        store,
        ref,
        allow_staging=allow_staging,
        freeze_events=freeze_events,
        load_events=load_events,
    )
    cls = _TYPE_BUILDERS.get(ref.object_type)
    if cls is None:
        return body
    # FactorExecutionResult ObjectRef binds fingerprint via stored body content_hash
    # alias; the dataclass itself has no content_hash field (fingerprint is canonical).
    rebuild_body = dict(body)
    if ref.object_type == "FactorExecutionResult":
        rebuild_body.pop("content_hash", None)
    obj = rebuild_dataclass(cls, rebuild_body)
    if isinstance(obj, FactorExecutionResult):
        from skills.factor_mining.adapters.execution_identity import (
            execution_envelope_identity,
        )

        recomputed = execution_envelope_identity(obj)
        if recomputed != obj.fingerprint:
            raise ObjectStoreError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="FactorExecutionResult fingerprint recomputation mismatch",
                    details={"expected": obj.fingerprint, "got": recomputed},
                )
            )
        if obj.fingerprint != ref.content_hash:
            raise ObjectStoreError(
                FailureDetail(
                    code=FailureCode.HASH_MISMATCH,
                    message="FactorExecutionResult fingerprint mismatch vs ObjectRef",
                )
            )
        return obj
    if hasattr(obj, "validate_hash"):
        obj.validate_hash()
    if getattr(obj, "content_hash", None) != ref.content_hash:
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="rebuilt object content_hash mismatch",
            )
        )
    return obj


def formal_artifact_ref(
    store: Any,
    *,
    namespace: str,
    object_type: str,
    object_id: str,
    body: Mapping[str, Any],
    meta: Mapping[str, Any] | None = None,
    input_refs: tuple = (),
    kind: str = KIND_OBJECT,
) -> ArtifactRef:
    payload = formal_payload(
        object_type=object_type, object_id=object_id, body=body
    )
    preview = getattr(store, "envelope_hash", None)
    if not callable(preview):
        raise ObjectStoreError(
            FailureDetail(
                code=FailureCode.ARTIFACT_PERSIST_FAILED,
                message="store missing envelope_hash",
            )
        )
    digest = preview(
        namespace=namespace,
        kind=kind,
        artifact_id=object_artifact_id(object_type, object_id),
        payload=payload,
        input_refs=input_refs,
        meta=meta if meta is not None else {"sealed": False},
    )
    return ArtifactRef(
        kind=kind,
        artifact_id=object_artifact_id(object_type, object_id),
        namespace=namespace,
        content_hash=digest,
        schema_version=SCHEMA_VERSION,
    )


def index_entry_hash(*, object_type: str, object_id: str, content_hash_hex: str) -> str:
    return content_hash(
        {
            "object_type": object_type,
            "object_id": object_id,
            "content_hash": content_hash_hex,
        }
    )


__all__ = [
    "KIND_OBJECT",
    "KIND_STAGING",
    "KIND_EVENT",
    "EVENT_GATED_TYPES",
    "ObjectStoreError",
    "object_artifact_id",
    "formal_payload",
    "canonical_object_ref",
    "put_staging_object",
    "put_formal_object",
    "load_staging_payload",
    "find_freeze_commit_event",
    "find_gated_publish_event",
    "list_kind_payloads",
    "load_verified_run_events",
    "load_formal_payload",
    "resolve_typed_object",
    "formal_artifact_ref",
    "index_entry_hash",
]
