"""Phase 04 Research Controller: transitions, spy ports, budget, isolation, freeze."""

from __future__ import annotations

import threading
from dataclasses import replace

import pytest

from skills.factor_mining.budget import (
    BudgetView,
    initial_budget_from_limits,
    release,
    reserve,
    settle,
)
from skills.factor_mining.contracts import (
    ArtifactRef,
    CandidateStatus,
    EvaluationReport,
    EvaluationRequest,
    EvaluationSection,
    FactorComputeRequest,
    FactorExecutionResult,
    FailureCode,
    FailureDetail,
    FreezeManifest,
    IndexSchema,
    ObjectRef,
    PoolDecision,
    PoolDecisionKind,
    ResearchRunStatus,
    ReviewConclusion,
    ReviewReport,
    SectionStatus,
    Severity,
    TaskLifecycleStatus,
    content_hash,
    to_plain_dict,
)
from skills.factor_mining.controller import (
    KIND_EVENT,
    KIND_OBJECT,
    KIND_STAGING,
    CommandRequest,
    ResearchController,
)
from skills.factor_mining.events import event_from_body
from skills.factor_mining.isolation import (
    VIS_SEALED,
    IsolationDenied,
    build_agent_task_view,
    is_sealed_marker,
    project_authorized_refs,
)
from skills.factor_mining.objects import (
    ObjectStoreError,
    load_formal_payload,
    put_formal_object,
)
from skills.factor_mining.policies import STOP_BUDGET_EXHAUSTED, evaluate_stop_reason
from skills.factor_mining.snapshots import (
    FreezeGateError,
    build_freeze_manifest,
    require_complete_refs,
    require_gate1_approval,
    require_pool_accept,
)
from skills.factor_mining.state import (
    CANDIDATE_TRANSITIONS,
    RUN_TRANSITIONS,
    TASK_TRANSITIONS,
    CandidateAggregate,
    IllegalTransitionError,
    RunAggregate,
    TaskAggregate,
    transition_candidate,
    transition_run,
    transition_task,
)
from tests.skills.factor_mining.builders import (
    make_brief,
    make_factor_spec,
    make_object_ref,
    make_provenance,
)
from tests.skills.factor_mining.memory_store import (
    InMemoryArtifactStore,
    InMemoryArtifactStoreError,
)

NS = "ns.demo"


def _brief_and_store():
    store = InMemoryArtifactStore()
    brief = make_brief()
    brief_ref = put_formal_object(
        store,
        namespace=NS,
        object_type="ResearchBrief",
        object_id=brief.brief_id,
        body=to_plain_dict(brief),
    )
    return store, brief, brief_ref


def _persist_factor(store, brief, **overrides):
    spec = make_factor_spec(brief, **overrides)
    # Bind brief_ref hash to the persisted ResearchBrief.
    brief_ref = ObjectRef(
        object_type="ResearchBrief",
        object_id=brief.brief_id,
        content_hash=brief.content_hash,
        namespace=NS,
    )
    if spec.brief_ref.content_hash != brief.content_hash:
        spec = replace(spec, brief_ref=brief_ref, content_hash="")
    ref = put_formal_object(
        store,
        namespace=NS,
        object_type="FactorSpec",
        object_id=spec.factor_id,
        body=to_plain_dict(spec),
    )
    return ref, spec


def _persist_review(
    store,
    *,
    report_id,
    role_id,
    factor_ref,
    evaluation_ref,
    conclusion=ReviewConclusion.PASS,
):
    report = ReviewReport(
        report_id=report_id,
        role_id=role_id,
        factor_ref=factor_ref,
        evaluation_ref=evaluation_ref,
        conclusion=conclusion,
        issues=(),
        allow_revision=True,
        requires_full_rerun=False,
        provenance=make_provenance(namespace=NS),
        rationale="ok",
    )
    return put_formal_object(
        store,
        namespace=NS,
        object_type="ReviewReport",
        object_id=report.report_id,
        body=to_plain_dict(report),
    ), report


def _persist_pool(store, *, decision_id, factor_ref, decision=PoolDecisionKind.ACCEPT):
    decision_obj = PoolDecision(
        decision_id=decision_id,
        factor_ref=factor_ref,
        decision=decision,
        incremental_evidence=(),
        residual_risks=(),
        role_id="pool_steward",
        provenance=make_provenance(namespace=NS),
        rationale="ok",
    )
    return put_formal_object(
        store,
        namespace=NS,
        object_type="PoolDecision",
        object_id=decision_obj.decision_id,
        body=to_plain_dict(decision_obj),
    ), decision_obj


def _controller(
    store,
    brief_ref,
    analyze=None,
    execution=None,
    gate1_verifier=None,
    gate2_verifier=None,
    oos_request_factory=None,
    now=None,
):
    brief = make_brief()

    class DefaultAnalyze:
        def __init__(self):
            self.calls: list[str] = []

        def preflight(self, request):
            self.calls.append("preflight")
            return _ok_report(request, "pre")

        def evaluate(self, request):
            self.calls.append("evaluate")
            return _ok_report(request, "eval")

        def compare_to_pool(self, request):
            self.calls.append("compare_to_pool")
            return _ok_report(request, "cmp")

    class DefaultExec:
        def __init__(self):
            self.calls: list[str] = []

        def execute(self, request):
            self.calls.append("execute")
            return _ok_execution(request, store)

    def _trusted_gate1(payload, request):
        if payload.get("human_approval_token") != "trusted-human-token":
            raise IsolationDenied(
                FailureDetail(
                    code=FailureCode.FORBIDDEN_INPUT,
                    message="Gate-1 agent self-approval rejected",
                    details={"role_id": request.role_id},
                )
            )

    an = analyze or DefaultAnalyze()
    ex = execution or DefaultExec()
    return ResearchController(
        store=store,
        analyze=an,
        execution=ex,
        resolve_brief=lambda _ref: brief,
        capability_check=lambda _role, _cap: True,
        gate1_verifier=gate1_verifier or _trusted_gate1,
        gate2_verifier=gate2_verifier,
        oos_request_factory=oos_request_factory,
        now=now,
    ), an, ex


def _ok_report(request: EvaluationRequest, tag: str) -> EvaluationReport:
    return EvaluationReport(
        report_id=f"rep-{tag}-{request.request_id}",
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
                name="data_quality",
                status=SectionStatus.COMPLETE,
                checks=(),
            ),
        ),
        provenance=make_provenance(
            namespace=request.namespace, data_version=request.data_version
        ),
        engine_version="analyze-test",
    )


def _hard_report(request: EvaluationRequest, tag: str) -> EvaluationReport:
    return EvaluationReport(
        report_id=f"rep-{tag}-{request.request_id}",
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
                name="formula_safety",
                status=SectionStatus.FAILED,
                checks=(),
            ),
        ),
        provenance=make_provenance(
            namespace=request.namespace, data_version=request.data_version
        ),
        engine_version="analyze-test",
        failure=FailureDetail(
            code=FailureCode.FORBIDDEN_INPUT,
            message="hard fail",
            severity=Severity.HARD_FAIL,
        ),
    )


def _caller_freeze_intent(
    *,
    manifest_id: str = "fm-1",
    outlier_policy: str = "none",
    neutralization_policy: str = "none",
    pool_baseline_refs: tuple = (),
) -> dict:
    """Gate-1 caller-only freeze fields; engines/holding/oos are derived by controller."""
    return {
        "manifest_id": manifest_id,
        "outlier_policy": outlier_policy,
        "neutralization_policy": neutralization_policy,
        "pool_baseline_refs": [to_plain_dict(r) for r in pool_baseline_refs],
    }


def _list_run_event_payloads(store, *, run_id: str) -> list[dict]:
    """Public-API event listing (no store._items)."""
    events = []
    for aid in store.list_artifact_ids(namespace=NS, kind=KIND_EVENT):
        if not str(aid).startswith(f"{run_id}-"):
            continue
        # get_by_identity returns the store payload (the event mapping itself).
        payload = store.get_by_identity(
            namespace=NS, kind=KIND_EVENT, artifact_id=str(aid)
        )
        events.append(dict(payload))
    events.sort(key=lambda e: int(e["sequence"]))
    return events


def _ok_execution(request: FactorComputeRequest, store) -> FactorExecutionResult:
    from skills.factor_mining.adapters.execution_identity import (
        execution_envelope_identity_from_parts,
    )

    # Series content hashes (canonical decoded payload) vs ArtifactRef envelope hashes.
    values_series_hash = "a" * 64
    mask_series_hash = "b" * 64
    values_ref = store.put(
        namespace=request.namespace,
        kind="factor_values",
        artifact_id=f"values-{request.execution_id}",
        payload={"stub": True, "series_content_hash": values_series_hash},
    )
    mask_ref = store.put(
        namespace=request.namespace,
        kind="valid_mask",
        artifact_id=f"mask-{request.execution_id}",
        payload={"stub": True, "series_content_hash": mask_series_hash},
    )
    assert values_ref.content_hash != values_series_hash
    assert mask_ref.content_hash != mask_series_hash
    index_schema = IndexSchema(
        names=("symbol", "eob"),
        symbol_level="symbol",
        datetime_level="eob",
        level_order=(0, 1),
        timezone="Asia/Shanghai",
    )
    provenance = make_provenance(
        namespace=request.namespace, data_version=request.data_version
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
        failure=None,
    )


