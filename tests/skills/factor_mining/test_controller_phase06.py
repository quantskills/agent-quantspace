"""Phase 06 sealed OOS: one-shot ledger, no feedback, and final release."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from skills.factor_mining.contracts import (
    CandidateStatus,
    EvaluationReport,
    EvaluationRequest,
    EvaluationSection,
    FactorComputeRequest,
    FailureCode,
    MetricFact,
    ObjectRef,
    OOSAttempt,
    OOSAuthorization,
    ResearchRunStatus,
    SectionStatus,
    TaskResultStatus,
    rebuild_dataclass,
    to_plain_dict,
)
from skills.factor_mining.controller import CommandRequest
from skills.factor_mining.event_chain import state_after_digest_from_run_payload
from skills.factor_mining.events import hash_event_body
from skills.factor_mining.objects import put_formal_object, resolve_typed_object
from tests.skills.factor_mining.builders import make_evidence_ref, make_provenance
from tests.skills.factor_mining.test_controller_phase04 import (
    NS,
    _brief_and_store,
    _caller_freeze_intent,
    _controller,
    _create_active_run,
    _ok_execution,
    _ok_report,
    _persist_factor,
    _persist_pool,
    _persist_review,
    _pipeline_payload,
)


class _OOSAnalyze:
    def __init__(self, *, pass_thresholds: bool = True) -> None:
        self.calls: list[str] = []
        self.pass_thresholds = pass_thresholds

    def preflight(self, request):
        self.calls.append("preflight")
        return _ok_report(request, "pre")

    def compare_to_pool(self, request):
        self.calls.append("compare_to_pool")
        return _ok_report(request, "compare")

    def evaluate(self, request):
        self.calls.append(f"evaluate:{request.split_id}")
        if request.split_id != "sealed":
            return _ok_report(request, "eval")
        facts = (
            MetricFact(
                name="rank_ic_ir",
                value=0.8 if self.pass_thresholds else 0.1,
                unit="ratio",
                sample_range="sealed",
                engine_version="analyze-test",
                data_version=request.data_version,
                evidence=make_evidence_ref(namespace=NS),
            ),
            MetricFact(
                name="coverage_worst",
                value=0.9,
                unit="ratio",
                sample_range="sealed",
                engine_version="analyze-test",
                data_version=request.data_version,
                evidence=make_evidence_ref(namespace=NS),
            ),
            MetricFact(
                name="group_turnover_mean",
                value=0.1,
                unit="ratio",
                sample_range="sealed",
                engine_version="analyze-test",
                data_version=request.data_version,
                evidence=make_evidence_ref(namespace=NS),
            ),
        )
        return EvaluationReport(
            report_id=f"oos-report-{request.request_id}",
            request_id=request.request_id,
            brief_ref=request.brief_ref,
            factor_ref=request.factor_ref,
            execution_ref=request.execution_ref,
            protocol_id=request.protocol_id,
            data_version=request.data_version,
            split_id=request.split_id,
            pool_refs=tuple(request.pool_refs),
            sections=(
                EvaluationSection(
                    name="predictive", status=SectionStatus.COMPLETE, facts=facts
                ),
            ),
            provenance=make_provenance(namespace=NS, data_version=request.data_version),
            engine_version="analyze-test",
        )


class _OOSExecution:
    def __init__(self, store, *, explode: bool = False) -> None:
        self._store = store
        self.explode = explode
        self.crash_process = False
        self.code_version_override: str | None = None
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        if self.crash_process:
            raise _SimulatedProcessCrash()
        if self.explode:
            raise RuntimeError("injected sealed worker crash")
        result = _ok_execution(request, self._store)
        if self.code_version_override is None:
            return result
        from skills.factor_mining.adapters.execution_identity import (
            execution_envelope_identity,
        )

        drifted = replace(
            result,
            provenance=replace(
                result.provenance, code_version=self.code_version_override
            ),
            fingerprint="d" * 64,
        )
        return replace(drifted, fingerprint=execution_envelope_identity(drifted))


class _SimulatedProcessCrash(BaseException):
    """Deliberately bypasses Controller's Exception recovery boundary."""


