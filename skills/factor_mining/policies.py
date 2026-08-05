"""Stop-policy evaluation for research runs (no Agent scheduling)."""

from __future__ import annotations

from collections.abc import Mapping

from skills.factor_mining.budget import (
    BudgetView,
    action_budget_keys,
    exhausted_keys,
)
from skills.factor_mining.contracts import CandidateStatus
from skills.factor_mining.state import RunAggregate

STOP_BUDGET_EXHAUSTED = "budget_exhausted"
STOP_REVISION_LIMIT = "revision_limit"
STOP_DEBATE_LIMIT = "debate_limit"
STOP_NO_NEW_FAMILY = "no_new_hypothesis_family"
STOP_DUPLICATE_THRESHOLD = "duplicate_threshold"
STOP_NO_INCREMENTAL_VALUE = "no_incremental_value"
STOP_DATA_INSUFFICIENT = "data_insufficient"
STOP_RESEARCH_POLLUTION = "research_pollution"
STOP_HUMAN_TERMINATED = "human_terminated"


def evaluate_stop_reason(
    run: RunAggregate,
    *,
    budget: BudgetView | None = None,
    action: str | None = None,
    consecutive_duplicate_families: int = 0,
    duplicate_threshold: int = 3,
    no_incremental_value: bool = False,
    data_insufficient: bool = False,
    research_pollution: bool = False,
    human_terminated: bool = False,
) -> str | None:
    """Return a stable stop reason string, or None when research may continue.

    When ``action`` is provided, only that action's budget keys are checked for
    exhaustion (optional zero revisions/debate must not block first propose).
    """
    if human_terminated:
        return STOP_HUMAN_TERMINATED
    if research_pollution:
        return STOP_RESEARCH_POLLUTION
    if data_insufficient:
        return STOP_DATA_INSUFFICIENT
    if no_incremental_value:
        return STOP_NO_INCREMENTAL_VALUE
    view = budget or BudgetView.from_run(run)
    if action:
        needed = action_budget_keys(action)
        if needed and any(view.remaining.get(key, 0) <= 0 for key in needed):
            return STOP_BUDGET_EXHAUSTED
    else:
        # Global stop only when core research actions are both blocked.
        if (
            view.remaining.get("candidates", 0) <= 0
            and view.remaining.get("experiments", 0) <= 0
        ):
            return STOP_BUDGET_EXHAUSTED
    if view.remaining.get("revisions", 0) <= 0 and any(
        cand.status is CandidateStatus.REJECTED and cand.parent_ref is not None
        for cand in run.candidates.values()
    ):
        if view.limits.get("revisions", 0) > 0 and view.remaining.get("revisions", 0) <= 0:
            if action in (None, "revise_candidate"):
                return STOP_REVISION_LIMIT
    if view.remaining.get("debate_rounds", 0) <= 0 and view.limits.get("debate_rounds", 0) > 0:
        debating = any(
            cand.status is CandidateStatus.DEBATING for cand in run.candidates.values()
        )
        if debating or any(t.debate_round > 0 for t in run.tasks.values()):
            if action in (None, "debate"):
                return STOP_DEBATE_LIMIT
    if consecutive_duplicate_families >= duplicate_threshold:
        return STOP_DUPLICATE_THRESHOLD
    if consecutive_duplicate_families > 0 and view.remaining.get("candidates", 0) <= 0:
        return STOP_NO_NEW_FAMILY
    return None


def stop_event_details(reason: str, *, extras: Mapping[str, object] | None = None) -> dict:
    payload = {"stop_reason": reason}
    if extras:
        payload.update(dict(extras))
    return payload


__all__ = [
    "STOP_BUDGET_EXHAUSTED",
    "STOP_REVISION_LIMIT",
    "STOP_DEBATE_LIMIT",
    "STOP_NO_NEW_FAMILY",
    "STOP_DUPLICATE_THRESHOLD",
    "STOP_NO_INCREMENTAL_VALUE",
    "STOP_DATA_INSUFFICIENT",
    "STOP_RESEARCH_POLLUTION",
    "STOP_HUMAN_TERMINATED",
    "evaluate_stop_reason",
    "stop_event_details",
    "exhausted_keys",
]