def _create_active_run(ctrl, brief_ref, run_id="run-1"):
    r1 = ctrl.handle(
        CommandRequest(
            command="create_run",
            run_id=run_id,
            aggregate_id=run_id,
            idempotency_key="create-1",
            actor_id="actor",
            role_id="orchestrator",
            payload={"namespace": NS, "brief_ref": to_plain_dict(brief_ref)},
        )
    )
    assert r1.ok and r1.run is not None
    r2 = ctrl.handle(
        CommandRequest(
            command="activate",
            run_id=run_id,
            aggregate_id=run_id,
            idempotency_key="act-1",
            actor_id="actor",
            role_id="orchestrator",
            expected_version=r1.run.version,
            payload={"namespace": NS},
        )
    )
    assert r2.ok and r2.run is not None
    return r2.run


# --------------------------------------------------------------------------- state tables
@pytest.mark.parametrize(
    ("frm", "command", "to"),
    [(frm, cmd, to) for (frm, cmd), to in RUN_TRANSITIONS.items()],
)
def test_phase04_run_transition_table(frm, command, to) -> None:
    assert transition_run(frm, command) is to


@pytest.mark.parametrize(
    ("frm", "command"),
    [
        (ResearchRunStatus.BRIEFED, "freeze"),
        (ResearchRunStatus.FROZEN, "activate"),
        (ResearchRunStatus.REJECTED, "activate"),
    ],
)
def test_phase04_illegal_run_transitions(frm, command) -> None:
    with pytest.raises(IllegalTransitionError):
        transition_run(frm, command)


@pytest.mark.parametrize(
    ("frm", "command", "to"),
    [(frm, cmd, to) for (frm, cmd), to in CANDIDATE_TRANSITIONS.items()],
)
def test_phase04_candidate_transition_table(frm, command, to) -> None:
    assert transition_candidate(frm, command) is to


@pytest.mark.parametrize(
    ("frm", "command"),
    [
        (CandidateStatus.PROPOSED, "evaluate"),
        (CandidateStatus.REJECTED, "preflight_pass"),
        (CandidateStatus.FROZEN, "reject"),
    ],
)
def test_phase04_illegal_candidate_transitions(frm, command) -> None:
    with pytest.raises(IllegalTransitionError):
        transition_candidate(frm, command)


@pytest.mark.parametrize(
    ("frm", "command", "to"),
    [(frm, cmd, to) for (frm, cmd), to in TASK_TRANSITIONS.items()],
)
def test_phase04_task_transition_table(frm, command, to) -> None:
    assert transition_task(frm, command) is to


def test_phase04_revision_lineage_starts_proposed() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref)
    factor_ref, spec = _persist_factor(store, brief)
    p = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="prop-1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert p.ok
    child_ref, child_spec = _persist_factor(
        store, brief, factor_id="cand-2", revision=2, parent_ref=factor_ref
    )
    rev = ctrl.handle(
        CommandRequest(
            command="revise_candidate",
            run_id=run.run_id,
            aggregate_id="cand-2",
            idempotency_key="rev-1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=p.run.version,
            payload={
                "namespace": NS,
                "parent_candidate_id": "cand-1",
                "factor_ref": to_plain_dict(child_ref),
            },
        )
    )
    assert rev.ok
    child = rev.run.candidates["cand-2"]
    assert child.status is CandidateStatus.PROPOSED
    assert child.parent_ref is not None
    assert child.revision == 2



# --------------------------------------------------------------------------- spy / short-circuit
def test_phase04_pipeline_spy_order_and_hard_fail_short_circuit() -> None:
    store, brief, brief_ref = _brief_and_store()

    class SpyAnalyze:
        def __init__(self):
            self.calls: list[str] = []
            self.fail_at: str | None = "preflight"

        def preflight(self, request):
            self.calls.append("preflight")
            if self.fail_at == "preflight":
                return _hard_report(request, "pre")
            return _ok_report(request, "pre")

        def evaluate(self, request):
            self.calls.append("evaluate")
            if self.fail_at == "evaluate":
                return _hard_report(request, "eval")
            return _ok_report(request, "eval")

        def compare_to_pool(self, request):
            self.calls.append("compare_to_pool")
            return _ok_report(request, "cmp")

    class SpyExec:
        def __init__(self):
            self.calls: list[str] = []

        def execute(self, request):
            self.calls.append("execute")
            return _ok_execution(request, store)

    analyze = SpyAnalyze()
    execution = SpyExec()
    ctrl, _, _ = _controller(store, brief_ref, analyze=analyze, execution=execution)
    run = _create_active_run(ctrl, brief_ref)
    factor_ref, spec = _persist_factor(store, brief)
    p = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="prop-1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert p.ok
    eval_req = EvaluationRequest(
        request_id="e1",
        namespace=NS,
        brief_ref=brief_ref,
        factor_ref=factor_ref,
        execution_ref=None,
        protocol_id="proto-1",
        data_version="data-v1",
        split_id="train",
    )
    compute_req = FactorComputeRequest(
        request_id="c1",
        namespace=NS,
        experiment_id="exp-1",
        execution_id="exec-1",
        brief_ref=brief_ref,
        factor_ref=factor_ref,
        data_version="data-v1",
        split_id="train",
    )
    failed = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe-fail",
            actor_id="a",
            role_id="orchestrator",
            expected_version=p.run.version,
            payload={
                "namespace": NS,
                "evaluation_request": eval_req,
                "compute_request": compute_req,
            },
        )
    )
    assert failed.ok is False
    assert analyze.calls == ["preflight"]
    assert execution.calls == []
    assert failed.run.candidates["cand-1"].status is CandidateStatus.REJECTED

    # Success path order.
    store2, brief2, brief_ref2 = _brief_and_store()
    analyze2 = SpyAnalyze()
    analyze2.fail_at = None
    execution2 = SpyExec()
    ctrl2, _, _ = _controller(store2, brief_ref2, analyze=analyze2, execution=execution2)
    run2 = _create_active_run(ctrl2, brief_ref2, run_id="run-2")
    factor_ref2, _ = _persist_factor(store2, brief2, factor_id=spec.factor_id)
    p2 = ctrl2.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run2.run_id,
            aggregate_id="cand-ok",
            idempotency_key="prop-ok",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run2.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref2)},
        )
    )
    assert p2.ok, p2.failure
    eval_req2 = replace(eval_req, brief_ref=brief_ref2, factor_ref=factor_ref2)
    compute_req2 = replace(compute_req, brief_ref=brief_ref2, factor_ref=factor_ref2)
    ok = ctrl2.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run2.run_id,
            aggregate_id="cand-ok",
            idempotency_key="pipe-ok",
            actor_id="a",
            role_id="orchestrator",
            expected_version=p2.run.version,
            payload={
                "namespace": NS,
                "evaluation_request": eval_req2,
                "compute_request": compute_req2,
            },
        )
    )
    assert ok.ok, ok.failure
    assert analyze2.calls == ["preflight", "evaluate", "compare_to_pool"]
    assert execution2.calls == ["execute"]
    assert ok.outputs["calls"] == ["preflight", "execute", "evaluate", "compare_to_pool"]
    assert ok.run.candidates["cand-ok"].status is CandidateStatus.REVIEW_PENDING


# --------------------------------------------------------------------------- idempotency / budget / concurrency
def test_phase04_idempotency_exactly_once_no_double_port_or_budget() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, analyze, execution = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref)
    factor_ref, _spec = _persist_factor(store, brief, factor_id="f1")
    p = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="same-key",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert p.ok
    remaining_after = p.run.budget_remaining["candidates"]
    puts_after = store.put_calls
    again = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="same-key",
            actor_id="a",
            role_id="orchestrator",
            expected_version=0,  # ignored on idempotent replay
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert again.replayed is True
    assert again.run.budget_remaining["candidates"] == remaining_after
    assert store.put_calls == puts_after


def test_phase04_expected_version_conflict() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref)
    bad = ctrl.handle(
        CommandRequest(
            command="activate",
            run_id=run.run_id,
            aggregate_id=run.run_id,
            idempotency_key="dup-act",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version - 1,
            payload={"namespace": NS},
        )
    )
    assert bad.ok is False
    assert bad.failure.code is FailureCode.INVALID_STATE


def test_phase04_budget_reserve_settle_release_and_exhaustion() -> None:
    view = initial_budget_from_limits(
        {"candidates": 1, "experiments": 1, "revisions": 1, "debate_rounds": 1}
    )
    reserved = reserve(view, reservation_id="r1", amounts={"candidates": 1})
    assert isinstance(reserved, BudgetView)
    assert reserved.remaining["candidates"] == 0
    exceeded = reserve(reserved, reservation_id="r2", amounts={"candidates": 1})
    assert isinstance(exceeded, FailureDetail)
    assert exceeded.code is FailureCode.BUDGET_EXCEEDED
    released = release(reserved, reservation_id="r1")
    assert isinstance(released, BudgetView)
    assert released.remaining["candidates"] == 1
    reserved2 = reserve(released, reservation_id="r3", amounts={"experiments": 1})
    settled = settle(reserved2, reservation_id="r3")
    assert isinstance(settled, BudgetView)
    assert "r3" not in settled.reservations
    assert settled.remaining["experiments"] == 0