def _oos_factory(manifest, authorization):
    return (
        FactorComputeRequest(
            request_id=f"oos-compute-{authorization.one_shot_key}",
            namespace=manifest.provenance.namespace,
            experiment_id=authorization.one_shot_key,
            execution_id=f"oos-execution-{authorization.one_shot_key}",
            brief_ref=manifest.brief_ref,
            factor_ref=manifest.factor_ref,
            data_version=manifest.data_version,
            split_id=authorization.sealed_split_id,
            sealed_execution=True,
        ),
        EvaluationRequest(
            request_id=f"oos-evaluate-{authorization.one_shot_key}",
            namespace=manifest.provenance.namespace,
            brief_ref=manifest.brief_ref,
            factor_ref=manifest.factor_ref,
            execution_ref=None,
            protocol_id=manifest.evaluation_protocol_id,
            data_version=manifest.data_version,
            split_id=authorization.sealed_split_id,
            pool_refs=manifest.pool_baseline_refs,
        ),
    )


def _freeze_ready_run(ctrl, store, brief, brief_ref, *, run_id: str):
    run = _create_active_run(ctrl, brief_ref, run_id=run_id)
    factor_ref, _ = _persist_factor(store, brief, factor_id=f"factor-{run_id}")
    proposed = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run_id,
            aggregate_id="cand-1",
            idempotency_key="propose",
            actor_id="agent",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert proposed.ok, proposed.failure
    pipeline = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run_id,
            aggregate_id="cand-1",
            idempotency_key="pipeline",
            actor_id="agent",
            role_id="orchestrator",
            expected_version=proposed.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    assert pipeline.ok, pipeline.failure
    current = pipeline.run
    candidate = current.candidates["cand-1"]
    for role, review_id in (("methodology_critic", "review-m"), ("leakage_and_code_reviewer", "review-l")):
        review_ref, _ = _persist_review(
            store,
            report_id=f"{review_id}-{run_id}",
            role_id=role,
            factor_ref=factor_ref,
            evaluation_ref=candidate.evaluation_ref,
        )
        result = ctrl.handle(
            CommandRequest(
                command="submit_review",
                run_id=run_id,
                aggregate_id="cand-1",
                idempotency_key=review_id,
                actor_id="agent",
                role_id="orchestrator",
                expected_version=current.version,
                payload={"namespace": NS, "review_ref": to_plain_dict(review_ref)},
            )
        )
        assert result.ok, result.failure
        current = result.run
    pool_ref, _ = _persist_pool(
        store, decision_id=f"pool-{run_id}", factor_ref=factor_ref
    )
    pooled = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=run_id,
            aggregate_id="cand-1",
            idempotency_key="pool",
            actor_id="agent",
            role_id="orchestrator",
            expected_version=current.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert pooled.ok, pooled.failure
    gate1 = ctrl.handle(
        CommandRequest(
            command="record_gate1_approval",
            run_id=run_id,
            aggregate_id=run_id,
            idempotency_key="gate1",
            actor_id="human-1",
            role_id="human",
            expected_version=pooled.run.version,
            payload={
                "namespace": NS,
                "approved": True,
                "human_approval_token": "trusted-human-token",
                "candidate_id": "cand-1",
                "freeze_intent": _caller_freeze_intent(manifest_id=f"manifest-{run_id}"),
            },
        )
    )
    assert gate1.ok, gate1.failure
    requested = ctrl.handle(
        CommandRequest(
            command="request_freeze",
            run_id=run_id,
            aggregate_id="cand-1",
            idempotency_key="request-freeze",
            actor_id="agent",
            role_id="orchestrator",
            expected_version=gate1.run.version,
            payload={"namespace": NS},
        )
    )
    assert requested.ok, requested.failure
    frozen = ctrl.handle(
        CommandRequest(
            command="freeze",
            run_id=run_id,
            aggregate_id="cand-1",
            idempotency_key="freeze",
            actor_id="agent",
            role_id="orchestrator",
            expected_version=requested.run.version,
            payload={"namespace": NS},
        )
    )
    assert frozen.ok, frozen.failure
    return frozen.run


