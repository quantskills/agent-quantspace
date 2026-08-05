"""Test-only deterministic fixture for the documented Phase 05 host protocol.

This module deliberately parses SKILL.md instead of providing a production role
registry or an agent runtime.  It models capability-mode equivalence and task
handoff checks using the public neutral contracts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from skills.factor_mining import AgentTaskResult, AgentTaskView, validate_agent_task_handoff


@dataclass(frozen=True)
class RoleProtocol:
    role_id: str
    output_contract: str
    declaration_order: int


@dataclass(frozen=True)
class SemanticCapabilities:
    isolated_contexts: bool
    parallel_dispatch: bool
    wait_collect: bool
    cancellation: bool


def parse_role_protocol(path: Path) -> tuple[RoleProtocol, ...]:
    """Read the role catalog from its only authority: SKILL.md."""
    blocks = re.findall(
        r"### Role:.*?\n\n```text\n(.*?)```", path.read_text(encoding="utf-8"), re.DOTALL
    )
    roles: list[RoleProtocol] = []
    for index, block in enumerate(blocks):
        fields = dict(re.findall(r"^(role_id|output_contract):\s*(\S.*?)\s*$", block, re.MULTILINE))
        roles.append(
            RoleProtocol(
                role_id=fields["role_id"],
                output_contract=fields["output_contract"],
                declaration_order=index,
            )
        )
    return tuple(roles)


def select_mode(capabilities: SemanticCapabilities) -> str:
    """Choose solely from semantic capability availability."""
    if (
        capabilities.isolated_contexts
        and capabilities.parallel_dispatch
        and capabilities.wait_collect
    ):
        return "native"
    if capabilities.isolated_contexts and capabilities.wait_collect:
        return "isolated"
    return "sequential"


def task_batches(
    roles: Sequence[RoleProtocol], capabilities: SemanticCapabilities
) -> tuple[tuple[RoleProtocol, ...], ...]:
    """Return deterministic logical batches without invoking a runtime."""
    factor_roles = tuple(role for role in roles if role.output_contract == "FactorSpec")
    review_roles = tuple(role for role in roles if role.output_contract == "ReviewReport")
    synth_roles = tuple(role for role in roles if role.output_contract == "PoolDecision")
    assert len(factor_roles) == 4
    assert len(review_roles) == 2
    assert len(synth_roles) == 1
    ordered = (factor_roles, review_roles, synth_roles)
    if select_mode(capabilities) != "sequential":
        return ordered
    return tuple((role,) for batch in ordered for role in batch)


def stable_collect(
    views: Sequence[AgentTaskView],
    returned: Iterable[AgentTaskResult],
    roles: Sequence[RoleProtocol],
) -> tuple[AgentTaskResult, ...]:
    """Validate exactly-once returns and normalize collection to SKILL order."""
    views_by_task = {view.task_id: view for view in views}
    if len(views_by_task) != len(views):
        raise ValueError("task views must have unique task_id")
    role_order = {role.role_id: role.declaration_order for role in roles}
    results: list[AgentTaskResult] = []
    seen: set[str] = set()
    for result in returned:
        if result.task_id in seen:
            raise ValueError("duplicate task result")
        view = views_by_task.get(result.task_id)
        if view is None:
            raise ValueError("task result has no issued task view")
        if result.role_id not in role_order:
            raise ValueError("task result role_id absent from SKILL protocol")
        validate_agent_task_handoff(view, result)
        seen.add(result.task_id)
        results.append(result)
    if seen != set(views_by_task):
        raise ValueError("not every issued task returned exactly once")
    return tuple(
        sorted(results, key=lambda item: (role_order[item.role_id], item.task_id))
    )


def audit_shape(
    results: Sequence[AgentTaskResult],
) -> tuple[tuple[str, str, str, str], ...]:
    """Comparable audit projection for all three capability modes."""
    return tuple(
        (
            result.task_id,
            result.role_id,
            result.status.value,
            result.output_type,
        )
        for result in results
    )


def authorized_view_inputs(view: AgentTaskView) -> Mapping[str, str]:
    """Expose only immutable ref hashes for isolation assertions in tests."""
    return dict(view.input_hashes)
