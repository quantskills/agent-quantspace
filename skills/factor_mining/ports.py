"""Abstract ports used by factor_mining orchestration.

Concrete adapters live under factor_mining and call outward into other skills.
Phase 01 freezes the protocol shapes only; no compute/analyze/store/report logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from skills.factor_mining.contracts import (
    ArtifactRef,
    EvaluationReport,
    EvaluationRequest,
    EvidenceRef,
    FactorComputeRequest,
    FactorExecutionResult,
    ObjectRef,
    ReportRequest,
)


@runtime_checkable
class FactorExecutionPort(Protocol):
    """Execute a FactorSpec against a panel through compute-compatible adapters."""

    def execute(self, request: FactorComputeRequest) -> FactorExecutionResult:
        """Return values/mask refs and index lineage, or a structured failure."""


@runtime_checkable
class AnalyzePort(Protocol):
    """Deterministic preflight, evaluation, and pool-incremental comparison."""

    def preflight(self, request: EvaluationRequest) -> EvaluationReport:
        """Run hard checks before factor execution or return-based scoring."""

    def evaluate(self, request: EvaluationRequest) -> EvaluationReport:
        """Produce sectioned MetricFact/RuleCheck results for one candidate."""

    def compare_to_pool(self, request: EvaluationRequest) -> EvaluationReport:
        """Compare one candidate to an explicit existing pool via formal evidence."""


@runtime_checkable
class ArtifactStorePort(Protocol):
    """Persist and load research artifacts under a caller-provided namespace."""

    def put(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = (),
    ) -> ArtifactRef:
        """Store a JSON-serializable payload and return a checksummed ArtifactRef."""

    def put_if_absent(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = (),
        meta: Mapping[str, Any] | None = None,
    ) -> Any:
        """Append-only create: identical content idempotent; divergent content rejected."""

    def get(self, ref: ArtifactRef) -> Mapping[str, Any]:
        """Load a payload after verifying namespace and content hash."""

    def get_by_identity(
        self, *, namespace: str, kind: str, artifact_id: str
    ) -> Mapping[str, Any]:
        """Load payload by identity after verifying on-disk/in-memory checksum."""

    def get_envelope(self, ref: ArtifactRef) -> Mapping[str, Any]:
        """Return verified envelope including payload + meta (sealed capability)."""

    def get_envelope_by_identity(
        self, *, namespace: str, kind: str, artifact_id: str
    ) -> Mapping[str, Any]:
        """Load full envelope by identity after verifying checksum."""

    def envelope_hash(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple[ObjectRef | ArtifactRef | EvidenceRef, ...] = (),
        meta: Mapping[str, Any] | None = None,
    ) -> str:
        """Preview the envelope content hash without writing."""

    def list_artifact_ids(self, *, namespace: str, kind: str) -> list[str]:
        """List artifact ids under a namespace/kind."""

    def exists(self, ref: ArtifactRef) -> bool:
        """Return True when the artifact is present and checksum-valid."""


@runtime_checkable
class ReportPort(Protocol):
    """Render research reports from formal object/evidence/artifact refs only."""

    def render(self, request: ReportRequest) -> ArtifactRef:
        """Create a report artifact; numeric claims must cite formal evidence refs."""


__all__ = [
    "FactorExecutionPort",
    "AnalyzePort",
    "ArtifactStorePort",
    "ReportPort",
]