def test_phase06_frozen_selectors_use_official_native_fact_names() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(
        store,
        brief_ref,
        analyze=_OOSAnalyze(),
        execution=_OOSExecution(store),
        gate2_verifier=_gate2,
        oos_request_factory=_oos_factory,
    )
    frozen = _freeze_ready_run(ctrl, store, brief, brief_ref, run_id="oos-native")
    manifest = resolve_typed_object(store, frozen.freeze_manifest_ref)
    assert manifest.evaluation_protocol_id == "proto-1"
    assert manifest.oos_metric_selectors["min_rank_ic_ir"] == {
        "fact_name": "rank_ic_ir",
        "operator": "gte",
    }
    request = EvaluationRequest(
        request_id="native-observation",
        namespace=NS,
        brief_ref=manifest.brief_ref,
        factor_ref=manifest.factor_ref,
        execution_ref=None,
        protocol_id=manifest.evaluation_protocol_id,
        data_version=manifest.data_version,
        split_id=manifest.split_refs["sealed"],
    )
    report = _OOSAnalyze().evaluate(request)
    assert ctrl._oos_thresholds_passed(report, manifest)
    legacy_only = replace(
        report,
        sections=(
            EvaluationSection(
                name="predictive",
                status=SectionStatus.COMPLETE,
                facts=(
                    replace(
                        report.sections[0].facts[0], name="min_rank_ic_ir"
                    ),
                ),
            ),
        ),
        content_hash="",
    )
    assert not ctrl._oos_thresholds_passed(legacy_only, manifest)
    wrong_engine = replace(
        report,
        sections=(
            replace(
                report.sections[0],
                facts=(
                    replace(
                        report.sections[0].facts[0], engine_version="other-engine"
                    ),
                    *report.sections[0].facts[1:],
                ),
            ),
        ),
        content_hash="",
    )
    assert not ctrl._oos_thresholds_passed(wrong_engine, manifest)


def _gate2(payload, _request) -> None:
    assert payload["approver_id"] == "human-2"


def test_phase06_sealed_oos_promotes_once_without_event_leakage() -> None:
    store, brief, brief_ref = _brief_and_store()
    analyze = _OOSAnalyze()
    execution = _OOSExecution(store)
    ctrl, _, _ = _controller(
        store,
        brief_ref,
        analyze=analyze,
        execution=execution,
        gate2_verifier=_gate2,
        oos_request_factory=_oos_factory,
        now=lambda: "2026-08-05T00:00:00+00:00",
    )
    frozen = _freeze_ready_run(ctrl, store, brief, brief_ref, run_id="oos-pass")
    calls_before_oos = execution.calls
    auth = ctrl.handle(
        CommandRequest(
            command="authorize_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="authorize",
            actor_id="human-1",
            role_id="human",
            expected_version=frozen.version,
            payload={"namespace": NS},
        )
    )
    assert auth.ok, auth.failure
    complete = ctrl.handle(
        CommandRequest(
            command="complete_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="execute-oos",
            actor_id="trusted-worker",
            role_id="executor",
            expected_version=auth.run.version,
            payload={"namespace": NS},
        )
    )
    assert complete.ok, complete.failure
    assert complete.run.status is ResearchRunStatus.OOS_TESTED
    assert complete.run.candidates["cand-1"].status is CandidateStatus.OOS_TESTED
    assert execution.calls == calls_before_oos + 1
    assert complete.run.oos_result_ref is not None
    assert "sealed" not in str(complete.outputs)
    duplicate = ctrl.handle(
        CommandRequest(
            command="complete_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="retry-with-new-key",
            actor_id="trusted-worker",
            role_id="executor",
            payload={"namespace": NS},
        )
    )
    assert not duplicate.ok
    assert duplicate.failure.code is FailureCode.OOS_ALREADY_CONSUMED
    assert execution.calls == calls_before_oos + 1
    untrusted_ctrl, _, _ = _controller(
        store,
        brief_ref,
        analyze=_OOSAnalyze(),
        execution=_OOSExecution(store),
        oos_request_factory=_oos_factory,
    )
    self_approval = untrusted_ctrl.handle(
        CommandRequest(
            command="record_gate2_approval",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="untrusted-gate2",
            actor_id="agent-pretending-human",
            role_id="human",
            expected_version=complete.run.version,
            payload={
                "namespace": NS,
                "candidate_id": "cand-1",
                "approved": True,
                "approver_id": "agent-pretending-human",
                "signed_at": "2026-08-05T00:01:00+00:00",
                "reason": "self approved",
            },
        )
    )
    assert not self_approval.ok
    assert self_approval.failure.code is FailureCode.FORBIDDEN_INPUT
    extra_gate2_field = ctrl.handle(
        CommandRequest(
            command="record_gate2_approval",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="gate2-extra",
            actor_id="human-2",
            role_id="human",
            expected_version=complete.run.version,
            payload={
                "namespace": NS,
                "candidate_id": "cand-1",
                "approved": True,
                "approver_id": "human-2",
                "signed_at": "2026-08-05T00:01:00+00:00",
                "reason": "threshold passed",
                "unaudited_override": "forbidden",
            },
        )
    )
    assert not extra_gate2_field.ok
    assert extra_gate2_field.failure.code is FailureCode.FORBIDDEN_INPUT
    gate2 = ctrl.handle(
        CommandRequest(
            command="record_gate2_approval",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="gate2",
            actor_id="human-2",
            role_id="human",
            expected_version=complete.run.version,
            payload={
                "namespace": NS,
                "candidate_id": "cand-1",
                "approved": True,
                "approver_id": "human-2",
                "signed_at": "2026-08-05T00:01:00+00:00",
                "reason": "pre-registered threshold passed",
            },
        )
    )
    assert gate2.ok, gate2.failure
    extra_promote_field = ctrl.handle(
        CommandRequest(
            command="promote",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="promote-extra",
            actor_id="human-2",
            role_id="human",
            expected_version=gate2.run.version,
            payload={"namespace": NS, "unaudited_override": True},
        )
    )
    assert not extra_promote_field.ok
    assert extra_promote_field.failure.code is FailureCode.FORBIDDEN_INPUT
    promoted = ctrl.handle(
        CommandRequest(
            command="promote",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="promote",
            actor_id="human-2",
            role_id="human",
            expected_version=gate2.run.version,
            payload={"namespace": NS},
        )
    )
    assert promoted.ok, promoted.failure
    assert promoted.run.status is ResearchRunStatus.PROMOTED
    assert promoted.run.candidates["cand-1"].status is CandidateStatus.PROMOTED
    release_request = ctrl.build_release_report_request(
        namespace=NS, run_id=frozen.run_id, title="sealed release"
    )
    assert set(release_request.object_refs) >= {
        promoted.run.brief_ref,
        promoted.run.freeze_manifest_ref,
        promoted.run.oos_authorization_ref,
        promoted.run.oos_result_ref,
    }
    assert set(release_request.artifact_refs) >= {
        promoted.run.gate1_approval_ref,
        promoted.run.gate2_approval_ref,
        promoted.run.release_knowledge_ref,
        *promoted.run.oos_attempt_refs,
    }
    class ReportSpy:
        def __init__(self) -> None:
            self.request = None

        def render(self, request):
            self.request = request
            return store.put(
                namespace=request.namespace,
                kind="report",
                artifact_id=request.request_id,
                payload={"object_refs": [to_plain_dict(ref) for ref in request.object_refs]},
                input_refs=request.object_refs + request.artifact_refs,
            )

    report = ReportSpy()
    report_ref = report.render(release_request)
    assert report.request == release_request
    assert store.get(report_ref)["object_refs"] == [
        to_plain_dict(ref) for ref in release_request.object_refs
    ]
    release_knowledge = store.get(promoted.run.release_knowledge_ref)
    assert release_knowledge["disposition"] == "promoted"
    assert release_knowledge["oos_result_ref"] == to_plain_dict(promoted.run.oos_result_ref)


