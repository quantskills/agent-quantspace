from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from skills.factor_mining import (
    AnalyzePort,
    ArtifactRef,
    ArtifactStorePort,
    EvaluationReport,
    EvaluationRequest,
    EvaluationSection,
    FactorComputeRequest,
    FactorExecutionPort,
    FactorExecutionResult,
    FailureCode,
    FailureDetail,
    IndexSchema,
    ReportPort,
    ReportRequest,
    SectionStatus,
)
from tests.skills.factor_mining.builders import (
    make_artifact_ref,
    make_factor_spec,
    make_object_ref,
    make_provenance,
)


class FakeExecutionPort:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[FactorComputeRequest] = []

    def execute(self, request: FactorComputeRequest) -> FactorExecutionResult:
        from skills.factor_mining.adapters.execution_identity import (
            execution_envelope_identity_from_parts,
        )

        self.calls.append(request)
        index_schema = IndexSchema(
            names=("symbol", "date"),
            symbol_level="symbol",
            datetime_level="date",
            level_order=(0, 1),
            timezone="UTC",
        )
        provenance = make_provenance(
            producer="fake-compute",
            namespace=request.namespace,
            data_version=request.data_version,
        )
        if self.fail:
            fingerprint = execution_envelope_identity_from_parts(
                request_id=request.request_id,
                experiment_id=request.experiment_id,
                execution_id=request.execution_id,
                brief_ref=request.brief_ref,
                factor_ref=request.factor_ref,
                values_ref=None,
                valid_mask_ref=None,
                index_schema=index_schema,
                provenance=provenance,
                callable_fingerprint="c" * 64,
                data_version=request.data_version,
                split_id=request.split_id,
                values_content_hash=None,
                valid_mask_content_hash=None,
                warnings=(),
                failure_code=FailureCode.FACTOR_RUNTIME_FAILED.value,
            )
            return FactorExecutionResult(
                request_id=request.request_id,
                experiment_id=request.experiment_id,
                execution_id=request.execution_id,
                brief_ref=request.brief_ref,
                factor_ref=request.factor_ref,
                values_ref=None,
                valid_mask_ref=None,
                index_schema=index_schema,
                provenance=provenance,
                fingerprint=fingerprint,
                callable_fingerprint="c" * 64,
                data_version=request.data_version,
                split_id=request.split_id,
                values_content_hash=None,
                valid_mask_content_hash=None,
                failure=FailureDetail(
                    code=FailureCode.FACTOR_RUNTIME_FAILED,
                    message="boom",
                ),
            )
        # Envelope ArtifactRef hashes intentionally distinct from Series content hashes.
        values_series_hash = "a" * 64
        mask_series_hash = "b" * 64
        values_ref = make_artifact_ref(
            kind="factor_values",
            artifact_id="v1",
            namespace=request.namespace,
            content_hash="d" * 64,
        )
        mask_ref = make_artifact_ref(
            kind="valid_mask",
            artifact_id="m1",
            namespace=request.namespace,
            content_hash="e" * 64,
        )
        callable_fp = "c" * 64
        fingerprint = execution_envelope_identity_from_parts(
            request_id=request.request_id,
            experiment_id=request.experiment_id,
            execution_id=request.execution_id,
            brief_ref=request.brief_ref,
            factor_ref=request.factor_ref,
            values_ref=values_ref,
            valid_mask_ref=mask_ref,
            index_schema=index_schema,
            provenance=provenance,
            callable_fingerprint=callable_fp,
            data_version=request.data_version,
            split_id=request.split_id,
            values_content_hash=values_series_hash,
            valid_mask_content_hash=mask_series_hash,
            warnings=(),
            failure_code=None,
        )
        return FactorExecutionResult(
            request_id=request.request_id,
            experiment_id=request.experiment_id,
            execution_id=request.execution_id,
            brief_ref=request.brief_ref,
            factor_ref=request.factor_ref,
            values_ref=values_ref,
            valid_mask_ref=mask_ref,
            index_schema=index_schema,
            provenance=provenance,
            fingerprint=fingerprint,
            callable_fingerprint=callable_fp,
            data_version=request.data_version,
            split_id=request.split_id,
            values_content_hash=values_series_hash,
            valid_mask_content_hash=mask_series_hash,
        )