def test_phase04_stop_policy_budget_exhausted() -> None:
    run = RunAggregate(
        run_id="r",
        namespace=NS,
        brief_ref=make_object_ref(namespace=NS),
        status=ResearchRunStatus.ACTIVE,
        budget_limits={"candidates": 1, "experiments": 0, "revisions": 0, "debate_rounds": 0},
        budget_remaining={"candidates": 0, "experiments": 0, "revisions": 0, "debate_rounds": 0},
    )
    assert evaluate_stop_reason(run) == STOP_BUDGET_EXHAUSTED


# --------------------------------------------------------------------------- isolation
def test_phase04_isolation_rejects_sealed_refs_and_visibility() -> None:
    run = RunAggregate(
        run_id="r",
        namespace=NS,
        brief_ref=make_object_ref(namespace=NS),
        status=ResearchRunStatus.ACTIVE,
    )
    task = TaskAggregate(
        task_id="t1",
        run_id="r",
        role_id="worker",
        status=TaskLifecycleStatus.PENDING,
    )
    sealed_ref = make_object_ref(
        object_type="OOSResult", object_id="oos-1", content_hash="f" * 64, namespace=NS
    )
    assert is_sealed_marker(to_plain_dict(sealed_ref))
    with pytest.raises(IsolationDenied):
        project_authorized_refs(
            namespace=NS, refs=(sealed_ref,), visibility=("train", "validation")
        )
    with pytest.raises(IsolationDenied):
        build_agent_task_view(
            run=run,
            task=task,
            goal="g",
            input_refs=(make_object_ref(namespace=NS),),
            expected_output_type="ResearchDecision",
            lease_id="lease-1",
            visibility=(VIS_SEALED,),
        )
    other_ns = make_object_ref(namespace="other.ns")
    with pytest.raises(IsolationDenied):
        project_authorized_refs(
            namespace=NS, refs=(other_ns,), visibility=("train",)
        )


def test_phase04_build_task_view_audits_sealed_denial() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref)
    created = ctrl.handle(
        CommandRequest(
            command="create_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="ct-1",
            actor_id="a",
            role_id="worker",
            expected_version=run.version,
            payload={"namespace": NS},
        )
    )
    assert created.ok
    sealed_body = {
        "result_id": "oos-1",
        "sealed": True,
        "split_id": "sealed-oos",
        "content_hash": "",
    }
    # content_hash required by put_formal_object
    from skills.factor_mining.contracts import content_hash as _ch
    sealed_body["content_hash"] = _ch({k: v for k, v in sealed_body.items() if k != "content_hash"})
    sealed = put_formal_object(
        store,
        namespace=NS,
        object_type="OOSResult",
        object_id="oos-1",
        body=sealed_body,
        meta={"sealed": True},
    )
    denied = ctrl.handle(
        CommandRequest(
            command="build_task_view",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="view-1",
            actor_id="a",
            role_id="worker",
            expected_version=created.run.version,
            payload={
                "namespace": NS,
                "input_refs": [to_plain_dict(sealed)],
                "goal": "inspect",
                "expected_output_type": "ResearchDecision",
            },
        )
    )
    assert denied.ok is False
    assert denied.failure is not None
    assert denied.failure.code is FailureCode.FORBIDDEN_INPUT
    assert denied.event is not None
    assert denied.event.result_status == "denied"


# --------------------------------------------------------------------------- fault injection / hash tamper / freeze / replay
def test_phase04_event_append_failure_no_half_migration() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref)
    version_before = run.version
    store.fail_kind = "controller_event"
    bad = ctrl.handle(
        CommandRequest(
            command="stop",
            run_id=run.run_id,
            aggregate_id=run.run_id,
            idempotency_key="stop-fail",
            actor_id="a",
            role_id="orchestrator",
            expected_version=version_before,
            payload={"namespace": NS, "reason": "human_terminated"},
        )
    )
    assert bad.ok is False
    assert bad.failure.code is FailureCode.RECOVERY_REQUIRED
    reloaded = ctrl.load_run(namespace=NS, run_id=run.run_id)
    assert reloaded is not None
    assert reloaded.version == version_before
    assert reloaded.status is ResearchRunStatus.ACTIVE


def test_phase04_hash_tamper_detected_on_get() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref)
    # Snapshot was written; tamper payload via public test-double API.
    store.tamper(namespace=NS, kind="controller_snapshot", artifact_id=run.run_id)
    from skills.factor_mining.contracts import ArtifactRef

    old_hash = "0" * 64
    with pytest.raises(ValueError):
        store.get(
            ArtifactRef(
                kind="controller_snapshot",
                artifact_id=run.run_id,
                namespace=NS,
                content_hash=old_hash,
            )
        )
    # Tampered body is still listed; wrong hash fails closed on get.
    assert run.run_id in store.list_artifact_ids(
        namespace=NS, kind="controller_snapshot"
    )


def test_phase04_freeze_requires_gate1_pool_and_refs() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref)
    factor_ref, _spec = _persist_factor(store, brief, factor_id="f1")
    cand = CandidateAggregate(
        candidate_id="cand-1",
        factor_ref=factor_ref,
        status=CandidateStatus.FREEZE_READY,
        evaluation_ref=None,
        review_refs=(),
        pool_decision_ref=None,
    )
    with pytest.raises(FreezeGateError):
        require_complete_refs(cand)
    with pytest.raises(FreezeGateError):
        require_gate1_approval(run, store_get=store.get)

    # Happy path pieces.
    eval_ref = make_object_ref(
        object_type="EvaluationReport", object_id="ev1", content_hash="b" * 64, namespace=NS
    )
    review_ref = make_object_ref(
        object_type="ReviewReport", object_id="rv1", content_hash="c" * 64, namespace=NS
    )
    decision_payload = {
        "decision_id": "pd-1",
        "decision": PoolDecisionKind.ACCEPT.value,
        "factor_ref": to_plain_dict(factor_ref),
        "role_id": "worker",
    }
    pd_art = store.put(
        namespace=NS,
        kind="controller_object",
        artifact_id="PoolDecision-pd-1",
        payload={
            "object_type": "PoolDecision",
            "object_id": "pd-1",
            "body": decision_payload,
        },
    )
    pool_ref = ObjectRef(
        object_type="PoolDecision",
        object_id="pd-1",
        content_hash=pd_art.content_hash,
        namespace=NS,
    )
    cand2 = replace(
        cand,
        preflight_ref=make_object_ref(
            object_type="EvaluationReport", object_id="pre1", content_hash="a" * 64, namespace=NS
        ),
        execution_ref=make_object_ref(
            object_type="FactorExecutionResult",
            object_id="ex1",
            content_hash="b" * 64,
            namespace=NS,
        ),
        evaluation_ref=eval_ref,
        compare_ref=make_object_ref(
            object_type="EvaluationReport", object_id="cmp1", content_hash="c" * 64, namespace=NS
        ),
        review_refs=(review_ref,),
        pool_decision_ref=pool_ref,
    )
    require_complete_refs(cand2)
    require_pool_accept(candidate=cand2, store_get=lambda ref: store.get_unchecked(
        namespace=ref.namespace,
        kind="controller_object",
        artifact_id=f"{ref.object_type}-{ref.object_id}",
    )["body"])

    # Controller Gate-1 requires exact candidate_id (fail closed).
    missing_id = ctrl.handle(
        CommandRequest(
            command="record_gate1_approval",
            run_id=run.run_id,
            aggregate_id=run.run_id,
            idempotency_key="g1-missing",
            actor_id="human",
            role_id="human",
            expected_version=run.version,
            payload={
                "namespace": NS,
                "approved": True,
                "human_approval_token": "trusted-human-token",
            },
        )
    )
    assert missing_id.ok is False
    assert missing_id.failure is not None
    assert missing_id.failure.code is FailureCode.INVALID_PARAMETERS

    # Persist Gate-1 approval artifact for require_gate1_approval / manifest hashing.
    gate_put = store.put_if_absent(
        namespace=NS,
        kind="gate1_approval",
        artifact_id=f"{run.run_id}-cand-1-g1",
        payload={
            "approved": True,
            "run_id": run.run_id,
            "candidate_id": "cand-1",
            "human_approval_token": "trusted-human-token",
            "namespace": NS,
        },
    )
    run_with_gate = replace(run, gate1_approval_ref=gate_put.ref)
    approval = require_gate1_approval(run_with_gate, store_get=store.get)
    manifest = build_freeze_manifest(
        manifest_id="fm-1",
        run=run_with_gate,
        candidate=cand2,
        brief=brief,
        approval_ref=approval,
        compute_engine_version="compute@1",
        analyze_engine_version="analyze@1",
        evaluation_protocol_id="proto-1",
        direction="long_high",
        params={"period": 20},
        missing_policy="keep_nan",
        adjustment_policy="post",
        outlier_policy="none",
        neutralization_policy="none",
        holding_horizon_bars=5,
        rebalance="weekly",
        cost=brief.cost,
        pool_baseline_refs=(),
        oos_thresholds={"min_rank_ic_ir": 0.2},
        oos_metric_selectors={
            "min_rank_ic_ir": {"fact_name": "rank_ic_ir", "operator": "gte"}
        },
        provenance=brief.provenance,
    )
    assert manifest.content_hash
    # Input change changes hash.
    manifest2 = build_freeze_manifest(
        manifest_id="fm-1",
        run=run_with_gate,
        candidate=cand2,
        brief=brief,
        approval_ref=approval,
        compute_engine_version="compute@1",
        analyze_engine_version="analyze@1",
        evaluation_protocol_id="proto-1",
        direction="long_high",
        params={"period": 21},
        missing_policy="keep_nan",
        adjustment_policy="post",
        outlier_policy="none",
        neutralization_policy="none",
        holding_horizon_bars=5,
        rebalance="weekly",
        cost=brief.cost,
        pool_baseline_refs=(),
        oos_thresholds={"min_rank_ic_ir": 0.2},
        oos_metric_selectors={
            "min_rank_ic_ir": {"fact_name": "rank_ic_ir", "operator": "gte"}
        },
        provenance=brief.provenance,
    )
    assert manifest.content_hash != manifest2.content_hash