def test_phase06_claim_crash_is_consumed_and_never_reexecutes() -> None:
    store, brief, brief_ref = _brief_and_store()
    execution = _OOSExecution(store)
    ctrl, _, _ = _controller(
        store,
        brief_ref,
        analyze=_OOSAnalyze(),
        execution=execution,
        gate2_verifier=_gate2,
        oos_request_factory=_oos_factory,
        now=lambda: "2026-08-05T00:00:00+00:00",
    )
    frozen = _freeze_ready_run(ctrl, store, brief, brief_ref, run_id="oos-crash")
    calls_before_oos = execution.calls
    auth = ctrl.handle(
        CommandRequest(
            command="authorize_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="authorize",
            actor_id="human-1",
            role_id="human",
            expected_version=frozen.version,
            payload={"namespace": NS},
        )
    )
    assert auth.ok
    execution.explode = True
    failed = ctrl.handle(
        CommandRequest(
            command="complete_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="claim",
            actor_id="trusted-worker",
            role_id="executor",
            expected_version=auth.run.version,
            payload={"namespace": NS},
        )
    )
    assert not failed.ok
    assert failed.run.status is ResearchRunStatus.OOS_TESTED
    assert execution.calls == calls_before_oos + 1
    retry = ctrl.handle(
        CommandRequest(
            command="complete_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="new-idempotency-key",
            actor_id="trusted-worker",
            role_id="executor",
            payload={"namespace": NS},
        )
    )
    assert not retry.ok
    assert retry.failure.code is FailureCode.OOS_ALREADY_CONSUMED
    assert execution.calls == calls_before_oos + 1


