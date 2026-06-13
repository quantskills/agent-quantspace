"""Parameter sensitivity analysis for factor functions."""

import logging
from collections.abc import Callable

import pandas as pd

logger = logging.getLogger(__name__)


def param_sweep(
    pool: str,
    factor_func: Callable,
    param_name: str,
    param_range: list,
    n: int = 5,
    base_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Sweep a single parameter of a factor function and compute IC/IR for each value.

    Parameters
    ----------
    pool : str
        Pool ID.
    factor_func : callable
        Factor function that takes (data, **kwargs) and returns factor values.
    param_name : str
        Name of the parameter to sweep.
    param_range : list
        Values to sweep.
    n : int
        Holding period for IC calculation.
    base_kwargs : dict, optional
        Other keyword arguments to pass to factor_func.

    Returns
    -------
    pd.DataFrame
        Columns: param_value, IC_mean, IC_std, IC_IR, t_stat
    """
    from skills.analyze.factor_analysis import full_stat
    from skills.store.data_manager import DataManager

    dm = DataManager()
    data = dm.load_pool_data(pool)
    close = data["close"].unstack("symbol")

    base_kwargs = base_kwargs or {}
    results = []

    for val in param_range:
        try:
            kwargs = {**base_kwargs, param_name: val}
            factor_vals = factor_func(data, **kwargs)

            if isinstance(factor_vals, pd.Series):
                factor_pivot = factor_vals.unstack("symbol")
            else:
                factor_pivot = factor_vals

            stat_df = close.stack().rename("close").to_frame()
            stat_df["fac_val"] = factor_pivot.stack()
            stat_df.index.names = ["eob", "symbol"]

            ic_stat, _, _, _ = full_stat(stat_df, n=n)

            results.append(
                {
                    "param_value": val,
                    "IC_mean": ic_stat.get("IC_mean"),
                    "IC_std": ic_stat.get("IC_std"),
                    "IC_IR": ic_stat.get("IC_IR"),
                    "t_stat": ic_stat.get("t_stat"),
                }
            )
        except Exception as e:
            logger.warning("param %s=%s failed: %s", param_name, val, e)
            continue

    if not results:
        return pd.DataFrame(columns=["param_value", "IC_mean", "IC_std", "IC_IR", "t_stat"])

    return pd.DataFrame(results)
