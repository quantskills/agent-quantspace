"""Batch factor screening across explicit panels and artifact namespaces."""

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
    namespace: str,
    n: int = 5,
    g: int = 5,
    top_k: int = 0,
    indicator_names: list[str] | None = None,
    persist: bool = True,
    data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Run full_stat for every discoverable indicator on explicit panel data.

    Parameters
    ----------
    namespace : str
        Artifact namespace used when persisting results.
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
        data/factor_test/{namespace}/ stays in sync.
    data : pd.DataFrame, optional
        Pre-loaded panel (MultiIndex symbol/eob). Required.

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
        raise ValueError(
            "screen_all_indicators requires explicit data. "
            "Load symbols with DataManager.read_symbols(...) and pass data=panel."
        )

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
                        namespace=namespace,
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
    namespaces: list[str] | None = None,
    n_list: list[int] | None = None,
    g: int = 5,
    indicator_names: list[str] | None = None,
    persist: bool = True,
    data_by_namespace: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Run factor screens across explicit namespace-to-panel mappings.

    Returns a combined DataFrame with an extra artifact namespace column.
    """
    if data_by_namespace is None:
        raise ValueError(
            "batch_evaluate requires explicit data_by_namespace. "
            "Load symbols with DataManager.read_symbols(...) for each namespace first."
        )
    if namespaces is None:
        namespaces = list(data_by_namespace)
    n_list = n_list or [1, 5, 20]

    rows: list[pd.DataFrame] = []
    for namespace in namespaces:
        panel = data_by_namespace.get(namespace)
        if panel is None:
            logger.warning("Namespace %s has no explicit data, skipping", namespace)
            continue
        if panel is None or panel.empty:
            logger.warning("Namespace %s empty, skipping", namespace)
            continue
        n_symbols = panel.index.get_level_values("symbol").nunique()
        if n_symbols < 3:
            logger.info("Namespace %s has %d symbols (<3), skipping", namespace, n_symbols)
            continue

        for n in n_list:
            ranking = screen_all_indicators(
                namespace=namespace,
                n=n,
                g=g,
                top_k=0,
                indicator_names=indicator_names,
                persist=persist,
                data=panel,
            )
            if not ranking.empty:
                ranking.insert(0, "namespace", namespace)
                rows.append(ranking)

    if not rows:
        return pd.DataFrame(columns=["namespace", *_SUMMARY_COLUMNS])
    combined = pd.concat(rows, ignore_index=True)
    return combined