def test_phase06_baseexception_after_started_is_restart_safe_and_consumed() -> None:
    store, brief, brief_ref = _brief_and_store()
    execution = _OOSExecution(store)
    ctrl, _, _ = _controller(
        store,
        brief_ref,
        analyze=_OOSAnalyze(),
        execution=execution,
        gate2_verifier=_gate2,
        oos_request_factory=_oos_factory,
        now=lambda: "2026-08-05T00:00:00+00:00",
    )
    frozen = _freeze_ready_run(ctrl, store, brief, brief_ref, run_id="oos-base-crash")
    auth = ctrl.handle(
        CommandRequest(
            command="authorize_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="authorize",
            actor_id="human-1",
            role_id="human",
            expected_version=frozen.version,
            payload={"namespace": NS},
        )
    )
    assert auth.ok
    execution.crash_process = True
    with pytest.raises(_SimulatedProcessCrash):
        ctrl.handle(
            CommandRequest(
                command="complete_oos",
                run_id=frozen.run_id,
                aggregate_id="cand-1",
                idempotency_key="first-worker",
                actor_id="trusted-worker",
                role_id="executor",
                expected_version=auth.run.version,
                payload={"namespace": NS},
            )
        )
    assert store.list_artifact_ids(namespace=NS, kind="oos_attempt_ledger") == [
        next(
            artifact_id
            for artifact_id in store.list_artifact_ids(
                namespace=NS, kind="oos_attempt_ledger"
            )
            if artifact_id.startswith("oos-start-")
        )
    ]
    restarted_execution = _OOSExecution(store)
    restarted, _, _ = _controller(
        store,
        brief_ref,
        analyze=_OOSAnalyze(),
        execution=restarted_execution,
        gate2_verifier=_gate2,
        oos_request_factory=_oos_factory,
        now=lambda: "2026-08-05T01:00:00+00:00",
    )
    retry = restarted.handle(
        CommandRequest(
            command="complete_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="new-worker-after-restart",
            actor_id="trusted-worker",
            role_id="executor",
            payload={"namespace": NS},
        )
    )
    assert not retry.ok
    assert retry.failure.code is FailureCode.OOS_ALREADY_CONSUMED
    assert restarted_execution.calls == 0


def test_phase06_threshold_failure_is_consumed_then_gate2_rejects_only() -> None:
    store, brief, brief_ref = _brief_and_store()
    execution = _OOSExecution(store)
    ctrl, _, _ = _controller(
        store,
        brief_ref,
        analyze=_OOSAnalyze(pass_thresholds=False),
        execution=execution,
        gate2_verifier=_gate2,
        oos_request_factory=_oos_factory,
        now=lambda: "2026-08-05T00:00:00+00:00",
    )
    frozen = _freeze_ready_run(ctrl, store, brief, brief_ref, run_id="oos-fail")
    auth = ctrl.handle(
        CommandRequest(
            command="authorize_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="authorize",
            actor_id="human-1",
            role_id="human",
            expected_version=frozen.version,
            payload={"namespace": NS},
        )
    )
    complete = ctrl.handle(
        CommandRequest(
            command="complete_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="execute",
            actor_id="trusted-worker",
            role_id="executor",
            expected_version=auth.run.version,
            payload={"namespace": NS},
        )
    )
    assert complete.ok, complete.failure
    assert complete.run.status is ResearchRunStatus.OOS_TESTED
    terminal = rebuild_dataclass(OOSAttempt, store.get(complete.run.oos_attempt_refs[-1]))
    assert terminal.status is TaskResultStatus.SUCCEEDED
    assert complete.outputs["passed"] is False
    assert complete.run.oos_result_ref is not None
    from skills.factor_mining.objects import resolve_typed_object

    result = resolve_typed_object(store, complete.run.oos_result_ref)
    assert result.passed is False
    for command, aggregate_id, payload in (
        ("revise_candidate", "child", {"namespace": NS, "parent_candidate_id": "cand-1"}),
        ("create_task", "generator-after-oos", {"namespace": NS}),
    ):
        denied = ctrl.handle(
            CommandRequest(
                command=command,
                run_id=frozen.run_id,
                aggregate_id=aggregate_id,
                idempotency_key=f"deny-{command}",
                actor_id="agent",
                role_id="generator",
                payload=payload,
            )
        )
        assert not denied.ok
        assert denied.failure.code is FailureCode.INVALID_STATE
    untrusted_gate2 = ctrl.handle(
        CommandRequest(
            command="record_gate2_approval",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="wrong-approve",
            actor_id="human-2",
            role_id="human",
            expected_version=complete.run.version,
            payload={
                "namespace": NS,
                "candidate_id": "cand-1",
                "approved": True,
                "approver_id": "human-2",
                "signed_at": "2026-08-05T00:01:00+00:00",
                "reason": "attempting to override threshold",
            },
        )
    )
    assert not untrusted_gate2.ok
    assert untrusted_gate2.failure.code is FailureCode.INVALID_STATE
    no_gate_promotion = ctrl.handle(
        CommandRequest(
            command="promote",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="promote-without-gate2",
            actor_id="human-2",
            role_id="human",
            payload={"namespace": NS},
        )
    )
    assert not no_gate_promotion.ok
    rejected_gate2 = ctrl.handle(
        CommandRequest(
            command="record_gate2_approval",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="gate2-reject",
            actor_id="human-2",
            role_id="human",
            expected_version=complete.run.version,
            payload={
                "namespace": NS,
                "candidate_id": "cand-1",
                "approved": False,
                "approver_id": "human-2",
                "signed_at": "2026-08-05T00:02:00+00:00",
                "reason": "frozen threshold missed",
            },
        )
    )
    assert rejected_gate2.ok, rejected_gate2.failure
    rejected = ctrl.handle(
        CommandRequest(
            command="reject_run",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="reject",
            actor_id="human-2",
            role_id="human",
            expected_version=rejected_gate2.run.version,
            payload={"namespace": NS},
        )
    )
    assert rejected.ok, rejected.failure
    assert rejected.run.status is ResearchRunStatus.REJECTED
    revived = ctrl.handle(
        CommandRequest(
            command="promote",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="revive",
            actor_id="human-2",
            role_id="human",
            payload={"namespace": NS},
        )
    )
    assert not revived.ok
    assert revived.failure.code is FailureCode.INVALID_STATE


