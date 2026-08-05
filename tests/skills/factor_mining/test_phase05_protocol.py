"""Phase 05 protocol tests using a deterministic test-only host fixture."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from skills.factor_mining import (
    AgentTaskResult,
    AgentTaskView,
    FailureCode,
    FailureDetail,
    ObjectRef,
    TaskLease,
    TaskResultStatus,
)
from tests.skills.factor_mining.phase05_protocol import (
    SemanticCapabilities,
    audit_shape,
    authorized_view_inputs,
    parse_role_protocol,
    select_mode,
    stable_collect,
    task_batches,
)

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills/factor_mining/SKILL.md"
NS = "ns.phase05"


def _ref(object_type: str, object_id: str, seed: int) -> ObjectRef:
    return ObjectRef(
        object_type=object_type,
        object_id=object_id,
        content_hash=f"{seed:064x}",
        namespace=NS,
    )


def _view(role, index: int) -> tuple[AgentTaskView, AgentTaskResult]:
    brief_ref = _ref("ResearchBrief", "brief-1", 1)
    factor_ref = _ref("FactorSpec", "factor-1", 2)
    evaluation_ref = _ref("EvaluationReport", "eval-1", 3)
    if role.output_contract == "FactorSpec":
        refs = (brief_ref,)
        candidate_ref = None
        consumed = {"candidates": 1}
    elif role.output_contract in {"ReviewReport", "PoolDecision"}:
        refs = (factor_ref, evaluation_ref)
        candidate_ref = factor_ref
        consumed = {}
    else:
        raise AssertionError("host supervisor is not dispatched as a child task")
    lease = TaskLease(
        lease_id=f"lease-{index}",
        run_id="run-1",
        task_id=f"task-{index}",
        role_id=role.role_id,
        candidates_remaining=4,
        experiments_remaining=4,
        revisions_remaining=1,
        debate_rounds_remaining=2,
    )
    view = AgentTaskView(
        task_id=lease.task_id,
        run_id=lease.run_id,
        parent_task_id="supervisor-task",
        role_id=role.role_id,
        goal="protocol fixture",
        input_refs=refs,
        input_hashes={f"ref:{idx}": ref.content_hash for idx, ref in enumerate(refs)},
        visibility=("brief", "factor", "evaluation"),
        lease=lease,
        attempt=1,
        debate_round=0,
        expected_output_type=role.output_contract,
        candidate_ref=candidate_ref,
    )
    result = AgentTaskResult(
        task_id=view.task_id,
        run_id=view.run_id,
        role_id=view.role_id,
        status=TaskResultStatus.SUCCEEDED,
        output_type=view.expected_output_type,
        output_ref=_ref(view.expected_output_type, f"output-{index}", index + 10),
        budget_consumed=consumed,
        handoff_to="Controller",
        parent_task_id=view.parent_task_id,
    )
    return view, result


def _dispatched_views_and_results():
    roles = parse_role_protocol(SKILL)
    dispatched = tuple(
        role
        for batch in task_batches(
            roles,
            SemanticCapabilities(
                isolated_contexts=True,
                parallel_dispatch=True,
                wait_collect=True,
                cancellation=True,
            ),
        )
        for role in batch
    )
    views_and_results = tuple(_view(role, index) for index, role in enumerate(dispatched))
    views = tuple(pair[0] for pair in views_and_results)
    results = tuple(pair[1] for pair in views_and_results)
    return roles, views, results


def test_phase05_capability_modes_have_same_logical_batches_and_audit_order() -> None:
    roles, views, results = _dispatched_views_and_results()
    profiles = (
        SemanticCapabilities(True, True, True, True),
        SemanticCapabilities(True, False, True, True),
        SemanticCapabilities(False, False, False, False),
    )
    assert tuple(select_mode(profile) for profile in profiles) == (
        "native",
        "isolated",
        "sequential",
    )
    parallel_batches = task_batches(roles, profiles[0])
    isolated_batches = task_batches(roles, profiles[1])
    sequential_batches = task_batches(roles, profiles[2])
    assert tuple(len(batch) for batch in parallel_batches) == (4, 2, 1)
    assert isolated_batches == parallel_batches
    assert tuple(len(batch) for batch in sequential_batches) == (1,) * 7
    assert tuple(role.role_id for batch in sequential_batches for role in batch) == tuple(
        role.role_id for batch in parallel_batches for role in batch
    )

    collected = tuple(stable_collect(views, reversed(results), roles) for _ in profiles)
    assert collected[0] == collected[1] == collected[2]
    assert audit_shape(collected[0]) == audit_shape(collected[1]) == audit_shape(collected[2])


def test_phase05_isolation_and_return_failures_are_rejected_without_extra_work() -> None:
    roles, views, results = _dispatched_views_and_results()
    generator_views = [view for view in views if view.expected_output_type == "FactorSpec"]
    reviewer_views = [view for view in views if view.expected_output_type == "ReviewReport"]
    assert len(generator_views) == 4
    assert len(reviewer_views) == 2
    assert all(set(authorized_view_inputs(view)) == {"ref:0"} for view in generator_views)
    assert all(len(authorized_view_inputs(view)) == 2 for view in reviewer_views)
    # Initial reviewer views contain formal factor/evaluation refs, never another review.
    assert all(
        all(ref.object_type != "ReviewReport" for ref in view.input_refs)
        for view in reviewer_views
    )

    with pytest.raises(ValueError, match="duplicate"):
        stable_collect(views, (*results, results[0]), roles)
    with pytest.raises(ValueError, match="exactly once"):
        stable_collect(views, results[:-1], roles)
    with pytest.raises(ValueError, match="role_id"):
        stable_collect(views, (replace(results[0], role_id="unlisted"), *results[1:]), roles)
    with pytest.raises(ValueError, match="task result has no issued"):
        stable_collect(views, (replace(results[0], task_id="unknown"), *results[1:]), roles)

    for status in (
        TaskResultStatus.FAILED,
        TaskResultStatus.CANCELLED,
        TaskResultStatus.TIMED_OUT,
    ):
        failed = AgentTaskResult(
            task_id=views[0].task_id,
            run_id=views[0].run_id,
            role_id=views[0].role_id,
            status=status,
            output_type=views[0].expected_output_type,
            output_ref=None,
            failure=FailureDetail(code=FailureCode.RECOVERY_REQUIRED, message=status.value),
            budget_consumed={},
            handoff_to="Controller",
            parent_task_id=views[0].parent_task_id,
        )
        returned = (failed, *results[1:])
        collected = stable_collect(views, reversed(returned), roles)
        assert collected[0].status is status
        assert collected[0].budget_consumed == {}


def test_phase05_view_hash_and_cross_namespace_injections_fail_before_dispatch() -> None:
    roles, views, _results = _dispatched_views_and_results()
    view = views[0]
    with pytest.raises(ValueError, match="input_hashes"):
        replace(view, input_hashes={"ref:0": "f" * 64})
    foreign = ObjectRef(
        object_type="ResearchBrief",
        object_id="foreign",
        content_hash="e" * 64,
        namespace="other.namespace",
    )
    reviewer = next(item for item in views if item.expected_output_type == "ReviewReport")
    with pytest.raises(ValueError, match="namespace mismatch"):
        replace(
            reviewer,
            input_refs=(foreign,),
            input_hashes={"ref:0": foreign.content_hash},
        )
    assert len(roles) == 8
