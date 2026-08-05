"""Canonical controller event bodies and hash-chain helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from skills.factor_mining.contracts import (
    SCHEMA_VERSION,
    ArtifactRef,
    ControllerEvent,
    EvidenceRef,
    FailureDetail,
    ObjectRef,
    content_hash,
    to_plain_dict,
)

GENESIS_HASH = "0" * 64


def _ref_plain(ref: ObjectRef | ArtifactRef | EvidenceRef | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(ref, Mapping):
        return dict(ref)
    return to_plain_dict(ref)


def build_event_body(
    *,
    sequence: int,
    prev_hash: str,
    run_id: str,
    aggregate_kind: str,
    aggregate_id: str,
    command: str,
    idempotency_key: str,
    actor_id: str,
    role_id: str,
    from_status: str,
    to_status: str,
    input_refs: Sequence[ObjectRef | ArtifactRef | EvidenceRef | Mapping[str, Any]] = (),
    output_refs: Sequence[ObjectRef | ArtifactRef | EvidenceRef | Mapping[str, Any]] = (),
    budget_delta: Mapping[str, int] | None = None,
    parent_task_id: str | None = None,
    result_status: str = "ok",
    failure: FailureDetail | Mapping[str, Any] | None = None,
    state_after_digest: str,
    outputs: Mapping[str, Any] | None = None,
    schema_version: str = SCHEMA_VERSION,
) -> dict[str, Any]:
    """Canonical event payload used for hashing and persistence (no event_hash)."""
    failure_plain: dict[str, Any] | None
    if failure is None:
        failure_plain = None
    elif isinstance(failure, FailureDetail):
        failure_plain = to_plain_dict(failure)
    else:
        failure_plain = dict(failure)
    return {
        "sequence": int(sequence),
        "prev_hash": prev_hash,
        "run_id": run_id,
        "aggregate_kind": aggregate_kind,
        "aggregate_id": aggregate_id,
        "command": command,
        "idempotency_key": idempotency_key,
        "actor_id": actor_id,
        "role_id": role_id,
        "parent_task_id": parent_task_id,
        "from_status": from_status,
        "to_status": to_status,
        "input_refs": [_ref_plain(ref) for ref in input_refs],
        "output_refs": [_ref_plain(ref) for ref in output_refs],
        "budget_delta": dict(budget_delta or {}),
        "result_status": result_status,
        "failure": failure_plain,
        "state_after_digest": state_after_digest,
        "outputs": dict(outputs or {}),
        "schema_version": schema_version,
    }


def hash_event_body(body: Mapping[str, Any]) -> str:
    payload = dict(body)
    payload.pop("event_hash", None)
    return content_hash(payload)


def event_from_body(body: Mapping[str, Any], *, event_hash: str) -> ControllerEvent:
    failure_raw = body.get("failure")
    failure = None
    if isinstance(failure_raw, Mapping):
        failure = FailureDetail(
            code=failure_raw["code"],
            message=str(failure_raw["message"]),
            severity=failure_raw.get("severity", "hard_fail"),
            retryable=bool(failure_raw.get("retryable", False)),
            details=dict(failure_raw.get("details") or {}),
        )
    return ControllerEvent(
        sequence=int(body["sequence"]),
        prev_hash=str(body["prev_hash"]),
        event_hash=event_hash,
        run_id=str(body["run_id"]),
        aggregate_kind=str(body["aggregate_kind"]),
        aggregate_id=str(body["aggregate_id"]),
        command=str(body["command"]),
        idempotency_key=str(body["idempotency_key"]),
        actor_id=str(body["actor_id"]),
        role_id=str(body["role_id"]),
        from_status=str(body["from_status"]),
        to_status=str(body["to_status"]),
        input_refs=tuple(_coerce_stored_ref(item) for item in body.get("input_refs", ())),
        output_refs=tuple(_coerce_stored_ref(item) for item in body.get("output_refs", ())),
        budget_delta=dict(body.get("budget_delta") or {}),
        parent_task_id=body.get("parent_task_id"),
        result_status=str(body.get("result_status", "ok")),
        failure=failure,
        state_after_digest=str(body["state_after_digest"]),
        outputs=dict(body.get("outputs") or {}),
        schema_version=str(body.get("schema_version", SCHEMA_VERSION)),
    )


def _coerce_stored_ref(
    raw: Mapping[str, Any],
) -> ObjectRef | ArtifactRef | EvidenceRef:
    if "object_type" in raw:
        return ObjectRef(**dict(raw))
    if "evidence_id" in raw:
        return EvidenceRef(**dict(raw))
    return ArtifactRef(**dict(raw))


__all__ = [
    "GENESIS_HASH",
    "build_event_body",
    "hash_event_body",
    "event_from_body",
]
