"""Strategy interfaces for modular cross-sectional backtesting."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from .types import ExitFilterConfig, FactorConfig


@dataclass
class StrategyContext:
    """Immutable inputs required by a strategy implementation."""

    data: pd.DataFrame
    factor_configs: list[FactorConfig]
    exit_filters: list[ExitFilterConfig]
    top_pct: float
    weight_method: str
    rebalance_freq: int
    vol_target: float | None
    exposure_policy: str
    defensive_symbols: list[str]
    execution_returns: pd.DataFrame
    signal_lag: int


@dataclass
class StrategyResult:
    """Outputs produced by a strategy before execution-time shifting."""

    signal_df: pd.DataFrame
    signal_weights: pd.DataFrame
    votes_df: pd.DataFrame


class BaseStrategy(ABC):
    """Strategy contract for generating cross-sectional signal tables."""

    @abstractmethod
    def generate(
        self,
        factor_df: pd.DataFrame,
        factor_pivots: dict[str, pd.DataFrame],
        context: StrategyContext,
    ) -> StrategyResult:
        """Return the long-form signal table and wide target weights."""