def test_phase04_replay_event_chain_recovers_state() -> None:
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref)
    events = _list_run_event_payloads(store, run_id=run.run_id)
    assert events
    rebuilt = ctrl.replay_events(namespace=NS, run_id=run.run_id, events=events)
    assert rebuilt.status is ResearchRunStatus.ACTIVE
    assert rebuilt.run_id == run.run_id
    # Tampered chain fails.
    bad = list(events)
    bad[0] = dict(bad[0])
    bad[0]["event_hash"] = "0" * 64
    with pytest.raises(ValueError, match="event hash mismatch"):
        ctrl.replay_events(namespace=NS, run_id=run.run_id, events=bad)


# --------------------------------------------------------------------------- root counterexamples (P0/P1)


def _pipeline_payload(brief_ref, factor_ref, *, eval_factor=None, compute_factor=None):
    fr = eval_factor or factor_ref
    cfr = compute_factor or factor_ref
    eval_req = EvaluationRequest(
        request_id="e1",
        namespace=NS,
        brief_ref=brief_ref,
        factor_ref=fr,
        execution_ref=None,
        protocol_id="proto-1",
        data_version="data-v1",
        split_id="train",
    )
    compute_req = FactorComputeRequest(
        request_id="c1",
        namespace=NS,
        experiment_id="exp-1",
        execution_id="exec-1",
        brief_ref=brief_ref,
        factor_ref=cfr,
        data_version="data-v1",
        split_id="train",
    )
    return {
        "namespace": NS,
        "evaluation_request": eval_req,
        "compute_request": compute_req,
    }


def test_phase04_p0_concurrent_cas_only_one_research_action() -> None:
    """P0-1: two controllers, same expected_version; only one research port action."""
    store, brief, brief_ref = _brief_and_store()
    results: list = []

    class CountingAnalyze:
        def __init__(self):
            self.calls: list[str] = []
            self._lock = threading.Lock()

        def preflight(self, request):
            with self._lock:
                self.calls.append("preflight")
            return _ok_report(request, "pre")

        def evaluate(self, request):
            with self._lock:
                self.calls.append("evaluate")
            return _ok_report(request, "eval")

        def compare_to_pool(self, request):
            with self._lock:
                self.calls.append("compare_to_pool")
            return _ok_report(request, "cmp")

    class CountingExec:
        def __init__(self):
            self.calls: list[str] = []
            self._lock = threading.Lock()

        def execute(self, request):
            with self._lock:
                self.calls.append("execute")
            return _ok_execution(request, store)

    analyze = CountingAnalyze()
    execution = CountingExec()
    ctrl_a, _, _ = _controller(store, brief_ref, analyze=analyze, execution=execution)
    ctrl_b, _, _ = _controller(store, brief_ref, analyze=analyze, execution=execution)
    run = _create_active_run(ctrl_a, brief_ref, run_id="cas-run")
    factor_ref, _spec = _persist_factor(store, brief, factor_id="f1")
    prop = ctrl_a.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="prop",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert prop.ok
    expected = prop.run.version
    payload = _pipeline_payload(brief_ref, factor_ref)
    start_barrier = threading.Barrier(2)

    def worker_sync(ctrl, key: str) -> None:
        start_barrier.wait(timeout=5)
        results.append(
            ctrl.handle(
                CommandRequest(
                    command="run_candidate_pipeline",
                    run_id=run.run_id,
                    aggregate_id="cand-1",
                    idempotency_key=key,
                    actor_id="a",
                    role_id="orchestrator",
                    expected_version=expected,
                    payload=payload,
                )
            )
        )

    t1 = threading.Thread(target=worker_sync, args=(ctrl_a, "pipe-a"))
    t2 = threading.Thread(target=worker_sync, args=(ctrl_b, "pipe-b"))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert len(results) == 2
    ok_count = sum(1 for r in results if r.ok)
    assert ok_count == 1, [(r.ok, getattr(r.failure, "message", None)) for r in results]
    assert analyze.calls.count("preflight") == 1
    assert execution.calls.count("execute") == 1
    events = _list_run_event_payloads(store, run_id="cas-run")
    seqs = [e["sequence"] for e in events]
    assert len(seqs) == len(set(seqs))


def test_phase04_p0_recovery_required_retry_does_not_recall_ports() -> None:
    """P0-2: port exception → same idempotency key retry does not re-call ports."""
    store, brief, brief_ref = _brief_and_store()

    class BoomAnalyze:
        def __init__(self):
            self.calls = 0

        def preflight(self, request):
            self.calls += 1
            raise RuntimeError("boom")

        def evaluate(self, request):
            raise AssertionError("should not evaluate")

        def compare_to_pool(self, request):
            raise AssertionError("should not compare")

    analyze = BoomAnalyze()
    ctrl, _, _ = _controller(store, brief_ref, analyze=analyze)
    run = _create_active_run(ctrl, brief_ref, run_id="rec-run")
    factor_ref, _spec = _persist_factor(store, brief, factor_id="f1")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="prop",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    payload = _pipeline_payload(brief_ref, factor_ref)
    first = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe-same",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=payload,
        )
    )
    assert first.ok is False
    assert first.failure.code is FailureCode.RECOVERY_REQUIRED
    assert analyze.calls == 1
    second = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe-same",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=payload,
        )
    )
    assert second.ok is False
    assert second.failure.code is FailureCode.RECOVERY_REQUIRED
    assert second.replayed is True
    assert analyze.calls == 1
    # Unrelated command must not be CAS-poisoned.
    loaded = ctrl.load_run(namespace=NS, run_id="rec-run")
    assert loaded is not None
    factor2, _ = _persist_factor(store, brief, factor_id="f2")
    other = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-2",
            idempotency_key="prop-2",
            actor_id="a",
            role_id="orchestrator",
            expected_version=loaded.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor2)},
        )
    )
    assert other.ok is True, other.failure
    assert analyze.calls == 1


def test_phase04_p0_lineage_mismatch_fails_before_ports() -> None:
    """P0-3: candidate A with compute/eval FactorSpec B fails before ports."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, analyze, execution = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="lin-run")
    factor_a, _sa = _persist_factor(store, brief, factor_id="fa")
    factor_b, _sb = _persist_factor(store, brief, factor_id="fb")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="prop",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_a)},
        )
    )
    bad = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe-bad",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=_pipeline_payload(
                brief_ref, factor_a, eval_factor=factor_b, compute_factor=factor_b
            ),
        )
    )
    assert bad.ok is False
    assert bad.failure.code is FailureCode.HASH_MISMATCH
    assert analyze.calls == []
    assert execution.calls == []


def test_phase04_p0_replay_exact_equality_and_rejects_tamper() -> None:
    """P0-4: replay exact head/idempotency/budget; wrong ns/run/gap/tamper rejected."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="rep-run")
    events = _list_run_event_payloads(store, run_id="rep-run")
    rebuilt = ctrl.replay_events(namespace=NS, run_id=run.run_id, events=events)
    assert rebuilt.version == run.version
    assert rebuilt.event_head_seq == run.event_head_seq
    assert rebuilt.event_head_hash == run.event_head_hash
    assert to_plain_dict(rebuilt.idempotency) == to_plain_dict(run.idempotency)
    assert dict(rebuilt.budget_remaining) == dict(run.budget_remaining)
    assert rebuilt.snapshot_hash() == run.snapshot_hash()

    # ControllerEvent.compute_hash exact
    raw = events[-1]
    body = {k: v for k, v in raw.items() if k != "event_hash"}
    event = event_from_body(body, event_hash=raw["event_hash"])
    assert event.compute_hash() == raw["event_hash"]

    # Tampered chain / wrong namespace / run / sequence gap.
    with pytest.raises(ValueError, match="namespace"):
        ctrl.replay_events(namespace="other.ns", run_id=run.run_id, events=events)
    with pytest.raises(ValueError, match="run_id"):
        ctrl.replay_events(namespace=NS, run_id="other-run", events=events)
    if len(events) >= 2:
        gapped = [events[0], dict(events[1])]
        gapped[1]["sequence"] = 99
        with pytest.raises(ValueError, match="sequence"):
            ctrl.replay_events(namespace=NS, run_id=run.run_id, events=gapped)
    tampered = list(events)
    tampered[0] = dict(tampered[0])
    tampered[0]["actor_id"] = "tampered"
    with pytest.raises(ValueError, match="event hash"):
        ctrl.replay_events(namespace=NS, run_id=run.run_id, events=tampered)


