"""Strategy-neutral target-weight contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd


@dataclass(frozen=True)
class StrategyContext:
    """Stable identity and domain metadata supplied to a weight generator."""

    strategy_id: str
    run_id: str
    variant_id: str | None
    domain: str


@dataclass
class StrategyResult:
    """Date x symbol target weights plus strategy-neutral diagnostics."""

    target_weights: pd.DataFrame
    diagnostics: dict[str, Any] = field(default_factory=dict)


class WeightGenerator(Protocol):
    """Protocol implemented by strategies that produce target weights."""

    def generate_weights(self, data: Any, context: StrategyContext) -> StrategyResult:
        """Generate date x symbol target weights."""


__all__ = ["StrategyContext", "StrategyResult", "WeightGenerator"]
