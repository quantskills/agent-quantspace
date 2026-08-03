from __future__ import annotations

from typing import Protocol

import pandas as pd


class CrossSectionalBacktestResult(Protocol):
    """State exposed by a cross-sectional backtest for exit analysis."""

    metrics: dict
    weights_df: pd.DataFrame
    result_df: pd.DataFrame