def test_phase04_p0_append_only_overwrite_rejected_and_create_run_replay() -> None:
    """P0-5: divergent put_if_absent rejected; create_run second call replayed."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    first = ctrl.handle(
        CommandRequest(
            command="create_run",
            run_id="cr-run",
            aggregate_id="cr-run",
            idempotency_key="create-1",
            actor_id="a",
            role_id="orchestrator",
            payload={"namespace": NS, "brief_ref": to_plain_dict(brief_ref)},
        )
    )
    assert first.ok and first.replayed is False
    second = ctrl.handle(
        CommandRequest(
            command="create_run",
            run_id="cr-run",
            aggregate_id="cr-run",
            idempotency_key="create-1",
            actor_id="a",
            role_id="orchestrator",
            payload={"namespace": NS, "brief_ref": to_plain_dict(brief_ref)},
        )
    )
    assert second.ok and second.replayed is True
    # Divergent overwrite of same event id rejected.
    with pytest.raises(InMemoryArtifactStoreError) as excinfo:
        store.put_if_absent(
            namespace=NS,
            kind=KIND_EVENT,
            artifact_id="cr-run-00000001",
            payload={"different": True},
        )
    assert excinfo.value.code is FailureCode.DUPLICATE_LOGICAL_KEY


def test_phase04_p0_cross_namespace_and_sealed_candidate_ref_rejected() -> None:
    """P0-6: cross-namespace / sealed-disguised candidate_ref rejected with audit event."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="iso-run")
    task = ctrl.handle(
        CommandRequest(
            command="create_task",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="t1",
            actor_id="a",
            role_id="generator",
            expected_version=run.version,
            payload={"namespace": NS, "visibility": ["brief", "factor"]},
        )
    )
    assert task.ok
    foreign = make_object_ref(
        object_type="FactorSpec",
        object_id="x",
        content_hash="c" * 64,
        namespace="other.namespace",
    )
    denied = ctrl.handle(
        CommandRequest(
            command="build_task_view",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="view-1",
            actor_id="a",
            role_id="generator",
            expected_version=task.run.version,
            payload={
                "namespace": NS,
                "goal": "g",
                "candidate_ref": to_plain_dict(foreign),
                "input_refs": [],
            },
        )
    )
    assert denied.ok is False
    assert denied.failure.code is FailureCode.INVALID_REFERENCE
    assert denied.event is not None
    assert denied.event.result_status == "denied"

    # Sealed via trusted store meta (not just name heuristic).
    sealed_body = {"report_id": "sealed-disguise", "sealed": True, "split_id": "sealed-x", "content_hash": ""}
    sealed_body["content_hash"] = content_hash(
        {k: v for k, v in sealed_body.items() if k != "content_hash"}
    )
    sealed_ref = put_formal_object(
        store,
        namespace=NS,
        object_type="EvaluationReport",
        object_id="sealed-disguise",
        body=sealed_body,
        meta={"sealed": True},
    )
    denied2 = ctrl.handle(
        CommandRequest(
            command="build_task_view",
            run_id=run.run_id,
            aggregate_id="task-1",
            idempotency_key="view-2",
            actor_id="a",
            role_id="generator",
            expected_version=denied.run.version if denied.run else task.run.version,
            payload={
                "namespace": NS,
                "goal": "g",
                "candidate_ref": to_plain_dict(sealed_ref),
                "input_refs": [],
            },
        )
    )
    assert denied2.ok is False
    assert denied2.failure.code is FailureCode.FORBIDDEN_INPUT


def test_phase04_p0_agent_self_gate1_rejected() -> None:
    """P0-6: with freeze_ready candidate, agent self-sign Gate-1 is FORBIDDEN_INPUT."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="g1-run")
    factor_ref, spec = _persist_factor(store, brief, factor_id="f1")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert prop.ok
    pipe = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    assert pipe.ok, pipe.failure
    cand = pipe.run.candidates["cand-1"]
    run_cur = pipe.run
    for role, rid, key in (
        ("methodology_critic", "rv-m", "rev-m"),
        ("leakage_and_code_reviewer", "rv-l", "rev-l"),
    ):
        review_ref, _ = _persist_review(
            store,
            report_id=rid,
            role_id=role,
            factor_ref=factor_ref,
            evaluation_ref=cand.evaluation_ref,
        )
        rev = ctrl.handle(
            CommandRequest(
                command="submit_review",
                run_id=run.run_id,
                aggregate_id="cand-1",
                idempotency_key=key,
                actor_id="a",
                role_id="orchestrator",
                expected_version=run_cur.version,
                payload={"namespace": NS, "review_ref": to_plain_dict(review_ref)},
            )
        )
        assert rev.ok, rev.failure
        run_cur = rev.run
    pool_ref, _ = _persist_pool(store, decision_id="pd-g1", factor_ref=factor_ref)
    pool = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pool",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run_cur.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert pool.ok, pool.failure
    assert pool.run.candidates["cand-1"].status is CandidateStatus.FREEZE_READY
    denied = ctrl.handle(
        CommandRequest(
            command="record_gate1_approval",
            run_id=run.run_id,
            aggregate_id=run.run_id,
            idempotency_key="g1-self",
            actor_id="agent-1",
            role_id="generator",
            expected_version=pool.run.version,
            payload={
                "namespace": NS,
                "approved": True,
                "candidate_id": "cand-1",
                "freeze_intent": _caller_freeze_intent(manifest_id="fm-self"),
            },
        )
    )
    assert denied.ok is False
    assert denied.failure is not None
    assert denied.failure.code is FailureCode.FORBIDDEN_INPUT



def test_phase04_p1_freeze_staging_invisible_and_fault_recovery() -> None:
    """Event append fail: staging exists, ordinary getter fails; snapshot fail still Frozen+readable."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="fz-run")
    factor_ref, spec = _persist_factor(store, brief, factor_id="f1")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert prop.ok, prop.failure
    pipe = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    assert pipe.ok, pipe.failure
    cand = pipe.run.candidates["cand-1"]
    run_cur = pipe.run
    for role, rid, key in (
        ("methodology_critic", "rv-meth", "rev-m"),
        ("leakage_and_code_reviewer", "rv-leak", "rev-l"),
    ):
        review_ref, _ = _persist_review(
            store,
            report_id=rid,
            role_id=role,
            factor_ref=factor_ref,
            evaluation_ref=cand.evaluation_ref,
        )
        rev = ctrl.handle(
            CommandRequest(
                command="submit_review",
                run_id=run.run_id,
                aggregate_id="cand-1",
                idempotency_key=key,
                actor_id="a",
                role_id="orchestrator",
                expected_version=run_cur.version,
                payload={"namespace": NS, "review_ref": to_plain_dict(review_ref)},
            )
        )
        assert rev.ok, rev.failure
        run_cur = rev.run
    pool_ref, _ = _persist_pool(store, decision_id="pd-1", factor_ref=factor_ref)
    pool = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pool",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run_cur.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert pool.ok, pool.failure
    gate = ctrl.handle(
        CommandRequest(
            command="record_gate1_approval",
            run_id=run.run_id,
            aggregate_id=run.run_id,
            idempotency_key="g1",
            actor_id="human",
            role_id="human",
            expected_version=pool.run.version,
            payload={
                "namespace": NS,
                "approved": True,
                "human_approval_token": "trusted-human-token",
                "candidate_id": "cand-1",
                "freeze_intent": _caller_freeze_intent(manifest_id="fm-fail"),
            },
        )
    )
    assert gate.ok, gate.failure
    req = ctrl.handle(
        CommandRequest(
            command="request_freeze",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rf",
            actor_id="a",
            role_id="orchestrator",
            expected_version=gate.run.version,
            payload={"namespace": NS},
        )
    )
    assert req.ok, req.failure

    freeze_payload = {"namespace": NS}
    store.fail_put_if_absent_kind = KIND_EVENT
    fail_event = ctrl.handle(
        CommandRequest(
            command="freeze",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="fz-fail-event",
            actor_id="a",
            role_id="orchestrator",
            expected_version=req.run.version,
            payload=freeze_payload,
        )
    )
    store.fail_put_if_absent_kind = None
    assert fail_event.ok is False
    assert fail_event.failure is not None
    assert fail_event.failure.code is FailureCode.RECOVERY_REQUIRED
    staging_body = store.get_by_identity(
        namespace=NS, kind=KIND_STAGING, artifact_id="FreezeManifest-fm-fail"
    )
    staging_hash = staging_body["body"]["content_hash"]
    staging_ref = ObjectRef(
        object_type="FreezeManifest",
        object_id="fm-fail",
        content_hash=staging_hash,
        namespace=NS,
    )
    with pytest.raises(ObjectStoreError) as excinfo:
        load_formal_payload(store, staging_ref, allow_staging=False)
    assert excinfo.value.failure.code is FailureCode.INVALID_REFERENCE
    reloaded = ctrl.load_run(namespace=NS, run_id="fz-run")
    assert reloaded is not None
    assert reloaded.status is ResearchRunStatus.FREEZE_PENDING

    store.fail_kind = "controller_snapshot"
    frozen = ctrl.handle(
        CommandRequest(
            command="freeze",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="fz",
            actor_id="a",
            role_id="orchestrator",
            expected_version=req.run.version,
            payload={"namespace": NS},
        )
    )
    store.fail_kind = None
    assert frozen.ok is True
    assert frozen.run is not None
    assert frozen.run.status is ResearchRunStatus.FROZEN
    manifest_ref = ObjectRef(**dict(frozen.outputs["manifest_ref"]))
    with pytest.raises(KeyError):
        store.get_by_identity(
            namespace=NS,
            kind=KIND_OBJECT,
            artifact_id=f"FreezeManifest-{manifest_ref.object_id}",
        )
    body = load_formal_payload(store, manifest_ref, allow_staging=False)
    assert body["content_hash"] == manifest_ref.content_hash
    rebuilt = ctrl.load_run(namespace=NS, run_id="fz-run")
    assert rebuilt is not None
    assert rebuilt.status is ResearchRunStatus.FROZEN