def test_phase06_authorization_and_frozen_lineage_drift_fail_closed() -> None:
    store, brief, brief_ref = _brief_and_store()
    execution = _OOSExecution(store)
    ctrl, _, _ = _controller(
        store,
        brief_ref,
        analyze=_OOSAnalyze(),
        execution=execution,
        gate2_verifier=_gate2,
        oos_request_factory=_oos_factory,
    )
    active = _create_active_run(ctrl, brief_ref, run_id="not-frozen")
    not_frozen = ctrl.handle(
        CommandRequest(
            command="authorize_oos",
            run_id=active.run_id,
            aggregate_id="cand-missing",
            idempotency_key="too-early",
            actor_id="human-1",
            role_id="human",
            payload={"namespace": NS},
        )
    )
    assert not not_frozen.ok
    assert not_frozen.failure.code is FailureCode.INVALID_STATE

    frozen = _freeze_ready_run(ctrl, store, brief, brief_ref, run_id="oos-drift")
    caller_split = ctrl.handle(
        CommandRequest(
            command="authorize_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="caller-split",
            actor_id="human-1",
            role_id="human",
            payload={"namespace": NS, "sealed_split_id": "attacker-split"},
        )
    )
    assert not caller_split.ok
    assert caller_split.failure.code is FailureCode.FORBIDDEN_INPUT
    missing_gate1 = ctrl._cmd_authorize_oos(
        CommandRequest(
            command="authorize_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="no-gate1",
            actor_id="human-1",
            role_id="human",
            payload={"namespace": NS},
        ),
        replace(frozen, gate1_approval_ref=None),
    )
    assert not missing_gate1.ok
    assert missing_gate1.failure.code is FailureCode.INVALID_STATE
    manifest_drift = ctrl._cmd_authorize_oos(
        CommandRequest(
            command="authorize_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="manifest-drift",
            actor_id="human-1",
            role_id="human",
            payload={"namespace": NS},
        ),
        replace(
            frozen,
            freeze_manifest_ref=ObjectRef(
                object_type="FreezeManifest",
                object_id="other-manifest",
                content_hash="f" * 64,
                namespace=NS,
            ),
        ),
    )
    assert not manifest_drift.ok
    assert manifest_drift.failure.code is FailureCode.HASH_MISMATCH

    auth = ctrl.handle(
        CommandRequest(
            command="authorize_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="authorize",
            actor_id="human-1",
            role_id="human",
            expected_version=frozen.version,
            payload={"namespace": NS},
        )
    )
    assert auth.ok
    original = resolve_typed_object(store, auth.run.oos_authorization_ref)
    assert isinstance(original, OOSAuthorization)
    for suffix, split_id, one_shot_key in (
        ("split", "not-the-frozen-split", original.one_shot_key),
        ("key", original.sealed_split_id, "attacker-one-shot-key"),
    ):
        rogue = replace(
            original,
            authorization_id=f"rogue-{suffix}",
            sealed_split_id=split_id,
            one_shot_key=one_shot_key,
            content_hash="",
        )
        rogue_ref = put_formal_object(
            store,
            namespace=NS,
            object_type="OOSAuthorization",
            object_id=rogue.authorization_id,
            body=to_plain_dict(rogue),
            meta={"sealed": True},
        )
        denied = ctrl._cmd_complete_oos(
            CommandRequest(
                command="complete_oos",
                run_id=frozen.run_id,
                aggregate_id="cand-1",
                idempotency_key=f"rogue-{suffix}",
                actor_id="trusted-worker",
                role_id="executor",
                payload={"namespace": NS},
            ),
            replace(auth.run, oos_authorization_ref=rogue_ref),
        )
        assert not denied.ok
        assert denied.failure.code is FailureCode.HASH_MISMATCH

    execution.code_version_override = "attacker-compute-engine"
    compute_drift = ctrl.handle(
        CommandRequest(
            command="complete_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="compute-version-drift",
            actor_id="trusted-worker",
            role_id="executor",
            expected_version=auth.run.version,
            payload={"namespace": NS},
        )
    )
    assert not compute_drift.ok
    assert compute_drift.failure.code is FailureCode.HASH_MISMATCH
    assert compute_drift.run.oos_result_ref is None


