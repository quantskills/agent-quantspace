"""Convert target weights into whole trading units (contracts or board lots)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .contracts import is_futures_symbol


class SizingLimitError(ValueError):
    """Raised when sized targets exceed a unit or notional cap; nothing is clipped."""

    def __init__(self, breaches: list[str]):
        super().__init__("Sized targets exceed limits: " + "; ".join(breaches))
        self.breaches = breaches


@dataclass(frozen=True)
class SizedTarget:
    symbol: str
    weight: float
    price: float
    multiplier: float
    lot_size: int
    raw_units: float
    units: int
    notional: float


def _round_lots(value: float, rounding: str) -> int:
    if rounding == "down":
        return math.trunc(value)
    if rounding == "nearest":
        return int(math.copysign(math.floor(abs(value) + 0.5), value))
    raise ValueError("rounding must be 'down' or 'nearest'")


def size_targets(
    weights: Mapping[str, float],
    capital: float,
    prices: Mapping[str, float],
    *,
    multipliers: Mapping[str, float] | None = None,
    lot_size: int = 100,
    rounding: Literal["down", "nearest"] = "down",
    max_units: int | None = None,
    max_notional: float | None = None,
) -> list[SizedTarget]:
    """Size each target weight as ``weight * capital / (price * multiplier)`` units.

    Futures always size in whole contracts and need an explicit multiplier; other symbols
    use ``multiplier`` 1 unless given and round to ``lot_size`` units. ``rounding="down"``
    truncates toward zero. Missing or invalid prices and multipliers raise instead of being
    guessed. Caps raise :class:`SizingLimitError` listing every breach.
    """
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("capital must be a positive finite number")
    if lot_size < 1:
        raise ValueError("lot_size must be at least 1")
    multipliers = multipliers or {}
    problems = []
    for symbol in sorted(weights):
        price = prices.get(symbol)
        if price is None or not math.isfinite(price) or price <= 0:
            problems.append(f"{symbol}: missing or invalid price")
        if is_futures_symbol(symbol) and symbol not in multipliers:
            problems.append(f"{symbol}: futures symbol needs a contract multiplier")
        multiplier = multipliers.get(symbol, 1.0)
        if not math.isfinite(multiplier) or multiplier <= 0:
            problems.append(f"{symbol}: invalid multiplier {multiplier}")
    if problems:
        raise ValueError("Cannot size targets: " + "; ".join(problems))

    sized, breaches = [], []
    for symbol in sorted(weights):
        weight = float(weights[symbol])
        price = float(prices[symbol])
        multiplier = float(multipliers.get(symbol, 1.0))
        lot = 1 if is_futures_symbol(symbol) else lot_size
        raw = weight * capital / (price * multiplier)
        units = _round_lots(raw / lot, rounding) * lot
        notional = abs(units) * price * multiplier
        if max_units is not None and abs(units) > max_units:
            breaches.append(f"{symbol}: {abs(units)} units > max {max_units}")
        if max_notional is not None and notional > max_notional:
            breaches.append(f"{symbol}: notional {notional:.2f} > max {max_notional:.2f}")
        sized.append(
            SizedTarget(
                symbol=symbol,
                weight=weight,
                price=price,
                multiplier=multiplier,
                lot_size=lot,
                raw_units=raw,
                units=units,
                notional=notional,
            )
        )
    if breaches:
        raise SizingLimitError(breaches)
    return sized


__all__ = ["SizedTarget", "SizingLimitError", "size_targets"]
