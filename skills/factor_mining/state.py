"""Pure run/candidate/task state aggregates and legal transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from skills.factor_mining.contracts import (
    ArtifactRef,
    CandidateStatus,
    EvidenceRef,
    ObjectRef,
    ResearchRunStatus,
    TaskLifecycleStatus,
    content_hash,
    to_plain_dict,
)

# (from_status, command) -> to_status
RUN_TRANSITIONS: dict[tuple[ResearchRunStatus, str], ResearchRunStatus] = {
    (ResearchRunStatus.BRIEFED, "activate"): ResearchRunStatus.ACTIVE,
    (ResearchRunStatus.ACTIVE, "request_freeze"): ResearchRunStatus.FREEZE_PENDING,
    (ResearchRunStatus.FREEZE_PENDING, "freeze"): ResearchRunStatus.FROZEN,
    # Phase 06: the sealed OOS path is deliberately narrow.  Nothing may
    # reopen a frozen research run or route an OOS outcome back to research.
    (ResearchRunStatus.FROZEN, "authorize_oos"): ResearchRunStatus.FROZEN,
    (ResearchRunStatus.FROZEN, "complete_oos"): ResearchRunStatus.OOS_TESTED,
    (ResearchRunStatus.OOS_TESTED, "record_gate2_approval"): ResearchRunStatus.OOS_TESTED,
    (ResearchRunStatus.OOS_TESTED, "promote"): ResearchRunStatus.PROMOTED,
    (ResearchRunStatus.OOS_TESTED, "reject_run"): ResearchRunStatus.REJECTED,
    (ResearchRunStatus.ACTIVE, "reject_run"): ResearchRunStatus.REJECTED,
    (ResearchRunStatus.FREEZE_PENDING, "reject_run"): ResearchRunStatus.REJECTED,
    (ResearchRunStatus.ACTIVE, "stop"): ResearchRunStatus.REJECTED,
}

CANDIDATE_TRANSITIONS: dict[tuple[CandidateStatus, str], CandidateStatus] = {
    (CandidateStatus.PROPOSED, "preflight_pass"): CandidateStatus.PREFLIGHT_PASSED,
    (CandidateStatus.PROPOSED, "reject"): CandidateStatus.REJECTED,
    (CandidateStatus.PREFLIGHT_PASSED, "compute"): CandidateStatus.COMPUTED,
    (CandidateStatus.PREFLIGHT_PASSED, "reject"): CandidateStatus.REJECTED,
    (CandidateStatus.COMPUTED, "evaluate"): CandidateStatus.EVALUATED,
    (CandidateStatus.COMPUTED, "reject"): CandidateStatus.REJECTED,
    (CandidateStatus.EVALUATED, "compare_pool"): CandidateStatus.REVIEW_PENDING,
    (CandidateStatus.EVALUATED, "reject"): CandidateStatus.REJECTED,
    (CandidateStatus.REVIEW_PENDING, "mark_debating"): CandidateStatus.DEBATING,
    (CandidateStatus.REVIEW_PENDING, "mark_synthesizing"): CandidateStatus.SYNTHESIZING,
    (CandidateStatus.REVIEW_PENDING, "mark_freeze_ready"): CandidateStatus.FREEZE_READY,
    (CandidateStatus.REVIEW_PENDING, "reject"): CandidateStatus.REJECTED,
    (CandidateStatus.DEBATING, "mark_debating"): CandidateStatus.DEBATING,
    (CandidateStatus.DEBATING, "mark_synthesizing"): CandidateStatus.SYNTHESIZING,
    (CandidateStatus.DEBATING, "reject"): CandidateStatus.REJECTED,
    (CandidateStatus.SYNTHESIZING, "mark_synthesizing"): CandidateStatus.SYNTHESIZING,
    (CandidateStatus.SYNTHESIZING, "mark_freeze_ready"): CandidateStatus.FREEZE_READY,
    (CandidateStatus.SYNTHESIZING, "reject"): CandidateStatus.REJECTED,
    (CandidateStatus.FREEZE_READY, "freeze"): CandidateStatus.FROZEN,
    (CandidateStatus.FREEZE_READY, "reject"): CandidateStatus.REJECTED,
    (CandidateStatus.FROZEN, "complete_oos"): CandidateStatus.OOS_TESTED,
    (CandidateStatus.OOS_TESTED, "promote"): CandidateStatus.PROMOTED,
    (CandidateStatus.OOS_TESTED, "reject"): CandidateStatus.REJECTED,
}

TASK_TRANSITIONS: dict[tuple[TaskLifecycleStatus, str], TaskLifecycleStatus] = {
    (TaskLifecycleStatus.PENDING, "claim"): TaskLifecycleStatus.CLAIMED,
    (TaskLifecycleStatus.CLAIMED, "start"): TaskLifecycleStatus.RUNNING,
    (TaskLifecycleStatus.CLAIMED, "cancel"): TaskLifecycleStatus.CANCELLED,
    (TaskLifecycleStatus.CLAIMED, "timeout"): TaskLifecycleStatus.TIMED_OUT,
    (TaskLifecycleStatus.RUNNING, "submit"): TaskLifecycleStatus.SUCCEEDED,
    (TaskLifecycleStatus.RUNNING, "fail"): TaskLifecycleStatus.FAILED,
    (TaskLifecycleStatus.RUNNING, "cancel"): TaskLifecycleStatus.CANCELLED,
    (TaskLifecycleStatus.RUNNING, "timeout"): TaskLifecycleStatus.TIMED_OUT,
}

RUN_TERMINAL = frozenset(
    {
        ResearchRunStatus.PROMOTED,
        ResearchRunStatus.REJECTED,
    }
)
# Phase 04 treats Frozen as the implemented terminal; later statuses are reserved.
PHASE04_RUN_TERMINAL = frozenset(
    {ResearchRunStatus.FROZEN, ResearchRunStatus.REJECTED}
)

CANDIDATE_TERMINAL = frozenset(
    {
        CandidateStatus.REJECTED,
        CandidateStatus.FROZEN,
        CandidateStatus.PROMOTED,
        CandidateStatus.OOS_TESTED,
    }
)

TASK_TERMINAL = frozenset(
    {
        TaskLifecycleStatus.SUCCEEDED,
        TaskLifecycleStatus.FAILED,
        TaskLifecycleStatus.CANCELLED,
        TaskLifecycleStatus.TIMED_OUT,
    }
)


class IllegalTransitionError(ValueError):
    """Raised by pure transition helpers when a move is not allowed."""


def transition_run(
    current: ResearchRunStatus, command: str
) -> ResearchRunStatus:
    key = (current, command)
    if key not in RUN_TRANSITIONS:
        raise IllegalTransitionError(
            f"illegal run transition: {current.value} + {command}"
        )
    return RUN_TRANSITIONS[key]


def transition_candidate(
    current: CandidateStatus, command: str
) -> CandidateStatus:
    key = (current, command)
    if key not in CANDIDATE_TRANSITIONS:
        raise IllegalTransitionError(
            f"illegal candidate transition: {current.value} + {command}"
        )
    return CANDIDATE_TRANSITIONS[key]


def transition_task(
    current: TaskLifecycleStatus, command: str
) -> TaskLifecycleStatus:
    key = (current, command)
    if key not in TASK_TRANSITIONS:
        raise IllegalTransitionError(
            f"illegal task transition: {current.value} + {command}"
        )
    return TASK_TRANSITIONS[key]


@dataclass
class CandidateAggregate:
    candidate_id: str
    factor_ref: ObjectRef
    status: CandidateStatus
    version: int = 1
    parent_ref: ObjectRef | None = None
    revision: int = 1
    preflight_ref: ObjectRef | None = None
    execution_ref: ObjectRef | None = None
    evaluation_ref: ObjectRef | None = None
    compare_ref: ObjectRef | None = None
    review_refs: tuple[ObjectRef, ...] = ()
    pool_decision_ref: ObjectRef | None = None
    freeze_manifest_ref: ObjectRef | None = None

    def to_payload(self) -> dict[str, Any]:
        return to_plain_dict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> CandidateAggregate:
        return cls(
            candidate_id=str(payload["candidate_id"]),
            factor_ref=ObjectRef(**dict(payload["factor_ref"])),
            status=CandidateStatus(payload["status"]),
            version=int(payload.get("version", 1)),
            parent_ref=(
                ObjectRef(**dict(payload["parent_ref"]))
                if payload.get("parent_ref")
                else None
            ),
            revision=int(payload.get("revision", 1)),
            preflight_ref=(
                ObjectRef(**dict(payload["preflight_ref"]))
                if payload.get("preflight_ref")
                else None
            ),
            execution_ref=(
                ObjectRef(**dict(payload["execution_ref"]))
                if payload.get("execution_ref")
                else None
            ),
            evaluation_ref=(
                ObjectRef(**dict(payload["evaluation_ref"]))
                if payload.get("evaluation_ref")
                else None
            ),
            compare_ref=(
                ObjectRef(**dict(payload["compare_ref"]))
                if payload.get("compare_ref")
                else None
            ),
            review_refs=tuple(
                ObjectRef(**dict(item)) for item in payload.get("review_refs", ())
            ),
            pool_decision_ref=(
                ObjectRef(**dict(payload["pool_decision_ref"]))
                if payload.get("pool_decision_ref")
                else None
            ),
            freeze_manifest_ref=(
                ObjectRef(**dict(payload["freeze_manifest_ref"]))
                if payload.get("freeze_manifest_ref")
                else None
            ),
        )


@dataclass
class TaskAggregate:
    task_id: str
    run_id: str
    role_id: str
    status: TaskLifecycleStatus
    version: int = 1
    parent_task_id: str | None = None
    candidate_id: str | None = None
    attempt: int = 1
    debate_round: int = 0
    lease_id: str | None = None
    reservation_id: str | None = None
    output_ref: ObjectRef | None = None
    visibility: tuple[str, ...] = ()
    # Immutable authorization input set established by create_task.  Task-view
    # construction may project this set, but must never accept fresh caller refs.
    input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = ()
    expected_output_type: str = "ResearchDecision"

    def to_payload(self) -> dict[str, Any]:
        return to_plain_dict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> TaskAggregate:
        return cls(
            task_id=str(payload["task_id"]),
            run_id=str(payload["run_id"]),
            role_id=str(payload["role_id"]),
            status=TaskLifecycleStatus(payload["status"]),
            version=int(payload.get("version", 1)),
            parent_task_id=payload.get("parent_task_id"),
            candidate_id=payload.get("candidate_id"),
            attempt=int(payload.get("attempt", 1)),
            debate_round=int(payload.get("debate_round", 0)),
            lease_id=payload.get("lease_id"),
            reservation_id=payload.get("reservation_id"),
            output_ref=(
                ObjectRef(**dict(payload["output_ref"]))
                if payload.get("output_ref")
                else None
            ),
            visibility=tuple(payload.get("visibility", ())),
            input_refs=tuple(
                _task_ref_from_payload(item) for item in payload["input_refs"]
            ),
            expected_output_type=str(payload["expected_output_type"]),
        )


def _task_ref_from_payload(
    raw: Mapping[str, Any],
) -> ObjectRef | ArtifactRef | EvidenceRef:
    """Restore one task-authorized ref without weakening its concrete type."""
    if "object_type" in raw:
        return ObjectRef(**dict(raw))
    if "evidence_id" in raw:
        value = dict(raw)
        artifact = value.get("artifact")
        if isinstance(artifact, Mapping):
            value["artifact"] = ArtifactRef(**dict(artifact))
        return EvidenceRef(**value)
    return ArtifactRef(**dict(raw))


@dataclass
class RunAggregate:
    run_id: str
    namespace: str
    brief_ref: ObjectRef
    status: ResearchRunStatus
    version: int = 1
    event_head_seq: int = 0
    event_head_hash: str = "0" * 64
    stop_reason: str | None = None
    gate1_approval_ref: ArtifactRef | None = None
    freeze_manifest_ref: ObjectRef | None = None
    oos_authorization_ref: ObjectRef | None = None
    oos_attempt_refs: tuple[ArtifactRef, ...] = ()
    oos_result_ref: ObjectRef | None = None
    gate2_approval_ref: ArtifactRef | None = None
    release_knowledge_ref: ArtifactRef | None = None
    budget_limits: Mapping[str, int] = field(default_factory=dict)
    budget_remaining: Mapping[str, int] = field(default_factory=dict)
    budget_reservations: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    candidates: dict[str, CandidateAggregate] = field(default_factory=dict)
    tasks: dict[str, TaskAggregate] = field(default_factory=dict)
    idempotency: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    failure_knowledge_ids: tuple[str, ...] = ()

    def snapshot_hash(self) -> str:
        return content_hash(self.to_payload())

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "namespace": self.namespace,
            "brief_ref": to_plain_dict(self.brief_ref),
            "status": self.status.value,
            "version": self.version,
            "event_head_seq": self.event_head_seq,
            "event_head_hash": self.event_head_hash,
            "stop_reason": self.stop_reason,
            "gate1_approval_ref": (
                to_plain_dict(self.gate1_approval_ref)
                if self.gate1_approval_ref is not None
                else None
            ),
            "freeze_manifest_ref": (
                to_plain_dict(self.freeze_manifest_ref)
                if self.freeze_manifest_ref is not None
                else None
            ),
            "oos_authorization_ref": (
                to_plain_dict(self.oos_authorization_ref)
                if self.oos_authorization_ref is not None
                else None
            ),
            "oos_attempt_refs": [to_plain_dict(ref) for ref in self.oos_attempt_refs],
            "oos_result_ref": (
                to_plain_dict(self.oos_result_ref)
                if self.oos_result_ref is not None
                else None
            ),
            "gate2_approval_ref": (
                to_plain_dict(self.gate2_approval_ref)
                if self.gate2_approval_ref is not None
                else None
            ),
            "release_knowledge_ref": (
                to_plain_dict(self.release_knowledge_ref)
                if self.release_knowledge_ref is not None
                else None
            ),
            "budget_limits": dict(self.budget_limits),
            "budget_remaining": dict(self.budget_remaining),
            "budget_reservations": {
                key: dict(value) for key, value in self.budget_reservations.items()
            },
            "candidates": {
                key: value.to_payload() for key, value in self.candidates.items()
            },
            "tasks": {key: value.to_payload() for key, value in self.tasks.items()},
            "idempotency": {key: dict(value) for key, value in self.idempotency.items()},
            "failure_knowledge_ids": list(self.failure_knowledge_ids),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RunAggregate:
        return cls(
            run_id=str(payload["run_id"]),
            namespace=str(payload["namespace"]),
            brief_ref=ObjectRef(**dict(payload["brief_ref"])),
            status=ResearchRunStatus(payload["status"]),
            version=int(payload.get("version", 1)),
            event_head_seq=int(payload.get("event_head_seq", 0)),
            event_head_hash=str(payload.get("event_head_hash", "0" * 64)),
            stop_reason=payload.get("stop_reason"),
            gate1_approval_ref=(
                ArtifactRef(**dict(payload["gate1_approval_ref"]))
                if payload.get("gate1_approval_ref")
                else None
            ),
            freeze_manifest_ref=(
                ObjectRef(**dict(payload["freeze_manifest_ref"]))
                if payload.get("freeze_manifest_ref")
                else None
            ),
            oos_authorization_ref=(
                ObjectRef(**dict(payload["oos_authorization_ref"]))
                if payload.get("oos_authorization_ref")
                else None
            ),
            oos_attempt_refs=tuple(
                ArtifactRef(**dict(item)) for item in payload.get("oos_attempt_refs", ())
            ),
            oos_result_ref=(
                ObjectRef(**dict(payload["oos_result_ref"]))
                if payload.get("oos_result_ref")
                else None
            ),
            gate2_approval_ref=(
                ArtifactRef(**dict(payload["gate2_approval_ref"]))
                if payload.get("gate2_approval_ref")
                else None
            ),
            release_knowledge_ref=(
                ArtifactRef(**dict(payload["release_knowledge_ref"]))
                if payload.get("release_knowledge_ref")
                else None
            ),
            budget_limits=dict(payload.get("budget_limits", {})),
            budget_remaining=dict(payload.get("budget_remaining", {})),
            budget_reservations={
                key: dict(value)
                for key, value in dict(payload.get("budget_reservations", {})).items()
            },
            candidates={
                key: CandidateAggregate.from_payload(value)
                for key, value in dict(payload.get("candidates", {})).items()
            },
            tasks={
                key: TaskAggregate.from_payload(value)
                for key, value in dict(payload.get("tasks", {})).items()
            },
            idempotency={
                key: dict(value)
                for key, value in dict(payload.get("idempotency", {})).items()
            },
            failure_knowledge_ids=tuple(payload.get("failure_knowledge_ids", ())),
        )

    def with_version_bump(self) -> RunAggregate:
        return replace(self, version=self.version + 1)


__all__ = [
    "RUN_TRANSITIONS",
    "CANDIDATE_TRANSITIONS",
    "TASK_TRANSITIONS",
    "RUN_TERMINAL",
    "PHASE04_RUN_TERMINAL",
    "CANDIDATE_TERMINAL",
    "TASK_TERMINAL",
    "IllegalTransitionError",
    "transition_run",
    "transition_candidate",
    "transition_task",
    "CandidateAggregate",
    "TaskAggregate",
    "RunAggregate",
]
