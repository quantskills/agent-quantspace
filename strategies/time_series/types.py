"""Shared types and configuration for time-series ML strategies."""

from typing import TypedDict


class TimeSeriesConfig(TypedDict, total=False):
    commission: float
    slippage: float
    delay: int
    position_mapping: dict


DEFAULT_TS_COMMISSION = 0.0003
DEFAULT_TS_SLIPPAGE = 0.0002
DEFAULT_TS_DELAY = 1
DEFAULT_POSITION_MAPPING = {1: 1, 0: -1}
