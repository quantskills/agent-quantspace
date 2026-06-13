"""Multi-strategy comparison via ModularBacktester."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def compare_strategies(
    pool: str,
    configs: list[dict],
    *,
    start: str | None = None,
    end: str | None = None,
    top_pct: float = 0.3,
    commission: float = 0.001,
    slippage_bp: float,
) -> pd.DataFrame:
    """Run multiple factor configurations through ModularBacktester and compare metrics.

    Parameters
    ----------
    pool : str
        Pool ID.
    configs : list[dict]
        Each dict has 'name' (str) and 'factor_configs' (list of factor config dicts).
    start, end : str, optional
        Date range filter.
    top_pct : float
        Top percentile for selection.
    commission : float
        Commission rate.
    slippage_bp : float
        Slippage in basis points. Execution cost assumptions must be explicit.

    Returns
    -------
    pd.DataFrame
        Columns: strategy_name, total_return, ann_return, max_drawdown, sharpe_ratio, calmar_ratio
    """
    from skills.store.data_manager import DataManager
    from strategies.cross_sectional.modular_backtester import ModularBacktester

    dm = DataManager()
    data = dm.load_pool_data(pool)

    if start:
        data = data.loc[data.index.get_level_values("eob") >= start]
    if end:
        data = data.loc[data.index.get_level_values("eob") <= end]

    results = []

    for cfg in configs:
        name = cfg.get("name", "unnamed")
        factor_configs = cfg.get("factor_configs", [])
        try:
            bt = ModularBacktester(
                data=data,
                factor_configs=factor_configs,
                top_pct=top_pct,
                commission=commission,
                slippage_bp=slippage_bp,
            )
            bt.run()
            metrics = bt.metrics if hasattr(bt, "metrics") else {}

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
        except Exception as e:
            logger.warning("Strategy %s failed: %s", name, e)
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
