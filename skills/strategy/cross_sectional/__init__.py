"""Reusable cross-sectional strategy types and target-weight helpers."""

from __future__ import annotations

from skills.strategy.cross_sectional.execution import SignalBacktestExecutor
from skills.strategy.cross_sectional.exits import (
    big_loss_filter,
    consecutive_loss_filter,
    drawdown_from_high_filter,
    gap_down_filter,
    soft_dd_scaledown,
    soft_vol_hysteresis,
    vol_spike_filter,
)
from skills.strategy.cross_sectional.factor_combination import (
    CombinationMethod,
    DynamicFactorWeightConfig,
    FactorCombinationResult,
    NormalizationMethod,
    combine_factor_scores,
    estimate_factor_weights,
    normalize_factor_frames,
    orient_factor_frames,
    rank_factor_frames,
)
from skills.strategy.cross_sectional.factor_frame import FactorFrameBuilder, FactorFrameBuildResult
from skills.strategy.cross_sectional.modular_backtester import ModularBacktester
from skills.strategy.cross_sectional.risk_controls import apply_risk_controls, universe_vol_exposure
from skills.strategy.cross_sectional.selection import (
    apply_rebalance_schedule,
    hold_weights_on_calendar,
    top_n_weights,
)
from skills.strategy.cross_sectional.signals_base import BaseStrategy
from skills.strategy.cross_sectional.signals_base import (
    StrategyContext as CrossSectionalStrategyContext,
)
from skills.strategy.cross_sectional.signals_base import (
    StrategyResult as CrossSectionalStrategyResult,
)
from skills.strategy.cross_sectional.signals_top_pct import TopPctStrategy
from skills.strategy.cross_sectional.strategy_comparison import compare_strategies
from skills.strategy.cross_sectional.types import ExitFilterConfig, FactorConfig, TradeAt

__all__ = [
    "BaseStrategy",
    "CombinationMethod",
    "CrossSectionalStrategyContext",
    "CrossSectionalStrategyResult",
    "DynamicFactorWeightConfig",
    "ExitFilterConfig",
    "FactorConfig",
    "FactorFrameBuilder",
    "FactorFrameBuildResult",
    "FactorCombinationResult",
    "NormalizationMethod",
    "ModularBacktester",
    "SignalBacktestExecutor",
    "TopPctStrategy",
    "TradeAt",
    "apply_risk_controls",
    "apply_rebalance_schedule",
    "big_loss_filter",
    "compare_strategies",
    "combine_factor_scores",
    "estimate_factor_weights",
    "normalize_factor_frames",
    "orient_factor_frames",
    "consecutive_loss_filter",
    "drawdown_from_high_filter",
    "gap_down_filter",
    "hold_weights_on_calendar",
    "universe_vol_exposure",
    "soft_dd_scaledown",
    "soft_vol_hysteresis",
    "top_n_weights",
    "rank_factor_frames",
    "vol_spike_filter",
]
