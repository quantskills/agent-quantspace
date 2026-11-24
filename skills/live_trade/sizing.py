"""Convert target weights into whole trading units, and describe lot targets.

Percent targets are sized here (:func:`size_targets`). Automatic futures orders hold the
lots a weight was sized to until the weight or the capital changes (:class:`SizedLots`).
Lot targets are never resized: a futures lot is one contract and a stock or fund lot
:data:`SHARES_PER_LOT` shares; :func:`describe_lots` only works out their value for messages.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from skills.backtest.units import SHARES_PER_LOT

from .contracts import WEIGHT_TOLERANCE, is_futures_symbol
from .ledger import validate_strategy_id, write_json_atomic


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


@dataclass(frozen=True)
class LotsTarget:
    """A lot target as messages show it.

    ``shares`` is the shares of a stock or fund target (lots x 100), None for futures;
    ``notional`` the absolute value at the reference price (None without a price, or a
    futures multiplier); ``share_of_capital`` the signed value over the capital, when given.
    """

    symbol: str
    lots: int
    shares: int | None
    price: float | None
    notional: float | None
    share_of_capital: float | None

    @property
    def units(self) -> int:
        """Contracts of a future, shares of a stock or fund."""
        return self.lots if self.shares is None else self.shares


def describe_lots(
    lots: Mapping[str, float],
    prices: Mapping[str, float],
    *,
    multipliers: Mapping[str, float] | None = None,
    capital: float | None = None,
) -> dict[str, LotsTarget]:
    """Shares, value and (with ``capital``) share of capital of whole-lot targets.

    Nothing is rounded or checked against a cap here; the value is left out when the price
    or a futures multiplier is missing, since it only informs the message.
    """
    multipliers = multipliers or {}
    described = {}
    for symbol in sorted(lots):
        count = int(round(float(lots[symbol])))
        futures = is_futures_symbol(symbol)
        price = prices.get(symbol)
        per_lot = multipliers.get(symbol) if futures else SHARES_PER_LOT
        notional = share = None
        if price is not None and per_lot is not None:
            value = count * float(price) * float(per_lot)
            notional = abs(value)
            share = value / capital if capital else None
        described[symbol] = LotsTarget(
            symbol=symbol,
            lots=count,
            shares=None if futures else count * SHARES_PER_LOT,
            price=None if price is None else float(price),
            notional=notional,
            share_of_capital=share,
        )
    return described


SIZED_LOTS_FILE = "sized_lots.json"


class SizedLots:
    """The lots each percent target was sized to, held until its weight or the capital changes.

    Automatic futures orders of a percent strategy size a weight into whole contracts only
    when it changes (beyond :data:`~skills.live_trade.contracts.WEIGHT_TOLERANCE` from the
    last run), when the symbol is new here, or when ``capital`` differs from the capital of
    the record; otherwise they keep the lots, whatever the price does since. This is how
    :func:`skills.backtest.percent_to_lots` sizes, so the lots backtest of a percent strategy
    is the account the orders build. The lots belong to the continuous symbol, so a roll
    carries them to the new contract unchanged. They are a target, not a position: partial
    fills and manual trades are brought back to them by the next run.

    Stored in ``<data_root>/live/<strategy_id>/sized_lots.json``::

        {"version": 1, "strategy_id": "...", "capital": 100000.0,
         "symbols": {"RB_DOMINANT.SHF": {"weight": 1.0, "lots": 3, "price": 3300.0,
                                         "sized_at": "2026-11-23T14:50:00"}}}

    ``weight`` is the weight of the last run, ``price`` and ``sized_at`` the price and the
    run the lots were sized at. Delete the file to size everything again on the next run.
    """

    def __init__(self, strategy_id: str, data_root: str | Path | None = None):
        from skills.store.workspace import resolve_workspace_paths

        self.strategy_id = validate_strategy_id(strategy_id)
        root = resolve_workspace_paths(data_root=data_root).data_root
        self.path = root / "live" / self.strategy_id / SIZED_LOTS_FILE

    def read(self) -> dict:
        """The record, or an empty one when there is none."""
        if not self.path.exists():
            return {"version": 1, "strategy_id": self.strategy_id, "capital": None, "symbols": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def hold(
        self,
        weights: Mapping[str, float],
        prices: Mapping[str, float],
        *,
        capital: float | None,
        multipliers: Mapping[str, float] | None = None,
        as_of: date | datetime,
    ) -> dict[str, int]:
        """Lots per symbol of ``weights`` (the full target, zeros included); writes the record.

        Changed, new, and (after a ``capital`` change) all symbols are sized with
        :func:`size_targets` at ``prices``, rounded toward zero; a zero weight is 0 lots and
        needs no price. Symbols missing from ``weights`` leave the record. Sizing errors
        (no ``capital``, a missing price or multiplier) raise and leave the record as it was.
        """
        if capital is None:
            raise ValueError("--capital is required to size orders")
        if not math.isfinite(capital) or capital <= 0:
            raise ValueError("capital must be a positive finite number")
        record = self.read()
        held = record.get("symbols", {})
        same_capital = record.get("capital") == float(capital)
        weights = {symbol: float(value) for symbol, value in weights.items()}
        resize = [
            symbol
            for symbol, weight in weights.items()
            if not same_capital
            or symbol not in held
            or abs(weight - float(held[symbol]["weight"])) > WEIGHT_TOLERANCE
        ]
        nonzero = {s: weights[s] for s in resize if abs(weights[s]) > WEIGHT_TOLERANCE}
        sized = (
            {
                item.symbol: item
                for item in size_targets(
                    nonzero, capital, prices, multipliers=dict(multipliers or {}), rounding="down"
                )
            }
            if nonzero
            else {}
        )
        stamp = as_of.isoformat()
        symbols = {}
        for symbol in sorted(weights):
            if symbol not in resize:
                symbols[symbol] = {**held[symbol], "weight": weights[symbol]}
                continue
            price = prices.get(symbol)
            symbols[symbol] = {
                "weight": weights[symbol],
                "lots": sized[symbol].units if symbol in sized else 0,
                "price": float(price) if price is not None and math.isfinite(price) else None,
                "sized_at": stamp,
            }
        write_json_atomic(
            self.path,
            {
                "version": 1,
                "strategy_id": self.strategy_id,
                "capital": float(capital),
                "symbols": symbols,
            },
        )
        return {symbol: int(entry["lots"]) for symbol, entry in symbols.items()}

    def clear(self) -> None:
        """Forget every sized lot, so the next percent run sizes everything at its prices."""
        self.path.unlink(missing_ok=True)


__all__ = [
    "SIZED_LOTS_FILE",
    "LotsTarget",
    "SizedLots",
    "SizedTarget",
    "SizingLimitError",
    "describe_lots",
    "size_targets",
]
