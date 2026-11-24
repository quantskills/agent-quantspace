"""Target units shared by the backtest and live trading: ``percent`` or ``lots``.

A strategy's target table holds either the share of capital per symbol (``percent``, where
1.0 is 100%) or the number of lots to hold (``lots``). A futures lot is one contract; a
stock or fund lot is :data:`SHARES_PER_LOT` shares. Lots are whole numbers, and stocks and
funds cannot be short. The unit is declared by the strategy (``LiveSpec.unit`` or
``daily_main(..., unit=)``) and passed to ``VectorBacktester(unit=)``; it never travels on
the table itself.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import numpy as np
import pandas as pd

Unit = Literal["percent", "lots"]
UNITS: tuple[str, ...] = ("percent", "lots")
# One stock or fund lot (A-share board lot); the only place lots turn into shares.
SHARES_PER_LOT = 100
# PandaData exchange suffixes whose symbols are futures, traded in whole contracts.
FUTURES_SUFFIXES = frozenset({"SHF", "DCE", "CZC", "CFE", "INE", "GFE"})
# Lots further than this from a whole number are refused instead of rounded.
LOTS_TOLERANCE = 1e-9


def is_futures_symbol(symbol: str) -> bool:
    """Whether a PandaData symbol such as ``RB2701.SHF`` names a futures contract."""
    return str(symbol).rpartition(".")[2] in FUTURES_SUFFIXES


def is_continuous_future(symbol: str) -> bool:
    """Whether ``symbol`` is a continuous futures code such as ``RB_DOMINANT.SHF``."""
    return is_futures_symbol(symbol) and "_" in str(symbol).partition(".")[0]


def check_unit(unit: str) -> str:
    """``unit`` itself when it is ``percent`` or ``lots``; ValueError otherwise."""
    if unit not in UNITS:
        raise ValueError(f"unit must be 'percent' or 'lots', not {unit!r}")
    return unit


def units_per_lot(symbol: str, multipliers: Mapping[str, float] | None = None) -> float:
    """Price units one lot moves: the contract multiplier of a future, 100 shares otherwise."""
    if not is_futures_symbol(symbol):
        return float(SHARES_PER_LOT)
    multipliers = multipliers or {}
    if symbol not in multipliers:
        raise ValueError(f"{symbol}: futures symbol needs a contract multiplier")
    value = float(multipliers[symbol])
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{symbol}: invalid multiplier {value}")
    return value


def lot_problem(symbol: str, value: float) -> str | None:
    """Why one lot target is invalid (not finite, not whole, a short stock or fund), or None."""
    number = float(value)
    if not math.isfinite(number):
        return f"{symbol}: lots {value} is not finite"
    if abs(number - round(number)) > LOTS_TOLERANCE:
        return f"{symbol}: lots {value} is not a whole number"
    if number < 0 and not is_futures_symbol(symbol):
        return f"{symbol}: stocks and funds cannot be short ({number:g} lots)"
    return None


def lots_problems(values: Mapping[str, float]) -> list[str]:
    """Why each invalid lot target is invalid."""
    found = (lot_problem(str(symbol), value) for symbol, value in values.items())
    return [problem for problem in found if problem]


def check_lots(values: Mapping[str, float]) -> dict[str, int]:
    """Whole lots per symbol; ValueError listing every invalid target, nothing rounded."""
    problems = lots_problems(values)
    if problems:
        raise ValueError("Invalid lot targets: " + "; ".join(problems))
    return {str(symbol): int(round(float(value))) for symbol, value in values.items()}


def check_lots_table(table: pd.DataFrame) -> pd.DataFrame:
    """A lots table as whole numbers (missing values are 0); ValueError on any bad cell."""
    filled = table.astype(float).fillna(0.0)
    values = filled.to_numpy()
    stocks = np.array([not is_futures_symbol(symbol) for symbol in filled.columns], dtype=bool)
    with np.errstate(invalid="ignore"):
        bad = (
            ~np.isfinite(values)
            | (np.abs(values - np.round(values)) > LOTS_TOLERANCE)
            | ((values < 0) & stocks[None, :])
        )
    problems = []
    for column in np.flatnonzero(bad.any(axis=0)):
        row = int(np.flatnonzero(bad[:, column])[0])
        symbol = str(filled.columns[column])
        problems.append(f"{lot_problem(symbol, values[row, column])} at {filled.index[row]}")
    if problems:
        raise ValueError("Invalid lot targets: " + "; ".join(problems))
    return filled.round()


__all__ = [
    "FUTURES_SUFFIXES",
    "LOTS_TOLERANCE",
    "SHARES_PER_LOT",
    "UNITS",
    "Unit",
    "check_lots",
    "check_lots_table",
    "check_unit",
    "is_continuous_future",
    "is_futures_symbol",
    "lot_problem",
    "lots_problems",
    "units_per_lot",
]
