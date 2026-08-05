"""Unambiguous command/idempotency identity encoding."""

from __future__ import annotations

from skills.factor_mining.contracts import content_hash


def command_identity_key(
    *,
    run_id: str,
    aggregate_id: str,
    idempotency_key: str,
) -> str:
    """Canonical opaque key — no colon/-- concatenation collisions."""
    return content_hash(
        {
            "run_id": run_id,
            "aggregate_id": aggregate_id,
            "idempotency_key": idempotency_key,
        }
    )


def version_slot_id(*, run_id: str, next_version: int) -> str:
    return content_hash({"run_id": run_id, "next_version": int(next_version)})


def event_artifact_id(*, run_id: str, sequence: int) -> str:
    return content_hash({"run_id": run_id, "sequence": int(sequence), "kind": "event"})


__all__ = [
    "command_identity_key",
    "version_slot_id",
    "event_artifact_id",
]
