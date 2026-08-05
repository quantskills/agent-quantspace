"""Phase 05 integration: host-neutral task handoffs stay behind Controller APIs."""

from __future__ import annotations

from pathlib import Path

from skills.factor_mining import (
    AgentTaskResult,
    AgentTaskView,
    FailureCode,
    ObjectRef,
    TaskResultStatus,
    rebuild_dataclass,
    to_plain_dict,
    validate_agent_task_handoff,
)
from skills.factor_mining.controller import CommandRequest
from tests.skills.factor_mining.phase05_protocol import parse_role_protocol, stable_collect
from tests.skills.factor_mining.test_controller_phase04 import (
    NS,
    _brief_and_store,
    _controller,
    _create_active_run,
    _persist_factor,
)

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/factor_mining/SKILL.md"


def test_integration_phase05_generator_handoffs_use_only_controller_tasks() -> None:
    """Four documented FactorSpec roles have identical Controller handoff semantics."""
    roles = parse_role_protocol(SKILL)
    generators = tuple(role for role in roles if role.output_contract == "FactorSpec")
    assert len(generators) == 4

    store, brief, brief_ref = _brief_and_store()
    ctrl, _, _ = _controller(store, brief_ref)
    current = _create_active_run(ctrl, brief_ref, run_id="phase05-generator-flow")
    views: list[AgentTaskView] = []
    results: list[AgentTaskResult] = []

    for index, role in enumerate(generators):
        created = ctrl.handle(
            CommandRequest(
                command="create_task",
                run_id=current.run_id,
                aggregate_id=f"generator-{index}",
                idempotency_key=f"create-{index}",
                actor_id="host",
                role_id=role.role_id,
                expected_version=current.version,
                payload={
                    "namespace": NS,
                    "visibility": ["brief"],
                    "input_refs": [to_plain_dict(brief_ref)],
                    "expected_output_type": role.output_contract,
                },
            )
        )
        assert created.ok, created.failure
        if index == 0:
            premature = ctrl.handle(
                CommandRequest(
                    command="start_task",
                    run_id=current.run_id,
                    aggregate_id=f"generator-{index}",
                    idempotency_key="premature-start",
                    actor_id="host",
                    role_id=role.role_id,
                    expected_version=created.run.version,
                    payload={"namespace": NS},
                )
            )
            assert premature.ok is False
            assert premature.failure is not None
            assert premature.failure.code is FailureCode.INVALID_STATE
        claimed = ctrl.handle(
            CommandRequest(
                command="claim_task",
                run_id=current.run_id,
                aggregate_id=f"generator-{index}",
                idempotency_key=f"claim-{index}",
                actor_id="host",
                role_id=role.role_id,
                expected_version=created.run.version,
                payload={"namespace": NS, "amounts": {"candidates": 1}},
            )
        )
        assert claimed.ok, claimed.failure
        started = ctrl.handle(
            CommandRequest(
                command="start_task",
                run_id=current.run_id,
                aggregate_id=f"generator-{index}",
                idempotency_key=f"start-{index}",
                actor_id="host",
                role_id=role.role_id,
                expected_version=claimed.run.version,
                payload={"namespace": NS},
            )
        )
        assert started.ok, started.failure
        issued = ctrl.handle(
            CommandRequest(
                command="build_task_view",
                run_id=current.run_id,
                aggregate_id=f"generator-{index}",
                idempotency_key=f"view-{index}",
                actor_id="host",
                role_id=role.role_id,
                expected_version=started.run.version,
                payload={
                    "namespace": NS,
                    "goal": "documented Phase 05 generator task",
                    "input_refs": [to_plain_dict(brief_ref)],
                    "expected_output_type": role.output_contract,
                },
            )
        )
        assert issued.ok, issued.failure
        view = rebuild_dataclass(AgentTaskView, issued.outputs["task_view"])
        factor_ref, _ = _persist_factor(store, brief, factor_id=f"phase05-{index}")
        result = AgentTaskResult(
            task_id=view.task_id,
            run_id=view.run_id,
            role_id=view.role_id,
            status=TaskResultStatus.SUCCEEDED,
            output_type=view.expected_output_type,
            output_ref=factor_ref,
            budget_consumed={"candidates": 1},
            handoff_to="Controller",
            parent_task_id=view.parent_task_id,
        )
        validate_agent_task_handoff(view, result)

        stale = ObjectRef(
            object_type=factor_ref.object_type,
            object_id=factor_ref.object_id,
            content_hash="f" * 64,
            namespace=factor_ref.namespace,
        )
        rejected = ctrl.handle(
            CommandRequest(
                command="submit_task",
                run_id=current.run_id,
                aggregate_id=view.task_id,
                idempotency_key=f"stale-{index}",
                actor_id="host",
                role_id=role.role_id,
                expected_version=issued.run.version,
                payload={"namespace": NS, "output_ref": to_plain_dict(stale)},
            )
        )
        assert rejected.ok is False
        assert rejected.failure is not None
        assert rejected.failure.code is FailureCode.HASH_MISMATCH

        submitted = ctrl.handle(
            CommandRequest(
                command="submit_task",
                run_id=current.run_id,
                aggregate_id=view.task_id,
                idempotency_key=f"submit-{index}",
                actor_id="host",
                role_id=role.role_id,
                expected_version=issued.run.version,
                payload={"namespace": NS, "output_ref": to_plain_dict(factor_ref)},
            )
        )
        assert submitted.ok, submitted.failure
        current = submitted.run
        views.append(view)
        results.append(result)

    collected = stable_collect(views, reversed(results), roles)
    assert tuple(item.role_id for item in collected) == tuple(
        role.role_id for role in generators
    )
    assert current.budget_remaining["candidates"] == 8