def test_phase04_p1_forged_missing_mismatched_freeze_refs_rejected() -> None:
    """P1-2: forged/missing/mismatched eval/review/pool refs rejected."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="badref-run")
    factor_ref, _spec = _persist_factor(store, brief, factor_id="f1")
    other_factor, _so = _persist_factor(store, brief, factor_id="f2")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert prop.ok and prop.run is not None, prop.failure
    pipe = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    assert pipe.ok and pipe.run is not None, pipe.failure
    cand = pipe.run.candidates["cand-1"]
    assert cand.evaluation_ref is not None
    # Two independent reviews required before pool.
    rev1_ref, _ = _persist_review(
        store,
        report_id="rv-method",
        role_id="methodology_critic",
        factor_ref=factor_ref,
        evaluation_ref=cand.evaluation_ref,
    )
    rev2_ref, _ = _persist_review(
        store,
        report_id="rv-leak",
        role_id="leakage_and_code_reviewer",
        factor_ref=factor_ref,
        evaluation_ref=cand.evaluation_ref,
    )
    rev = ctrl.handle(
        CommandRequest(
            command="submit_review",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rev-1",
            actor_id="a",
            role_id="orchestrator",
            expected_version=pipe.run.version,
            payload={"namespace": NS, "review_ref": to_plain_dict(rev1_ref)},
        )
    )
    assert rev.ok and rev.run is not None, rev.failure
    rev = ctrl.handle(
        CommandRequest(
            command="submit_review",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rev-2",
            actor_id="a",
            role_id="orchestrator",
            expected_version=rev.run.version,
            payload={"namespace": NS, "review_ref": to_plain_dict(rev2_ref)},
        )
    )
    assert rev.ok and rev.run is not None, rev.failure
    # Mismatched pool factor_ref must be rejected with exact HASH_MISMATCH.
    pool_ref, _ = _persist_pool(
        store, decision_id="pool-bad", factor_ref=other_factor
    )
    bad_pool = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pool-bad",
            actor_id="a",
            role_id="orchestrator",
            expected_version=rev.run.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert bad_pool.ok is False
    assert bad_pool.failure is not None
    assert bad_pool.failure.code is FailureCode.HASH_MISMATCH

    # Missing evaluation on freeze path
    from skills.factor_mining.snapshots import FreezeGateError, require_complete_refs

    incomplete = CandidateAggregate(
        candidate_id="x",
        factor_ref=factor_ref,
        status=CandidateStatus.FREEZE_READY,
    )
    with pytest.raises(FreezeGateError):
        require_complete_refs(incomplete)


def test_phase04_p1_oos_thresholds_strict_float_and_phase06_transitions() -> None:
    """P1-4: frozen threshold schema is strict; Phase06 transitions stay explicit."""
    transitions = {cmd for (_, cmd) in RUN_TRANSITIONS}
    assert {"authorize_oos", "complete_oos", "promote"} <= transitions

    store, brief, brief_ref = _brief_and_store()
    factor_ref, _spec = _persist_factor(store, brief, factor_id="f1")
    eval_ref = make_object_ref(
        object_type="EvaluationReport", object_id="e1", content_hash="b" * 64, namespace=NS
    )
    review_ref = make_object_ref(
        object_type="ReviewReport", object_id="r1", content_hash="c" * 64, namespace=NS
    )
    pool_ref = make_object_ref(
        object_type="PoolDecision", object_id="p1", content_hash="d" * 64, namespace=NS
    )
    approval = ArtifactRef(
        kind="gate1_approval",
        artifact_id="g1",
        namespace=NS,
        content_hash="e" * 64,
    )
    base = {
        "manifest_id": "fm",
        "run_id": "r",
        "brief_ref": brief_ref,
        "factor_ref": factor_ref,
        "universe": brief.universe,
        "data_version": brief.data_version,
        "split_refs": {"train": "train", "validation": "validation", "sealed": "sealed"},
        "compute_engine_version": "c",
        "analyze_engine_version": "a",
        "evaluation_protocol_id": "proto-1",
        "direction": "long_high",
        "params": {},
        "missing_policy": "keep_nan",
        "adjustment_policy": "post",
        "outlier_policy": "none",
        "neutralization_policy": "none",
        "holding_horizon_bars": 5,
        "rebalance": "weekly",
        "cost": brief.cost,
        "pool_baseline_refs": (),
        "preflight_ref": make_object_ref(
            object_type="EvaluationReport", object_id="pre1", content_hash="a" * 64, namespace=NS
        ),
        "execution_ref": make_object_ref(
            object_type="FactorExecutionResult",
            object_id="ex1",
            content_hash="b" * 64,
            namespace=NS,
        ),
        "evaluation_ref": eval_ref,
        "compare_ref": make_object_ref(
            object_type="EvaluationReport", object_id="cmp1", content_hash="c" * 64, namespace=NS
        ),
        "review_refs": (review_ref,),
        "pool_decision_ref": pool_ref,
        "approval_ref": approval,
        "provenance": brief.provenance,
        "oos_metric_selectors": {
            "min_rank_ic_ir": {"fact_name": "rank_ic_ir", "operator": "gte"}
        },
    }
    ok = FreezeManifest(**base, oos_thresholds={"min_rank_ic_ir": 1})  # int→float ok
    assert ok.oos_thresholds["min_rank_ic_ir"] == 1.0
    with pytest.raises(ValueError):
        FreezeManifest(**base, oos_thresholds={"min_rank_ic_ir": True})
    with pytest.raises(ValueError):
        FreezeManifest(**base, oos_thresholds={"min_rank_ic_ir": "0.2"})


def test_phase04_p0_failure_knowledge_staging_event_gated() -> None:
    """FK staged before terminal event; event fail ⇒ public getter not committed; success publishes."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run = _create_active_run(ctrl, brief_ref, run_id="fk-run")
    factor_ref, _ = _persist_factor(store, brief, factor_id="f1")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert prop.ok
    # Event append failure after staging: FK staging exists but not publicly readable.
    store.fail_put_if_absent_kind = KIND_EVENT
    bad = ctrl.handle(
        CommandRequest(
            command="reject_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rej-fail",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload={
                "namespace": NS,
                "record_failure_knowledge": True,
                "family_fingerprint": "fam" + "0" * 13,
                "formula_fingerprint": "frm" + "0" * 13,
                "failure_type": "manual_reject",
                "disposition": "rejected",
                "split_id": "train",
            },
        )
    )
    store.fail_put_if_absent_kind = None
    assert bad.ok is False
    assert bad.failure is not None
    assert bad.failure.code is FailureCode.RECOVERY_REQUIRED
    # Discover staged FK id
    staging_ids = store.list_artifact_ids(namespace=NS, kind=KIND_STAGING)
    fk_ids = [aid for aid in staging_ids if aid.startswith("FailureKnowledgeEntry-")]
    assert len(fk_ids) == 1
    body = store.get_by_identity(namespace=NS, kind=KIND_STAGING, artifact_id=fk_ids[0])
    fk_ref = ObjectRef(
        object_type="FailureKnowledgeEntry",
        object_id=body["object_id"],
        content_hash=body["body"]["content_hash"],
        namespace=NS,
    )
    with pytest.raises(ObjectStoreError) as excinfo:
        load_formal_payload(store, fk_ref, allow_staging=False)
    assert excinfo.value.failure.code is FailureCode.INVALID_REFERENCE
    # Candidate still proposed (event never committed).
    loaded = ctrl.load_run(namespace=NS, run_id="fk-run")
    assert loaded is not None
    assert loaded.candidates["cand-1"].status is CandidateStatus.PROPOSED
    # Successful reject publishes FK via terminal event binding.
    ok = ctrl.handle(
        CommandRequest(
            command="reject_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rej-ok",
            actor_id="a",
            role_id="orchestrator",
            expected_version=loaded.version,
            payload={
                "namespace": NS,
                "record_failure_knowledge": True,
                "family_fingerprint": "fam" + "1" * 13,
                "formula_fingerprint": "frm" + "1" * 13,
                "failure_type": "manual_reject",
                "disposition": "rejected",
                "split_id": "train",
            },
        )
    )
    assert ok.ok is True, ok.failure
    pub_ref = ObjectRef(**dict(ok.outputs["failure_knowledge_ref"]))
    published = load_formal_payload(store, pub_ref, allow_staging=False)
    assert published["content_hash"] == pub_ref.content_hash
    assert published["knowledge_id"] == pub_ref.object_id


