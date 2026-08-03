"""Shared types and utilities for cross-sectional strategies."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

import pandas as pd

TradeAt = Literal["open", "close"]


class FactorConfig(TypedDict):
    """Configuration for one entry factor."""

    func: Any
    kwargs: NotRequired[dict[str, Any]]
    name: NotRequired[str]
    direction: NotRequired[int]


class ExitFilterConfig(TypedDict):
    """Configuration for one exit filter."""

    func: Any
    kwargs: NotRequired[dict[str, Any]]
    name: NotRequired[str]
    condition: NotRequired[Any]


def _normalize_rebalance_freq(rebalance_freq: int | str) -> int:
    """Normalize rebalance frequency aliases to an integer trading-day step."""
    alias_map = {"D": 1, "W": 5, "M": 22}

    if isinstance(rebalance_freq, str):
        freq_key = rebalance_freq.upper()
        if freq_key in alias_map:
            return alias_map[freq_key]
        try:
            normalized = int(rebalance_freq)
        except ValueError as exc:
            raise ValueError(
                "rebalance_freq must be one of 'D', 'W', 'M', or a positive integer."
            ) from exc
    else:
        normalized = int(rebalance_freq)

    if normalized < 1:
        raise ValueError("rebalance_freq must be a positive integer.")
    return normalized


def _calculate_month_span(index: pd.DatetimeIndex) -> float:
    """Return the span of a DatetimeIndex in fractional months."""
    start_date = index.min()
    end_date = index.max()
    month_count = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    days_in_start_month = (start_date + pd.offsets.MonthEnd(0)).day
    days_in_end_month = (end_date + pd.offsets.MonthEnd(0)).day
    fraction = (end_date.day / days_in_end_month) - (start_date.day / days_in_start_month)
    return month_count + fraction


__all__ = [
    "ExitFilterConfig",
    "FactorConfig",
    "TradeAt",
    "_calculate_month_span",
    "_normalize_rebalance_freq",
]
