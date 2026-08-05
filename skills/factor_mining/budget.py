"""Atomic research-budget reserve / settle / release helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from skills.factor_mining.contracts import FailureCode, FailureDetail
from skills.factor_mining.state import RunAggregate

BUDGET_KEYS = (
    "candidates",
    "experiments",
    "revisions",
    "debate_rounds",
)


@dataclass(frozen=True)
class BudgetReservation:
    reservation_id: str
    amounts: Mapping[str, int]


@dataclass
class BudgetView:
    limits: dict[str, int] = field(default_factory=dict)
    remaining: dict[str, int] = field(default_factory=dict)
    reservations: dict[str, dict[str, int]] = field(default_factory=dict)

    @classmethod
    def from_run(cls, run: RunAggregate) -> BudgetView:
        return cls(
            limits=dict(run.budget_limits),
            remaining=dict(run.budget_remaining),
            reservations={
                key: dict(value) for key, value in run.budget_reservations.items()
            },
        )

    def apply_to_run(self, run: RunAggregate) -> RunAggregate:
        return replace(
            run,
            budget_limits=dict(self.limits),
            budget_remaining=dict(self.remaining),
            budget_reservations={
                key: dict(value) for key, value in self.reservations.items()
            },
        )


def _require_nonneg_int_map(
    values: Mapping[str, Any], *, label: str, allow_partial: bool
) -> dict[str, int]:
    if not isinstance(values, Mapping):
        raise ValueError(f"{label} must be a mapping")
    unknown = set(values) - set(BUDGET_KEYS)
    if unknown:
        raise ValueError(f"{label} has unknown keys: {sorted(unknown)}")
    out: dict[str, int] = {}
    for key in BUDGET_KEYS:
        if key not in values:
            if allow_partial:
                out[key] = 0
                continue
            raise ValueError(f"{label} missing required key {key}")
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"{label}.{key} must be a non-negative int "
                "(bool/float/string rejected)"
            )
        if value < 0:
            raise ValueError(f"{label}.{key} must be non-negative")
        out[key] = value
    return out


def initial_budget_from_limits(limits: Mapping[str, Any]) -> BudgetView:
    cleaned = _require_nonneg_int_map(limits, label="budget_limits", allow_partial=False)
    return BudgetView(limits=dict(cleaned), remaining=dict(cleaned), reservations={})


def reserve(
    view: BudgetView,
    *,
    reservation_id: str,
    amounts: Mapping[str, Any],
) -> BudgetView | FailureDetail:
    """Atomically reserve amounts; fails closed on insufficient remaining."""
    if not reservation_id:
        return FailureDetail(
            code=FailureCode.INVALID_PARAMETERS,
            message="reservation_id required",
        )
    if reservation_id in view.reservations:
        return FailureDetail(
            code=FailureCode.DUPLICATE_LOGICAL_KEY,
            message="reservation already exists",
            details={"reservation_id": reservation_id},
        )
    try:
        normalized = _require_nonneg_int_map(
            amounts, label="reserve_amounts", allow_partial=True
        )
    except ValueError as exc:
        return FailureDetail(
            code=FailureCode.INVALID_PARAMETERS,
            message=str(exc),
        )
    for key, value in normalized.items():
        if value > view.remaining.get(key, 0):
            return FailureDetail(
                code=FailureCode.BUDGET_EXCEEDED,
                message=f"insufficient remaining budget for {key}",
                details={
                    "key": key,
                    "requested": value,
                    "remaining": view.remaining.get(key, 0),
                },
            )
    remaining = dict(view.remaining)
    for key, value in normalized.items():
        remaining[key] = remaining.get(key, 0) - value
    reservations = dict(view.reservations)
    reservations[reservation_id] = {k: v for k, v in normalized.items() if v}
    return BudgetView(
        limits=dict(view.limits),
        remaining=remaining,
        reservations=reservations,
    )


def settle(view: BudgetView, *, reservation_id: str) -> BudgetView | FailureDetail:
    """Consume a reservation (success or research failure after start)."""
    amounts = view.reservations.get(reservation_id)
    if amounts is None:
        return FailureDetail(
            code=FailureCode.INVALID_REFERENCE,
            message="unknown reservation_id",
            details={"reservation_id": reservation_id},
        )
    reservations = dict(view.reservations)
    reservations.pop(reservation_id)
    return BudgetView(
        limits=dict(view.limits),
        remaining=dict(view.remaining),
        reservations=reservations,
    )


def release(view: BudgetView, *, reservation_id: str) -> BudgetView | FailureDetail:
    """Release an unused reservation (cancel before start)."""
    amounts = view.reservations.get(reservation_id)
    if amounts is None:
        return FailureDetail(
            code=FailureCode.INVALID_REFERENCE,
            message="unknown reservation_id",
            details={"reservation_id": reservation_id},
        )
    remaining = dict(view.remaining)
    for key, value in amounts.items():
        remaining[key] = remaining.get(key, 0) + int(value)
    reservations = dict(view.reservations)
    reservations.pop(reservation_id)
    return BudgetView(
        limits=dict(view.limits),
        remaining=remaining,
        reservations=reservations,
    )


def exhausted_keys(view: BudgetView) -> tuple[str, ...]:
    return tuple(key for key in BUDGET_KEYS if view.remaining.get(key, 0) <= 0)


def action_budget_keys(action: str) -> frozenset[str]:
    """Budget dimensions required for a specific research action."""
    mapping = {
        "propose_candidate": frozenset({"candidates"}),
        "run_candidate_pipeline": frozenset({"experiments"}),
        "revise_candidate": frozenset({"revisions"}),
        "debate": frozenset({"debate_rounds"}),
    }
    return mapping.get(action, frozenset())


__all__ = [
    "BUDGET_KEYS",
    "BudgetReservation",
    "BudgetView",
    "initial_budget_from_limits",
    "reserve",
    "settle",
    "release",
    "exhausted_keys",
    "action_budget_keys",
]
