"""Batch factor screening across all indicators for a pool."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


_SUMMARY_COLUMNS = [
    "indicator",
    "factor_id",
    "n",
    "g",
    "IC_mean",
    "IC_std",
    "IC_IR",
    "IC_mean_last_1y",
    "IC_IR_LAST_1Y",
    "IC_positive_ratio",
    "t_stat",
    "p_value",
    "IC_count",
    "top_group_cum_return",
    "bottom_group_cum_return",
    "long_short_return",
    "mean_turnover",
]


def _build_stat_df(close: pd.Series, factor_series: pd.Series) -> pd.DataFrame:
    """Combine close+factor into the (eob, symbol) shape required by full_stat/IC_stat."""
    stat_df = pd.concat(
        [close.rename("close"), factor_series.rename("fac_val")],
        axis=1,
    ).dropna()
    stat_df.index.names = ["symbol", "eob"]
    return stat_df.swaplevel("symbol", "eob").sort_index()


def screen_all_indicators(
    pool: str,
    n: int = 5,
    g: int = 5,
    top_k: int = 0,
    indicator_names: list[str] | None = None,
    persist: bool = True,
    data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Run full_stat (silent) for every discoverable indicator on a pool and rank by |IC_IR|.

    Parameters
    ----------
    pool : str
        Pool ID (e.g. 'macro_asset_pool').
    n : int
        Holding period for IC calculation.
    g : int
        Number of layers for group_stat.
    top_k : int
        Return only top_k factors by |IC_IR|. 0 = return all.
    indicator_names : list[str], optional
        Subset of indicator names. None = all auto-discovered.
    persist : bool
        If True, call DataManager.save_factor_test() for each indicator so
        data/factor_test/{pool}/ stays in sync.
    data : pd.DataFrame, optional
        Pre-loaded panel (MultiIndex symbol/eob). If None, loaded via DataManager.

    Returns
    -------
    pd.DataFrame
        Ranking table with IC/group/turnover summary columns.
    """
    from skills.analyze.factor_analysis import full_stat
    from skills.compute.indicators import discover_indicators
    from skills.compute.wrappers import Factor
    from skills.store.data_manager import DataManager

    dm = DataManager()
    if data is None:
        data = dm.load_pool_data(pool)

    registry = discover_indicators()
    names = indicator_names or list(registry.keys())
    results = []

    for name in names:
        func = registry.get(name)
        if func is None:
            logger.warning("Indicator %s not found in registry, skipping", name)
            continue
        try:
            factor = Factor(func)
            factor_series = factor.calculate(data)
            stat_df = _build_stat_df(data["close"], factor_series)

            ic_stat, ic_series, group_return, turnover = full_stat(stat_df, n=n, g=g, plot=False)

            cum_returns = (
                (1 + group_return).prod() - 1 if not group_return.empty else pd.Series(dtype=float)
            )
            top_col = group_return.columns[-1] if not group_return.empty else None
            bot_col = group_return.columns[0] if not group_return.empty else None
            mean_turnover = (
                float(turnover.mean().mean())
                if turnover is not None and not turnover.empty
                else None
            )

            factor_id = factor.name
            row = {
                "indicator": name,
                "factor_id": factor_id,
                "n": n,
                "g": g,
                "IC_mean": ic_stat.get("IC_mean"),
                "IC_std": ic_stat.get("IC_std"),
                "IC_IR": ic_stat.get("IC_IR"),
                "IC_mean_last_1y": ic_stat.get("IC_mean_last_1y"),
                "IC_IR_LAST_1Y": ic_stat.get("IC_IR_LAST_1Y"),
                "IC_positive_ratio": ic_stat.get("IC_>0"),
                "t_stat": ic_stat.get("t_stat"),
                "p_value": ic_stat.get("p_value"),
                "IC_count": ic_stat.get("IC_count"),
                "top_group_cum_return": cum_returns.get(top_col) if top_col else None,
                "bottom_group_cum_return": cum_returns.get(bot_col) if bot_col else None,
                "long_short_return": (
                    cum_returns.get(top_col, 0) - cum_returns.get(bot_col, 0)
                    if top_col and bot_col
                    else None
                ),
                "mean_turnover": mean_turnover,
            }
            results.append(row)

            if persist:
                try:
                    dm.save_factor_test(
                        pool_id=pool,
                        factor_id=factor_id,
                        n=n,
                        g=g,
                        ic_stat=ic_stat,
                        ic_series=ic_series,
                        group_return=group_return,
                        turnover=turnover,
                    )
                except Exception as persist_err:
                    logger.warning("Persist failed for %s: %s", factor_id, persist_err)
        except Exception as e:
            logger.warning("Indicator %s failed: %s", name, e)
            continue

    if not results:
        return pd.DataFrame(columns=_SUMMARY_COLUMNS)

    df = pd.DataFrame(results)
    df = df.sort_values("IC_IR", key=lambda x: x.abs(), ascending=False)
    if top_k > 0:
        df = df.head(top_k)
    return df.reset_index(drop=True)


def batch_evaluate(
    pool_ids: list[str] | None = None,
    n_list: list[int] | None = None,
    g: int = 5,
    indicator_names: list[str] | None = None,
    persist: bool = True,
    generate_tearsheets: bool = False,
) -> pd.DataFrame:
    """Run screen_all_indicators across multiple pools and holding periods.

    Returns a combined DataFrame with an extra 'pool' column.
    """
    from skills.store.data_manager import DataManager

    dm = DataManager()
    if pool_ids is None:
        try:
            pools_df = dm.list_pools()
            pool_ids = (
                pools_df.loc[pools_df.get("frequency", "") == "1d", "pool_id"].tolist()
                if not pools_df.empty
                else []
            )
        except Exception:
            pool_ids = []
    n_list = n_list or [1, 5, 20]

    rows: list[pd.DataFrame] = []
    for pool in pool_ids:
        try:
            panel = dm.load_pool_data(pool)
        except Exception as e:
            logger.warning("Pool %s load failed, skipping: %s", pool, e)
            continue
        if panel is None or panel.empty:
            logger.warning("Pool %s empty, skipping", pool)
            continue
        n_symbols = panel.index.get_level_values("symbol").nunique()
        if n_symbols < 3:
            logger.info("Pool %s has %d symbols (<3), skipping", pool, n_symbols)
            continue

        for n in n_list:
            ranking = screen_all_indicators(
                pool=pool,
                n=n,
                g=g,
                top_k=0,
                indicator_names=indicator_names,
                persist=persist,
                data=panel,
            )
            if not ranking.empty:
                ranking.insert(0, "pool", pool)
                rows.append(ranking)

            if generate_tearsheets and not ranking.empty:
                try:
                    from skills.analyze.tearsheet import generate_pool_summary_report

                    generate_pool_summary_report(pool_id=pool)
                except Exception as e:
                    logger.warning("Summary report for %s failed: %s", pool, e)

    if not rows:
        return pd.DataFrame(columns=["pool", *_SUMMARY_COLUMNS])
    combined = pd.concat(rows, ignore_index=True)
    return combined