def test_phase04_p0_pipeline_terminal_event_fail_started_ledger() -> None:
    """Terminal event append fail: started ledger → same-key RECOVERY_REQUIRED, no re-call."""
    store, brief, brief_ref = _brief_and_store()

    class OrderedAnalyze:
        def __init__(self):
            self.calls: list[str] = []

        def preflight(self, request):
            self.calls.append("preflight")
            return _ok_report(request, "pre")

        def evaluate(self, request):
            self.calls.append("evaluate")
            return _ok_report(request, "eval")

        def compare_to_pool(self, request):
            self.calls.append("compare_to_pool")
            return _ok_report(request, "cmp")

    class OrderedExec:
        def __init__(self):
            self.calls: list[str] = []

        def execute(self, request):
            self.calls.append("execute")
            return _ok_execution(request, store)

    analyze = OrderedAnalyze()
    execution = OrderedExec()
    ctrl, _, _ = _controller(store, brief_ref, analyze=analyze, execution=execution)
    run = _create_active_run(ctrl, brief_ref, run_id="term-run")
    factor_ref, _ = _persist_factor(store, brief, factor_id="f1")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert prop.ok
    # Block only the terminal event (started is head+1, terminal head+2).
    started_seq = prop.run.event_head_seq + 1
    terminal_seq = prop.run.event_head_seq + 2
    terminal_aid = f"term-run-{terminal_seq:08d}"
    orig = store.put_if_absent

    def blocked_put_if_absent(**kwargs):
        if kwargs.get("kind") == KIND_EVENT and kwargs.get("artifact_id") == terminal_aid:
            raise RuntimeError("injected terminal event failure")
        return orig(**kwargs)

    store.put_if_absent = blocked_put_if_absent  # type: ignore[method-assign]
    first = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe-term",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    store.put_if_absent = orig  # type: ignore[method-assign]
    assert first.ok is False
    assert first.failure is not None
    assert first.failure.code is FailureCode.RECOVERY_REQUIRED
    # Full port path reached terminal append: exact stage order/count.
    assert analyze.calls == ["preflight", "evaluate", "compare_to_pool"]
    assert execution.calls == ["execute"]
    # Same key: exact RecoveryRequired from started ledger; ports not recalled.
    second = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe-term",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    assert second.ok is False
    assert second.failure is not None
    assert second.failure.code is FailureCode.RECOVERY_REQUIRED
    assert second.replayed is True
    assert analyze.calls == ["preflight", "evaluate", "compare_to_pool"]
    assert execution.calls == ["execute"]
    loaded = ctrl.load_run(namespace=NS, run_id="term-run")
    assert loaded is not None
    assert loaded.event_head_seq == started_seq
    # Unrelated command proceeds from advanced head.
    factor2, _ = _persist_factor(store, brief, factor_id="f2")
    other = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-2",
            idempotency_key="prop-2",
            actor_id="a",
            role_id="orchestrator",
            expected_version=loaded.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor2)},
        )
    )
    assert other.ok is True, other.failure
    assert analyze.calls == ["preflight", "evaluate", "compare_to_pool"]
    assert execution.calls == ["execute"]


def _pipeline_to_review_pending(ctrl, store, brief, brief_ref, *, run_id="pr-run"):
    run = _create_active_run(ctrl, brief_ref, run_id=run_id)
    factor_ref, spec = _persist_factor(store, brief, factor_id="f1")
    prop = ctrl.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor_ref)},
        )
    )
    assert prop.ok, prop.failure
    pipe = ctrl.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=_pipeline_payload(brief_ref, factor_ref),
        )
    )
    assert pipe.ok, pipe.failure
    return pipe.run, factor_ref, spec


def test_phase04_p1f_dual_hash_accepted_tampered_fingerprint_rejected() -> None:
    """Envelope ArtifactRef hashes may differ from Series content hashes; fingerprint must recompute."""
    from dataclasses import replace as dc_replace

    from skills.factor_mining.adapters.execution_identity import (
        execution_envelope_identity,
    )

    store, brief, brief_ref = _brief_and_store()

    class DualHashExec:
        def __init__(self):
            self.tamper = False
            self.calls = 0

        def execute(self, request):
            self.calls += 1
            result = _ok_execution(request, store)
            assert result.values_ref is not None
            assert result.valid_mask_ref is not None
            assert result.values_ref.content_hash != result.values_content_hash
            assert result.valid_mask_ref.content_hash != result.valid_mask_content_hash
            assert execution_envelope_identity(result) == result.fingerprint
            if self.tamper:
                return dc_replace(result, fingerprint="0" * 64)
            return result

    exec_port = DualHashExec()
    ctrl, _, _ = _controller(store, brief_ref, execution=exec_port)
    run, factor_ref, _ = _pipeline_to_review_pending(
        ctrl, store, brief, brief_ref, run_id="dual-ok"
    )
    assert exec_port.calls == 1
    assert run.candidates["cand-1"].execution_ref is not None

    store2, brief2, brief_ref2 = _brief_and_store()
    exec_bad = DualHashExec()
    exec_bad.tamper = True
    ctrl2, _, _ = _controller(store2, brief_ref2, execution=exec_bad)
    run2 = _create_active_run(ctrl2, brief_ref2, run_id="dual-bad")
    factor2, _ = _persist_factor(store2, brief2, factor_id="f1")
    prop = ctrl2.handle(
        CommandRequest(
            command="propose_candidate",
            run_id=run2.run_id,
            aggregate_id="cand-1",
            idempotency_key="p",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run2.version,
            payload={"namespace": NS, "factor_ref": to_plain_dict(factor2)},
        )
    )
    assert prop.ok
    bad = ctrl2.handle(
        CommandRequest(
            command="run_candidate_pipeline",
            run_id=run2.run_id,
            aggregate_id="cand-1",
            idempotency_key="pipe",
            actor_id="a",
            role_id="orchestrator",
            expected_version=prop.run.version,
            payload=_pipeline_payload(brief_ref2, factor2),
        )
    )
    assert bad.ok is False
    assert bad.failure is not None
    assert bad.failure.code is FailureCode.HASH_MISMATCH
    assert "fingerprint" in bad.failure.message