class FakeAnalyzePort:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def _report(self, request: EvaluationRequest, op: str) -> EvaluationReport:
        self.ops.append(op)
        return EvaluationReport(
            report_id=f"{op}-{request.request_id}",
            request_id=request.request_id,
            brief_ref=request.brief_ref,
            factor_ref=request.factor_ref,
            execution_ref=request.execution_ref,
            protocol_id=request.protocol_id,
            data_version=request.data_version,
            split_id=request.split_id,
            pool_refs=tuple(request.pool_refs),
            sections=(
                EvaluationSection(name="data_quality", status=SectionStatus.NOT_RUN),
            ),
            provenance=make_provenance(
                producer="fake-analyze",
                namespace=request.namespace,
                data_version=request.data_version,
            ),
            engine_version="fake-analyze-0",
        )

    def preflight(self, request: EvaluationRequest) -> EvaluationReport:
        return self._report(request, "preflight")

    def evaluate(self, request: EvaluationRequest) -> EvaluationReport:
        return self._report(request, "evaluate")

    def compare_to_pool(self, request: EvaluationRequest) -> EvaluationReport:
        return self._report(request, "compare_to_pool")


class FakeArtifactStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], Mapping[str, Any]] = {}

    def put(
        self,
        *,
        namespace: str,
        kind: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        input_refs: tuple = (),
    ) -> ArtifactRef:
        self._items[(namespace, kind, artifact_id)] = dict(payload)
        return ArtifactRef(
            kind=kind,
            artifact_id=artifact_id,
            namespace=namespace,
            content_hash="d" * 64,
        )

    def get(self, ref: ArtifactRef) -> Mapping[str, Any]:
        key = (ref.namespace, ref.kind, ref.artifact_id)
        if key not in self._items:
            raise KeyError(key)
        return self._items[key]

    def exists(self, ref: ArtifactRef) -> bool:
        return (ref.namespace, ref.kind, ref.artifact_id) in self._items


class FakeReportPort:
    def __init__(self, store: FakeArtifactStore) -> None:
        self.store = store

    def render(self, request: ReportRequest) -> ArtifactRef:
        return self.store.put(
            namespace=request.namespace,
            kind="report",
            artifact_id=request.request_id,
            payload={"title": request.title, "run_id": request.run_id},
        )


def test_ports_are_structural_and_dependency_inverted() -> None:
    execution: FactorExecutionPort = FakeExecutionPort()
    analyze: AnalyzePort = FakeAnalyzePort()
    store: ArtifactStorePort = FakeArtifactStore()
    report: ReportPort = FakeReportPort(store)  # type: ignore[arg-type]

    factor = make_factor_spec()
    factor_ref = make_object_ref(
        object_type="FactorSpec",
        object_id=factor.factor_id,
        content_hash=factor.content_hash,
    )
    compute_request = FactorComputeRequest(
        request_id="c1",
        namespace="ns.demo",
        experiment_id="e1",
        execution_id="x1",
        brief_ref=factor.brief_ref,
        factor_ref=factor_ref,
        data_version="data-v1",
        split_id="validation",
    )
    result = execution.execute(compute_request)
    assert result.failure is None
    assert result.values_ref is not None

    eval_request = EvaluationRequest(
        request_id="a1",
        namespace="ns.demo",
        brief_ref=factor.brief_ref,
        factor_ref=factor_ref,
        execution_ref=None,
        protocol_id="proto-1",
        data_version="data-v1",
        split_id="validation",
    )
    assert analyze.preflight(eval_request).report_id.startswith("preflight-")
    assert analyze.evaluate(eval_request).report_id.startswith("evaluate-")
    assert analyze.compare_to_pool(eval_request).report_id.startswith("compare_to_pool-")

    ref = store.put(
        namespace="ns.demo",
        kind="note",
        artifact_id="n1",
        payload={"ok": True},
    )
    assert store.exists(ref)
    assert store.get(ref)["ok"] is True

    report_ref = report.render(
        ReportRequest(
            request_id="r1",
            namespace="ns.demo",
            run_id="run-1",
            title="demo",
            object_refs=(factor_ref,),
        )
    )
    assert report_ref.kind == "report"


def test_fake_execution_port_propagates_structured_failure() -> None:
    execution: FactorExecutionPort = FakeExecutionPort(fail=True)
    factor = make_factor_spec()
    result = execution.execute(
        FactorComputeRequest(
            request_id="c2",
            namespace="ns.demo",
            experiment_id="e1",
            execution_id="x2",
            brief_ref=factor.brief_ref,
            factor_ref=make_object_ref(
                object_type="FactorSpec",
                object_id=factor.factor_id,
                content_hash=factor.content_hash,
            ),
            data_version="data-v1",
            split_id="validation",
        )
    )
    assert result.failure is not None
    assert result.failure.code is FailureCode.FACTOR_RUNTIME_FAILED
    with pytest.raises(KeyError):
        FakeArtifactStore().get(make_artifact_ref())
