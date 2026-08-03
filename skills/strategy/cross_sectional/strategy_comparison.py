"""Cross-sectional strategy comparison via ``ModularBacktester``."""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def compare_strategies(
    data: pd.DataFrame,
    configs: list[dict],
    *,
    start: str | None = None,
    end: str | None = None,
    top_pct: float = 0.3,
    commission: float = 0.001,
    slippage_bp: float,
) -> pd.DataFrame:
    """Run factor configurations against an explicit panel and compare metrics."""
    from skills.strategy.cross_sectional.modular_backtester import ModularBacktester

    if data is None:
        raise ValueError("compare_strategies requires explicit data")

    if start:
        data = data.loc[data.index.get_level_values("eob") >= start]
    if end:
        data = data.loc[data.index.get_level_values("eob") <= end]

    results = []
    for config in configs:
        name = config.get("name", "unnamed")
        factor_configs = config.get("factor_configs", [])
        try:
            backtester = ModularBacktester(
                data=data,
                factor_configs=factor_configs,
                top_pct=top_pct,
                commission=commission,
                slippage_bp=slippage_bp,
            )
            backtester.run()
            metrics = backtester.metrics
            results.append(
                {
                    "strategy_name": name,
                    "total_return": metrics.get("total_return"),
                    "ann_return": metrics.get("ann_return"),
                    "max_drawdown": metrics.get("max_drawdown"),
                    "sharpe_ratio": metrics.get("sharpe_ratio"),
                    "calmar_ratio": metrics.get("calmar_ratio"),
                }
            )
        except Exception as exc:
            logger.warning("Strategy %s failed: %s", name, exc)
            results.append(
                {
                    "strategy_name": name,
                    "total_return": None,
                    "ann_return": None,
                    "max_drawdown": None,
                    "sharpe_ratio": None,
                    "calmar_ratio": None,
                }
            )

    return pd.DataFrame(results)


__all__ = ["compare_strategies"]
