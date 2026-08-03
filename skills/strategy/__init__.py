"""Reusable strategy contracts and target-weight helpers."""

from skills.strategy.contracts import StrategyContext, StrategyResult, WeightGenerator
from skills.strategy.cross_sectional import top_n_weights
from skills.strategy.ports import MarketDataReader
from skills.strategy.time_series import (
    DEFAULT_POSITION_MAPPING,
    DEFAULT_TS_COMMISSION,
    DEFAULT_TS_DELAY,
    DEFAULT_TS_SLIPPAGE,
    TimeSeriesBacktester,
    TimeSeriesConfig,
    signal_to_single_asset_weights,
)

__all__ = [
    "DEFAULT_POSITION_MAPPING",
    "DEFAULT_TS_COMMISSION",
    "DEFAULT_TS_DELAY",
    "DEFAULT_TS_SLIPPAGE",
    "MarketDataReader",
    "StrategyContext",
    "StrategyResult",
    "TimeSeriesBacktester",
    "TimeSeriesConfig",
    "WeightGenerator",
    "signal_to_single_asset_weights",
    "top_n_weights",
]
