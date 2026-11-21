"""Live-trading contracts: target snapshots, weight changes, rebalance signals, deliveries."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import pandas as pd

# PandaData exchange suffixes whose symbols are futures, sized in whole contracts.
FUTURES_SUFFIXES = frozenset({"SHF", "DCE", "CZC", "CFE", "INE", "GFE"})
# Weight differences at or below this are treated as no change.
WEIGHT_TOLERANCE = 1e-6


def is_futures_symbol(symbol: str) -> bool:
    """Whether a PandaData symbol such as ``RB2701.SHF`` names a futures contract."""
    return symbol.rpartition(".")[2] in FUTURES_SUFFIXES


def _time_label(value: pd.Timestamp) -> str:
    stamp = pd.Timestamp(value)
    if stamp == stamp.normalize():
        return stamp.strftime("%Y-%m-%d")
    return stamp.strftime("%Y-%m-%d %H:%M:%S")


def _row_at(frame: pd.DataFrame, as_of: str | pd.Timestamp | None, name: str) -> pd.Series:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f"{name} table needs a datetime index or an eob column")
    if frame.empty:
        raise ValueError(f"{name} table is empty")
    ordered = frame.sort_index()
    if as_of is None:
        return ordered.iloc[-1]
    eligible = ordered.loc[ordered.index <= pd.Timestamp(as_of)]
    if eligible.empty:
        raise ValueError(f"{name} table has no row at or before {as_of}")
    return eligible.iloc[-1]


def _clean_weights(row: pd.Series) -> dict[str, float]:
    weights = {}
    for symbol, value in row.items():
        weight = 0.0 if pd.isna(value) else float(value)
        if not math.isfinite(weight):
            raise ValueError(f"Target weight for {symbol} is not finite")
        if abs(weight) > WEIGHT_TOLERANCE:
            weights[str(symbol)] = weight
    return weights


@dataclass(frozen=True)
class TargetSnapshot:
    """Nonzero target weights of one strategy at one decision time."""

    strategy_id: str
    as_of: str
    weights: dict[str, float]
    prices: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_frames(
        cls,
        weights: pd.DataFrame,
        strategy_id: str,
        *,
        as_of: str | pd.Timestamp | None = None,
        prices: pd.DataFrame | None = None,
    ) -> TargetSnapshot:
        """Take the weights row at or before ``as_of`` (default: the last row).

        ``prices`` is an optional date by symbol table; its row at or before the same time
        supplies reference prices. Missing prices stay missing instead of being filled.
        """
        row = _row_at(weights, as_of, "weights")
        stamp = pd.Timestamp(row.name)
        reference = {}
        if prices is not None:
            price_row = _row_at(prices, stamp, "prices")
            for symbol, value in price_row.items():
                if pd.notna(value) and math.isfinite(float(value)) and float(value) > 0:
                    reference[str(symbol)] = float(value)
        return cls(
            strategy_id=strategy_id,
            as_of=_time_label(stamp),
            weights=_clean_weights(row),
            prices=reference,
        )


@dataclass(frozen=True)
class WeightChange:
    symbol: str
    previous: float
    target: float

    @property
    def delta(self) -> float:
        return self.target - self.previous


@dataclass(frozen=True)
class Signal:
    """Weight changes that move the last delivered target to a new target."""

    signal_id: str
    strategy_id: str
    as_of: str
    changes: tuple[WeightChange, ...]
    target: dict[str, float]
    prices: dict[str, float]

    @property
    def is_empty(self) -> bool:
        return not self.changes


@dataclass(frozen=True)
class DeliveryResult:
    """Outcome of sending one signal to one notification channel."""

    channel: str
    ok: bool
    detail: str = ""


def diff_weights(
    previous: Mapping[str, float],
    target: Mapping[str, float],
    tolerance: float = WEIGHT_TOLERANCE,
) -> tuple[WeightChange, ...]:
    """Changed symbols, including exits to zero, sorted by symbol."""
    changes = []
    for symbol in sorted(set(previous) | set(target)):
        before = float(previous.get(symbol, 0.0))
        after = float(target.get(symbol, 0.0))
        if abs(after - before) > tolerance:
            changes.append(WeightChange(symbol=symbol, previous=before, target=after))
    return tuple(changes)


def _rounded(weights: Mapping[str, float]) -> dict[str, float]:
    return {symbol: round(float(weight), 10) for symbol, weight in sorted(weights.items())}


def build_signal(snapshot: TargetSnapshot, previous: Mapping[str, float] | None = None) -> Signal:
    """Build a deterministic signal: the same base and target always give the same id."""
    base = dict(previous or {})
    payload = json.dumps(
        {
            "strategy_id": snapshot.strategy_id,
            "as_of": snapshot.as_of,
            "base": _rounded(base),
            "target": _rounded(snapshot.weights),
        },
        sort_keys=True,
    )
    return Signal(
        signal_id=hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
        strategy_id=snapshot.strategy_id,
        as_of=snapshot.as_of,
        changes=diff_weights(base, snapshot.weights),
        target=dict(snapshot.weights),
        prices=dict(snapshot.prices),
    )


__all__ = [
    "FUTURES_SUFFIXES",
    "WEIGHT_TOLERANCE",
    "DeliveryResult",
    "Signal",
    "TargetSnapshot",
    "WeightChange",
    "build_signal",
    "diff_weights",
    "is_futures_symbol",
]