def test_phase04_p1d_review_conclusion_drives_transition_not_payload() -> None:
    """Persisted ReviewReport.conclusion is sole authority; payload hard_reject ignored."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run, factor_ref, _ = _pipeline_to_review_pending(
        ctrl, store, brief, brief_ref, run_id="rev-concl"
    )
    cand = run.candidates["cand-1"]

    # FAIL despite payload hard_reject=false → REJECTED
    fail_ref, _ = _persist_review(
        store,
        report_id="rv-fail",
        role_id="methodology_critic",
        factor_ref=factor_ref,
        evaluation_ref=cand.evaluation_ref,
        conclusion=ReviewConclusion.FAIL,
    )
    failed = ctrl.handle(
        CommandRequest(
            command="submit_review",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rev-fail",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run.version,
            payload={
                "namespace": NS,
                "review_ref": to_plain_dict(fail_ref),
                "hard_reject": False,
            },
        )
    )
    assert failed.ok, failed.failure
    assert failed.run.candidates["cand-1"].status is CandidateStatus.REJECTED

    # Fresh candidate for PASS / DEBATE / REVISE
    for conclusion, expect_status, key in (
        (ReviewConclusion.PASS, CandidateStatus.REVIEW_PENDING, "pass"),
        (ReviewConclusion.DEBATE, CandidateStatus.DEBATING, "debate"),
        (ReviewConclusion.REVISE, CandidateStatus.SYNTHESIZING, "revise"),
    ):
        store_i, brief_i, brief_ref_i = _brief_and_store()
        ctrl_i, _, _ = _controller(store_i, brief_ref_i)
        run_i, factor_i, _ = _pipeline_to_review_pending(
            ctrl_i, store_i, brief_i, brief_ref_i, run_id=f"rev-{key}"
        )
        cand_i = run_i.candidates["cand-1"]
        rev_ref, _ = _persist_review(
            store_i,
            report_id=f"rv-{key}",
            role_id="methodology_critic",
            factor_ref=factor_i,
            evaluation_ref=cand_i.evaluation_ref,
            conclusion=conclusion,
        )
        out = ctrl_i.handle(
            CommandRequest(
                command="submit_review",
                run_id=run_i.run_id,
                aggregate_id="cand-1",
                idempotency_key=f"rev-{key}",
                actor_id="a",
                role_id="orchestrator",
                expected_version=run_i.version,
                payload={
                    "namespace": NS,
                    "review_ref": to_plain_dict(rev_ref),
                    # Adversarial: payload claims hard_reject even when PASS.
                    "hard_reject": True,
                },
            )
        )
        assert out.ok, out.failure
        assert out.run.candidates["cand-1"].status is expect_status


def test_phase04_p1e_gate1_rejects_mutated_derived_freeze_fields() -> None:
    """Derived freeze fields in Gate-1 intent must exact-match evidence; freeze cannot mutate."""
    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run, factor_ref, _ = _pipeline_to_review_pending(
        ctrl, store, brief, brief_ref, run_id="gate1-mut"
    )
    cand = run.candidates["cand-1"]
    run_cur = run
    for role, rid, key in (
        ("methodology_critic", "rv-m", "rev-m"),
        ("leakage_and_code_reviewer", "rv-l", "rev-l"),
    ):
        review_ref, _ = _persist_review(
            store,
            report_id=rid,
            role_id=role,
            factor_ref=factor_ref,
            evaluation_ref=cand.evaluation_ref,
        )
        rev = ctrl.handle(
            CommandRequest(
                command="submit_review",
                run_id=run.run_id,
                aggregate_id="cand-1",
                idempotency_key=key,
                actor_id="a",
                role_id="orchestrator",
                expected_version=run_cur.version,
                payload={"namespace": NS, "review_ref": to_plain_dict(review_ref)},
            )
        )
        assert rev.ok, rev.failure
        run_cur = rev.run
    pool_ref, _ = _persist_pool(store, decision_id="pd-1", factor_ref=factor_ref)
    pool = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pool",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run_cur.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert pool.ok, pool.failure

    bad_intent = _caller_freeze_intent(manifest_id="fm-mut")
    bad_intent["holding_horizon_bars"] = 999  # must derive from brief.horizon_bars
    denied = ctrl.handle(
        CommandRequest(
            command="record_gate1_approval",
            run_id=run.run_id,
            aggregate_id=run.run_id,
            idempotency_key="g1-bad",
            actor_id="human",
            role_id="human",
            expected_version=pool.run.version,
            payload={
                "namespace": NS,
                "approved": True,
                "human_approval_token": "trusted-human-token",
                "candidate_id": "cand-1",
                "freeze_intent": bad_intent,
            },
        )
    )
    assert denied.ok is False
    assert denied.failure is not None
    assert denied.failure.code is FailureCode.HASH_MISMATCH

    gate = ctrl.handle(
        CommandRequest(
            command="record_gate1_approval",
            run_id=run.run_id,
            aggregate_id=run.run_id,
            idempotency_key="g1-ok",
            actor_id="human",
            role_id="human",
            expected_version=pool.run.version,
            payload={
                "namespace": NS,
                "approved": True,
                "human_approval_token": "trusted-human-token",
                "candidate_id": "cand-1",
                "freeze_intent": _caller_freeze_intent(manifest_id="fm-mut-ok"),
            },
        )
    )
    assert gate.ok, gate.failure
    req = ctrl.handle(
        CommandRequest(
            command="request_freeze",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rf",
            actor_id="a",
            role_id="orchestrator",
            expected_version=gate.run.version,
            payload={"namespace": NS},
        )
    )
    assert req.ok, req.failure
    mutate_freeze = ctrl.handle(
        CommandRequest(
            command="freeze",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="fz-mut",
            actor_id="a",
            role_id="orchestrator",
            expected_version=req.run.version,
            payload={"namespace": NS, "holding_horizon_bars": 1},
        )
    )
    assert mutate_freeze.ok is False
    assert mutate_freeze.failure is not None
    assert mutate_freeze.failure.code is FailureCode.FORBIDDEN_INPUT


def test_phase04_p1bc_event_gated_publish_rejects_forged_and_unreadable() -> None:
    """P1-B/C: FreezeManifest/FK require verified chain; listed unreadable fails closed."""
    from skills.factor_mining.event_chain import EventChainError, load_run_event_payloads

    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    run, factor_ref, _ = _pipeline_to_review_pending(
        ctrl, store, brief, brief_ref, run_id="gate-ev"
    )
    cand = run.candidates["cand-1"]
    run_cur = run
    for role, rid, key in (
        ("methodology_critic", "rv-m", "rev-m"),
        ("leakage_and_code_reviewer", "rv-l", "rev-l"),
    ):
        review_ref, _ = _persist_review(
            store,
            report_id=rid,
            role_id=role,
            factor_ref=factor_ref,
            evaluation_ref=cand.evaluation_ref,
        )
        rev = ctrl.handle(
            CommandRequest(
                command="submit_review",
                run_id=run.run_id,
                aggregate_id="cand-1",
                idempotency_key=key,
                actor_id="a",
                role_id="orchestrator",
                expected_version=run_cur.version,
                payload={"namespace": NS, "review_ref": to_plain_dict(review_ref)},
            )
        )
        assert rev.ok, rev.failure
        run_cur = rev.run
    pool_ref, _ = _persist_pool(store, decision_id="pd-1", factor_ref=factor_ref)
    pool = ctrl.handle(
        CommandRequest(
            command="submit_pool_decision",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="pool",
            actor_id="a",
            role_id="orchestrator",
            expected_version=run_cur.version,
            payload={"namespace": NS, "pool_decision_ref": to_plain_dict(pool_ref)},
        )
    )
    assert pool.ok
    gate = ctrl.handle(
        CommandRequest(
            command="record_gate1_approval",
            run_id=run.run_id,
            aggregate_id=run.run_id,
            idempotency_key="g1",
            actor_id="human",
            role_id="human",
            expected_version=pool.run.version,
            payload={
                "namespace": NS,
                "approved": True,
                "human_approval_token": "trusted-human-token",
                "candidate_id": "cand-1",
                "freeze_intent": _caller_freeze_intent(manifest_id="fm-ev"),
            },
        )
    )
    assert gate.ok, gate.failure
    req = ctrl.handle(
        CommandRequest(
            command="request_freeze",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="rf",
            actor_id="a",
            role_id="orchestrator",
            expected_version=gate.run.version,
            payload={"namespace": NS},
        )
    )
    assert req.ok
    frozen = ctrl.handle(
        CommandRequest(
            command="freeze",
            run_id=run.run_id,
            aggregate_id="cand-1",
            idempotency_key="fz",
            actor_id="a",
            role_id="orchestrator",
            expected_version=req.run.version,
            payload={"namespace": NS},
        )
    )
    assert frozen.ok, frozen.failure
    manifest_ref = frozen.run.freeze_manifest_ref
    assert manifest_ref is not None
    # Happy path: verified publish.
    body = load_formal_payload(store, manifest_ref, allow_staging=False)
    assert body["content_hash"] == manifest_ref.content_hash

    # Forged ObjectRef hash must not publish.
    forged = ObjectRef(
        object_type="FreezeManifest",
        object_id=manifest_ref.object_id,
        content_hash="f" * 64,
        namespace=NS,
    )
    with pytest.raises(ObjectStoreError):
        load_formal_payload(store, forged, allow_staging=False)

    # Listed event unreadable → load_run_event_payloads fail-closed (not end-of-log).
    from tests.skills.factor_mining.memory_store import UnreadableListedArtifactStore

    aids = [
        aid
        for aid in store.list_artifact_ids(namespace=NS, kind=KIND_EVENT)
        if str(aid).startswith("gate-ev-")
    ]
    assert aids
    victim = sorted(aids)[-1]
    wrapped = UnreadableListedArtifactStore(store)
    wrapped.mark_unreadable(namespace=NS, kind=KIND_EVENT, artifact_id=victim)
    # Still listed via public API.
    assert victim in wrapped.list_artifact_ids(namespace=NS, kind=KIND_EVENT)
    with pytest.raises(EventChainError) as excinfo:
        load_run_event_payloads(wrapped, namespace=NS, run_id="gate-ev")
    assert excinfo.value.failure.code is FailureCode.RECOVERY_REQUIRED
    assert "unreadable" in excinfo.value.failure.message


def test_phase04_p1c_listed_event_gap_is_corruption() -> None:
    from skills.factor_mining.event_chain import EventChainError, parse_run_event_sequences

    with pytest.raises(EventChainError) as excinfo:
        parse_run_event_sequences(
            run_id="run-x",
            artifact_ids=["run-x-00000001", "run-x-00000003"],
        )
    assert "gap" in excinfo.value.failure.message
