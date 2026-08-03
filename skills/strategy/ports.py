"""Minimal input ports used by strategy workflows in this repository."""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class MarketDataReader(Protocol):
    """Read explicit symbols into the standard ``(symbol, eob)`` panel."""

    def read_symbols(self, symbols: list[str], frequency: str = "1d") -> pd.DataFrame:
        """Return a sorted market-data panel for the requested symbols."""


__all__ = ["MarketDataReader"]
