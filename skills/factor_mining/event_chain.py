"""Strict controller event-chain verification (shared by replay and gated getters).

Neutral module: no imports from controller or objects, to avoid cycles.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from skills.factor_mining.contracts import (
    SCHEMA_VERSION,
    FailureCode,
    FailureDetail,
    content_hash,
)
from skills.factor_mining.events import (
    GENESIS_HASH,
    event_from_body,
    hash_event_body,
)

KIND_EVENT = "controller_event"


class EventChainError(Exception):
    """Fail-closed event ledger corruption / binding failure."""

    def __init__(self, failure: FailureDetail) -> None:
        super().__init__(failure.message)
        self.failure = failure


def state_after_digest_from_run_payload(run_payload: Mapping[str, Any]) -> str:
    """Canonical state digest used in ControllerEvent.state_after_digest."""
    payload = dict(run_payload)
    payload["event_head_hash"] = None
    return content_hash(
        {k: v for k, v in payload.items() if k != "event_head_hash"}
    )


def parse_run_event_sequences(
    *, run_id: str, artifact_ids: Sequence[str]
) -> list[int]:
    """Parse listed event artifact ids; reject malformed/duplicate/gapped sets."""
    prefix = f"{run_id}-"
    seqs: list[int] = []
    seen: set[int] = set()
    for aid in artifact_ids:
        text = str(aid)
        if not text.startswith(prefix):
            continue
        tail = text[len(prefix) :]
        if not tail.isdigit() or int(tail) < 1 or f"{int(tail):08d}" != tail:
            raise EventChainError(
                FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="malformed controller_event artifact id",
                    details={"artifact_id": text, "run_id": run_id},
                )
            )
        seq = int(tail)
        if seq in seen:
            raise EventChainError(
                FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="duplicate controller_event sequence id",
                    details={"sequence": seq, "run_id": run_id},
                )
            )
        seen.add(seq)
        seqs.append(seq)
    ordered = sorted(seqs)
    if ordered and ordered != list(range(1, ordered[-1] + 1)):
        raise EventChainError(
            FailureDetail(
                code=FailureCode.RECOVERY_REQUIRED,
                message="controller_event sequence gap or non-contiguous ids",
                details={"sequences": ordered, "run_id": run_id},
            )
        )
    return ordered


def verify_event_payload(
    raw: Mapping[str, Any],
    *,
    namespace: str,
    run_id: str,
    expected_sequence: int,
    prev_hash: str,
) -> dict[str, Any]:
    """Verify one persisted event payload against chain position and bindings."""
    if "event_hash" not in raw:
        raise EventChainError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="event missing event_hash",
                details={"sequence": expected_sequence},
            )
        )
    body = {k: v for k, v in dict(raw).items() if k != "event_hash"}
    event_hash = str(raw["event_hash"])
    if int(body.get("sequence", -1)) != expected_sequence:
        raise EventChainError(
            FailureDetail(
                code=FailureCode.RECOVERY_REQUIRED,
                message="event sequence mismatch",
                details={
                    "expected": expected_sequence,
                    "got": body.get("sequence"),
                },
            )
        )
    if str(body.get("prev_hash")) != prev_hash:
        raise EventChainError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="event chain prev_hash mismatch",
                details={"sequence": expected_sequence},
            )
        )
    if str(body.get("run_id")) != run_id:
        raise EventChainError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="event run_id mismatch",
                details={"expected": run_id, "got": body.get("run_id")},
            )
        )
    if str(body.get("schema_version", "")) != SCHEMA_VERSION:
        raise EventChainError(
            FailureDetail(
                code=FailureCode.SCHEMA_MISMATCH,
                message="event schema_version mismatch",
                details={
                    "expected": SCHEMA_VERSION,
                    "got": body.get("schema_version"),
                },
            )
        )
    if hash_event_body(body) != event_hash:
        raise EventChainError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="event hash mismatch",
                details={"sequence": expected_sequence},
            )
        )
    event = event_from_body(body, event_hash=event_hash)
    if event.compute_hash() != event_hash:
        raise EventChainError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="ControllerEvent.compute_hash mismatch",
                details={"sequence": expected_sequence},
            )
        )
    out_run = dict(body.get("outputs") or {}).get("run")
    if not isinstance(out_run, Mapping):
        raise EventChainError(
            FailureDetail(
                code=FailureCode.RECOVERY_REQUIRED,
                message="event outputs.run required",
                details={"sequence": expected_sequence},
            )
        )
    if str(out_run.get("namespace")) != namespace:
        raise EventChainError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="event namespace mismatch",
                details={
                    "expected": namespace,
                    "got": out_run.get("namespace"),
                    "sequence": expected_sequence,
                },
            )
        )
    if str(out_run.get("run_id")) != run_id:
        raise EventChainError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="event outputs.run.run_id mismatch",
                details={"sequence": expected_sequence},
            )
        )
    digest = state_after_digest_from_run_payload(out_run)
    if digest != event.state_after_digest:
        raise EventChainError(
            FailureDetail(
                code=FailureCode.HASH_MISMATCH,
                message="state_after_digest mismatch",
                details={"sequence": expected_sequence},
            )
        )
    verified = dict(body)
    verified["event_hash"] = event_hash
    return verified


def verify_event_chain(
    events: Sequence[Mapping[str, Any]],
    *,
    namespace: str,
    run_id: str,
) -> list[dict[str, Any]]:
    """Verify an ordered event list; empty is allowed (no events yet)."""
    verified: list[dict[str, Any]] = []
    prev = GENESIS_HASH
    for idx, raw in enumerate(events, start=1):
        item = verify_event_payload(
            raw,
            namespace=namespace,
            run_id=run_id,
            expected_sequence=idx,
            prev_hash=prev,
        )
        verified.append(item)
        prev = str(item["event_hash"])
    return verified


def load_run_event_payloads(
    store: Any,
    *,
    namespace: str,
    run_id: str,
) -> list[dict[str, Any]]:
    """Load and strictly verify the event chain for one run.

    Listed IDs must be well-formed, contiguous, and fully readable. A getter
    failure for a listed id is corruption (never treated as end-of-log).
    """
    getter = getattr(store, "get_by_identity", None)
    if not callable(getter):
        raise EventChainError(
            FailureDetail(
                code=FailureCode.ARTIFACT_PERSIST_FAILED,
                message="store missing get_by_identity for event chain",
            )
        )
    lister = getattr(store, "list_artifact_ids", None)
    if not callable(lister):
        raise EventChainError(
            FailureDetail(
                code=FailureCode.ARTIFACT_PERSIST_FAILED,
                message="store missing list_artifact_ids for event chain",
            )
        )
    listed = [
        str(aid)
        for aid in lister(namespace=namespace, kind=KIND_EVENT)
        if str(aid).startswith(f"{run_id}-")
    ]
    sequences = parse_run_event_sequences(run_id=run_id, artifact_ids=listed)
    raw_events: list[dict[str, Any]] = []
    for seq in sequences:
        artifact_id = f"{run_id}-{seq:08d}"
        try:
            payload = getter(
                namespace=namespace, kind=KIND_EVENT, artifact_id=artifact_id
            )
        except Exception as exc:  # noqa: BLE001
            raise EventChainError(
                FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="listed controller_event is unreadable/corrupt",
                    details={
                        "artifact_id": artifact_id,
                        "cause_type": type(exc).__name__,
                        "cause": str(exc),
                    },
                )
            ) from exc
        if not isinstance(payload, Mapping):
            raise EventChainError(
                FailureDetail(
                    code=FailureCode.RECOVERY_REQUIRED,
                    message="listed controller_event payload is not a mapping",
                    details={"artifact_id": artifact_id},
                )
            )
        raw_events.append(dict(payload))
    return verify_event_chain(raw_events, namespace=namespace, run_id=run_id)


__all__ = [
    "KIND_EVENT",
    "EventChainError",
    "state_after_digest_from_run_payload",
    "parse_run_event_sequences",
    "verify_event_payload",
    "verify_event_chain",
    "load_run_event_payloads",
]