def _sync_rehashed_event(event: dict) -> dict:
    """Model a powerful attacker who recomputes run/result/event hashes."""
    outputs = dict(event["outputs"])
    run = dict(outputs["run"])
    ordinary = {
        key: value for key, value in outputs.items() if key not in {"run", "command_result"}
    }
    command_result = dict(outputs["command_result"])
    command_result["outputs"] = ordinary
    command_result["run"] = {**run, "event_head_hash": None, "idempotency": {}}
    outputs["command_result"] = command_result
    event = {
        **event,
        "outputs": outputs,
        "state_after_digest": state_after_digest_from_run_payload(run),
    }
    body = {key: value for key, value in event.items() if key != "event_hash"}
    return {**body, "event_hash": hash_event_body(body)}


def test_phase06_replay_rejects_rehashed_oos_refs_and_external_object_tampering() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(
        store,
        brief_ref,
        analyze=_OOSAnalyze(),
        execution=_OOSExecution(store),
        gate2_verifier=_gate2,
        oos_request_factory=_oos_factory,
    )
    frozen = _freeze_ready_run(ctrl, store, brief, brief_ref, run_id="oos-replay")
    auth = ctrl.handle(
        CommandRequest(
            command="authorize_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="authorize",
            actor_id="human-1",
            role_id="human",
            expected_version=frozen.version,
            payload={"namespace": NS},
        )
    )
    complete = ctrl.handle(
        CommandRequest(
            command="complete_oos",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="execute",
            actor_id="trusted-worker",
            role_id="executor",
            expected_version=auth.run.version,
            payload={"namespace": NS},
        )
    )
    gate2 = ctrl.handle(
        CommandRequest(
            command="record_gate2_approval",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="gate2",
            actor_id="human-2",
            role_id="human",
            expected_version=complete.run.version,
            payload={
                "namespace": NS,
                "candidate_id": "cand-1",
                "approved": True,
                "approver_id": "human-2",
                "signed_at": "2026-08-05T00:01:00+00:00",
                "reason": "threshold passed",
            },
        )
    )
    promoted = ctrl.handle(
        CommandRequest(
            command="promote",
            run_id=frozen.run_id,
            aggregate_id="cand-1",
            idempotency_key="promote",
            actor_id="human-2",
            role_id="human",
            expected_version=gate2.run.version,
            payload={"namespace": NS},
        )
    )
    assert promoted.ok, promoted.failure
    from tests.skills.factor_mining.test_controller_phase04 import _list_run_event_payloads

    events = _list_run_event_payloads(store, run_id=frozen.run_id)
    auth_obj = resolve_typed_object(store, auth.run.oos_authorization_ref)
    rogue = replace(
        auth_obj,
        authorization_id="rehashed-rogue",
        one_shot_key="rogue-key",
        content_hash="",
    )
    rogue_ref = put_formal_object(
        store,
        namespace=NS,
        object_type="OOSAuthorization",
        object_id=rogue.authorization_id,
        body=to_plain_dict(rogue),
        meta={"sealed": True},
    )
    auth_index = next(i for i, item in enumerate(events) if item["command"] == "authorize_oos")
    forged = deepcopy(events[: auth_index + 1])
    event = dict(forged[auth_index])
    outputs = dict(event["outputs"])
    outputs["authorization_ref"] = to_plain_dict(rogue_ref)
    run = dict(outputs["run"])
    run["oos_authorization_ref"] = to_plain_dict(rogue_ref)
    outputs["run"] = run
    event["output_refs"] = [to_plain_dict(rogue_ref)]
    event["outputs"] = outputs
    forged[auth_index] = _sync_rehashed_event(event)
    with pytest.raises(ValueError, match="external authority binding failed"):
        ctrl.replay_events(namespace=NS, run_id=frozen.run_id, events=forged)

    original_result = resolve_typed_object(store, complete.run.oos_result_ref)
    complete_index = next(
        i for i, item in enumerate(events) if item["command"] == "complete_oos"
    )
    threshold_rogue = replace(
        original_result,
        result_id="rehashed-threshold-result",
        passed=not original_result.passed,
        content_hash="",
    )
    threshold_rogue_ref = put_formal_object(
        store,
        namespace=NS,
        object_type="OOSResult",
        object_id=threshold_rogue.result_id,
        body=to_plain_dict(threshold_rogue),
        meta={"sealed": True},
    )
    forged = deepcopy(events[: complete_index + 1])
    event = dict(forged[complete_index])
    outputs = dict(event["outputs"])
    outputs["oos_result_ref"] = to_plain_dict(threshold_rogue_ref)
    outputs["passed"] = threshold_rogue.passed
    run = dict(outputs["run"])
    run["oos_result_ref"] = to_plain_dict(threshold_rogue_ref)
    outputs["run"] = run
    event["output_refs"] = [
        outputs["attempt_terminal_ref"],
        to_plain_dict(threshold_rogue_ref),
    ]
    event["outputs"] = outputs
    forged[complete_index] = _sync_rehashed_event(event)
    with pytest.raises(ValueError, match="external authority binding failed"):
        ctrl.replay_events(namespace=NS, run_id=frozen.run_id, events=forged)

    rogue_result = replace(
        original_result,
        result_id="rehashed-rogue-result",
        sealed_split_id="attacker-sealed-split",
        content_hash="",
    )
    rogue_result_ref = put_formal_object(
        store,
        namespace=NS,
        object_type="OOSResult",
        object_id=rogue_result.result_id,
        body=to_plain_dict(rogue_result),
        meta={"sealed": True},
    )
    forged = deepcopy(events[: complete_index + 1])
    event = dict(forged[complete_index])
    outputs = dict(event["outputs"])
    outputs["oos_result_ref"] = to_plain_dict(rogue_result_ref)
    run = dict(outputs["run"])
    run["oos_result_ref"] = to_plain_dict(rogue_result_ref)
    outputs["run"] = run
    event["output_refs"] = [
        outputs["attempt_terminal_ref"],
        to_plain_dict(rogue_result_ref),
    ]
    event["outputs"] = outputs
    forged[complete_index] = _sync_rehashed_event(event)
    with pytest.raises(ValueError, match="external authority binding failed"):
        ctrl.replay_events(namespace=NS, run_id=frozen.run_id, events=forged)

    tamper_targets = (
        (NS, "controller_object", f"OOSAuthorization-{auth_obj.authorization_id}", "one_shot_key", "tampered"),
        (NS, "oos_attempt_ledger", complete.run.oos_attempt_refs[0].artifact_id, "one_shot_key", "tampered"),
        (NS, "controller_object", f"OOSResult-{complete.run.oos_result_ref.object_id}", "candidate_id", "tampered"),
        (NS, "gate2_approval", gate2.run.gate2_approval_ref.artifact_id, "approved", False),
        (NS, "release_knowledge", promoted.run.release_knowledge_ref.artifact_id, "disposition", "tampered"),
    )
    for namespace, kind, artifact_id, field, value in tamper_targets:
        key = (namespace, kind, artifact_id)
        original = deepcopy(store._items[key])
        target = store._items[key]["payload"]
        if kind == "controller_object":
            target = target["body"]
        target[field] = value
        with pytest.raises(ValueError, match="trusted external authority binding failed"):
            ctrl.replay_events(namespace=NS, run_id=frozen.run_id, events=events)
        store._items[key] = original
