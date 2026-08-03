"""Factor-frame construction helpers for modular backtesting."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .types import FactorConfig


@dataclass
class FactorFrameBuildResult:
    """Container for factor-frame outputs."""

    factor_df: pd.DataFrame
    factor_pivots: dict[str, pd.DataFrame]


@dataclass
class FactorFrameBuilder:
    """Build a long-form factor DataFrame while keeping wide pivots for ranking."""

    data: pd.DataFrame
    factor_configs: list[FactorConfig]

    def build(self) -> FactorFrameBuildResult:
        factor_df = self.data.copy()
        factor_pivots: dict[str, pd.DataFrame] = {}

        for config in self.factor_configs:
            func = config["func"]
            kwargs = config.get("kwargs", {})
            name = config.get("name", func.__name__)

            factor_series = self.data.groupby(level="symbol", group_keys=False).apply(
                lambda group, _func=func, _kwargs=kwargs: _func(group, **_kwargs)
            )
            factor_series = factor_series.reindex(self.data.index)
            factor_df[f"factor__{name}"] = factor_series
            factor_pivots[name] = factor_series.unstack(level="symbol")

        return FactorFrameBuildResult(
            factor_df=factor_df,
            factor_pivots=factor_pivots,
        )
