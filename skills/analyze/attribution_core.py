"""Core attribution helpers for ETF rotation research."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

DATE_COL = "date"
SYMBOL_COL = "symbol"
STRATEGY_COL = "strategy_id"
CATEGORY_COL = "category"
DEFAULT_STRATEGY_ID = "default"
CASH_CATEGORY = "cash"


def normalize_weight_ledger(
    weights: pd.DataFrame,
    strategy_id: str | None,
    weight_col: str = "weight",
) -> pd.DataFrame:
    """Convert a wide or long weight ledger into date/strategy/symbol/weight rows."""
    _require_dataframe(weights, "weights")

    if _is_long_weight_ledger(weights):
        selected_weight_col = _choose_column(
            weights,
            weight_col,
            fallback_cols=("weight", "w_exec", "w_target"),
            df_name="weights",
        )
        out = weights[[DATE_COL, SYMBOL_COL, selected_weight_col]].copy()
        out = out.rename(columns={selected_weight_col: "weight"})
        out[STRATEGY_COL] = _resolve_strategy_id(weights, strategy_id)
    else:
        out = _normalize_wide_weights(weights, strategy_id)

    out = out[[DATE_COL, STRATEGY_COL, SYMBOL_COL, "weight"]]
    out = out.dropna(subset=["weight"])
    return out.sort_values([DATE_COL, STRATEGY_COL, SYMBOL_COL]).reset_index(drop=True)


def compute_symbol_pnl(
    executed_weights: pd.DataFrame,
    symbol_returns: pd.DataFrame,
    cost: pd.DataFrame | None = None,
    *,
    weight_col: str = "w_exec",
    return_col: str = "ret_1d_fwd",
    cost_col: str = "cost_cash",
    strategy_id: str | None = None,
    portfolio_returns: pd.DataFrame | None = None,
    gross_return_col: str = "gross_return",
    net_return_col: str = "net_return",
    return_reconcile: bool = False,
) -> pd.DataFrame:
    """Compute symbol-level gross, cost, and net return contributions."""
    _require_dataframe(executed_weights, "executed_weights")
    _require_dataframe(symbol_returns, "symbol_returns")
    _require_columns(symbol_returns, (DATE_COL, SYMBOL_COL, return_col), "symbol_returns")

    weights = _prepare_weight_frame(
        executed_weights,
        weight_col=weight_col,
        output_col="w_exec",
        df_name="executed_weights",
        strategy_id=strategy_id,
    )
    returns = symbol_returns[[DATE_COL, SYMBOL_COL, return_col]].copy()
    returns = returns.drop_duplicates(subset=[DATE_COL, SYMBOL_COL], keep="last")

    pnl = weights.merge(returns, on=[DATE_COL, SYMBOL_COL], how="left")
    _raise_if_missing_values(
        pnl,
        return_col,
        "symbol_returns does not contain returns for executed weight rows",
    )

    costs = _prepare_cost_frame(
        executed_weights,
        cost=cost,
        cost_col=cost_col,
        strategy_id=strategy_id,
    )
    if costs is None:
        pnl["cost_contrib"] = 0.0
    else:
        merge_cols = [DATE_COL, SYMBOL_COL]
        if STRATEGY_COL in costs.columns:
            merge_cols = [DATE_COL, STRATEGY_COL, SYMBOL_COL]
        pnl = pnl.merge(costs, on=merge_cols, how="left")
        pnl["cost_contrib"] = pnl["cost_contrib"].fillna(0.0)

    pnl["gross_contrib"] = pnl["w_exec"] * pnl[return_col]
    pnl[cost_col] = pnl["cost_contrib"]
    pnl["net_contrib"] = pnl["gross_contrib"] - pnl["cost_contrib"]

    columns = [
        DATE_COL,
        STRATEGY_COL,
        SYMBOL_COL,
        "w_exec",
        return_col,
        cost_col,
        "gross_contrib",
        "cost_contrib",
        "net_contrib",
    ]
    pnl = pnl[columns].sort_values([DATE_COL, STRATEGY_COL, SYMBOL_COL]).reset_index(drop=True)

    if return_reconcile:
        return _daily_return_reconcile(
            pnl,
            portfolio_returns=portfolio_returns,
            gross_return_col=gross_return_col,
            net_return_col=net_return_col,
        )
    return pnl


def compute_category_pnl(symbol_pnl: pd.DataFrame, category_map: pd.DataFrame) -> pd.DataFrame:
    """Aggregate symbol-level PnL into category-level weights and contributions."""
    _require_dataframe(symbol_pnl, "symbol_pnl")
    _require_dataframe(category_map, "category_map")
    _require_columns(
        symbol_pnl,
        (DATE_COL, SYMBOL_COL, "gross_contrib", "net_contrib"),
        "symbol_pnl",
    )
    _require_columns(category_map, (SYMBOL_COL, CATEGORY_COL), "category_map")

    pnl = symbol_pnl.copy()
    if STRATEGY_COL not in pnl.columns:
        pnl[STRATEGY_COL] = DEFAULT_STRATEGY_ID
    weight_col = _choose_column(
        pnl,
        "w_exec",
        fallback_cols=("weight",),
        df_name="symbol_pnl",
    )
    if "cost_contrib" not in pnl.columns:
        pnl["cost_contrib"] = pnl["gross_contrib"] - pnl["net_contrib"]

    category_lookup = category_map[[SYMBOL_COL, CATEGORY_COL]].drop_duplicates(SYMBOL_COL)
    merged = pnl.merge(category_lookup, on=SYMBOL_COL, how="left")
    _raise_if_missing_values(
        merged,
        CATEGORY_COL,
        "category_map does not contain categories for symbol_pnl rows",
    )

    grouped = (
        merged.groupby([DATE_COL, STRATEGY_COL, CATEGORY_COL], as_index=False)
        .agg(
            weight=(weight_col, "sum"),
            gross_contrib=("gross_contrib", "sum"),
            cost_contrib=("cost_contrib", "sum"),
            net_contrib=("net_contrib", "sum"),
        )
        .sort_values([DATE_COL, STRATEGY_COL, CATEGORY_COL])
        .reset_index(drop=True)
    )
    return grouped


def make_category_neutral_benchmark(
    symbol_returns: pd.DataFrame,
    category_map: pd.DataFrame,
    eligibility: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Create category-equal and within-category-equal benchmark weights."""
    _require_dataframe(symbol_returns, "symbol_returns")
    _require_dataframe(category_map, "category_map")
    _require_columns(symbol_returns, (DATE_COL, SYMBOL_COL), "symbol_returns")
    _require_columns(category_map, (SYMBOL_COL, CATEGORY_COL), "category_map")

    universe = symbol_returns[[DATE_COL, SYMBOL_COL]].drop_duplicates().copy()
    category_lookup = category_map[[SYMBOL_COL, CATEGORY_COL]].drop_duplicates(SYMBOL_COL)
    universe = universe.merge(category_lookup, on=SYMBOL_COL, how="left")
    _raise_if_missing_values(
        universe,
        CATEGORY_COL,
        "category_map does not contain categories for symbol_returns rows",
    )

    if eligibility is not None:
        universe = _apply_eligibility(universe, eligibility)

    if universe.empty:
        return pd.DataFrame(columns=[DATE_COL, SYMBOL_COL, CATEGORY_COL, "weight"])

    universe["category_count"] = universe.groupby(DATE_COL)[CATEGORY_COL].transform("nunique")
    universe["symbol_count_in_category"] = universe.groupby([DATE_COL, CATEGORY_COL])[
        SYMBOL_COL
    ].transform("nunique")
    universe["weight"] = 1.0 / universe["category_count"] / universe["symbol_count_in_category"]

    return (
        universe[[DATE_COL, SYMBOL_COL, CATEGORY_COL, "weight"]]
        .sort_values([DATE_COL, CATEGORY_COL, SYMBOL_COL])
        .reset_index(drop=True)
    )


def compute_brinson_attribution(
    portfolio_weights: pd.DataFrame,
    benchmark_weights: pd.DataFrame,
    symbol_returns: pd.DataFrame,
    category_map: pd.DataFrame,
) -> pd.DataFrame:
    """Compute daily category Brinson-Fachler allocation, selection, and interaction."""
    _require_dataframe(portfolio_weights, "portfolio_weights")
    _require_dataframe(benchmark_weights, "benchmark_weights")
    _require_dataframe(symbol_returns, "symbol_returns")
    _require_dataframe(category_map, "category_map")
    _require_columns(symbol_returns, (DATE_COL, SYMBOL_COL, "ret_1d_fwd"), "symbol_returns")
    _require_columns(category_map, (SYMBOL_COL, CATEGORY_COL), "category_map")

    portfolio = _prepare_weight_frame(
        portfolio_weights,
        weight_col="w_exec",
        output_col="portfolio_weight",
        df_name="portfolio_weights",
    )
    benchmark = _prepare_benchmark_weight_frame(benchmark_weights)

    returns = symbol_returns[[DATE_COL, SYMBOL_COL, "ret_1d_fwd"]].drop_duplicates(
        subset=[DATE_COL, SYMBOL_COL],
        keep="last",
    )
    category_lookup = category_map[[SYMBOL_COL, CATEGORY_COL]].drop_duplicates(SYMBOL_COL)

    portfolio_positions = _merge_weights_returns_categories(
        portfolio,
        returns,
        category_lookup,
        weight_col="portfolio_weight",
        df_name="portfolio_weights",
    )
    benchmark_positions = _merge_weights_returns_categories(
        benchmark,
        returns,
        category_lookup,
        weight_col="benchmark_weight",
        df_name="benchmark_weights",
    )

    portfolio_category = _category_returns(
        portfolio_positions,
        group_cols=[DATE_COL, STRATEGY_COL, CATEGORY_COL],
        weight_col="portfolio_weight",
        contrib_col="portfolio_contrib",
        return_col="portfolio_category_return",
    )
    benchmark_category = _category_returns(
        benchmark_positions,
        group_cols=[DATE_COL, CATEGORY_COL],
        weight_col="benchmark_weight",
        contrib_col="benchmark_contrib",
        return_col="benchmark_category_return",
    )

    strategy_dates = portfolio[[DATE_COL, STRATEGY_COL]].drop_duplicates()
    benchmark_dates = benchmark[[DATE_COL]].drop_duplicates()
    missing_benchmark_dates = _missing_key_rows(
        strategy_dates[[DATE_COL]], benchmark_dates, [DATE_COL]
    )
    if not missing_benchmark_dates.empty:
        raise ValueError("benchmark_weights is missing dates present in portfolio_weights")

    category_dates = pd.concat(
        [
            portfolio_category[[DATE_COL, CATEGORY_COL]],
            benchmark_category[[DATE_COL, CATEGORY_COL]],
        ],
        ignore_index=True,
    ).drop_duplicates()

    base = strategy_dates.merge(category_dates, on=DATE_COL, how="inner")
    combined = base.merge(
        portfolio_category,
        on=[DATE_COL, STRATEGY_COL, CATEGORY_COL],
        how="left",
    ).merge(
        benchmark_category,
        on=[DATE_COL, CATEGORY_COL],
        how="left",
    )
    combined = _add_cash_rows_for_reconciliation(combined)

    numeric_fill_cols = [
        "portfolio_weight",
        "portfolio_contrib",
        "benchmark_weight",
        "benchmark_contrib",
    ]
    combined[numeric_fill_cols] = combined[numeric_fill_cols].fillna(0.0)

    daily = combined.groupby([DATE_COL, STRATEGY_COL], as_index=False).agg(
        portfolio_return=("portfolio_contrib", "sum"),
        benchmark_return=("benchmark_contrib", "sum"),
        portfolio_total_weight=("portfolio_weight", "sum"),
        benchmark_total_weight=("benchmark_weight", "sum"),
    )
    combined = combined.merge(daily, on=[DATE_COL, STRATEGY_COL], how="left")

    combined["benchmark_category_return"] = np.where(
        combined["benchmark_weight"].abs() > 0.0,
        combined["benchmark_contrib"] / combined["benchmark_weight"],
        combined["benchmark_return"],
    )
    combined["portfolio_category_return"] = np.where(
        combined["portfolio_weight"].abs() > 0.0,
        combined["portfolio_contrib"] / combined["portfolio_weight"],
        combined["benchmark_category_return"],
    )

    active_weight = combined["portfolio_weight"] - combined["benchmark_weight"]
    excess_category_return = (
        combined["portfolio_category_return"] - combined["benchmark_category_return"]
    )
    combined["allocation"] = active_weight * (
        combined["benchmark_category_return"] - combined["benchmark_return"]
    )
    combined["selection"] = combined["benchmark_weight"] * excess_category_return
    combined["interaction"] = active_weight * excess_category_return
    combined["total_effect"] = (
        combined["allocation"] + combined["selection"] + combined["interaction"]
    )
    combined["active_contrib"] = combined["portfolio_contrib"] - combined["benchmark_contrib"]

    daily_totals = (
        combined.groupby([DATE_COL, STRATEGY_COL], as_index=False)
        .agg(daily_attribution_total=("total_effect", "sum"))
        .merge(daily, on=[DATE_COL, STRATEGY_COL], how="left")
    )
    daily_totals["daily_active_return"] = (
        daily_totals["portfolio_return"] - daily_totals["benchmark_return"]
    )
    daily_totals["reconcile_residual"] = (
        daily_totals["daily_active_return"] - daily_totals["daily_attribution_total"]
    )

    combined = combined.merge(
        daily_totals[
            [
                DATE_COL,
                STRATEGY_COL,
                "daily_active_return",
                "daily_attribution_total",
                "reconcile_residual",
            ]
        ],
        on=[DATE_COL, STRATEGY_COL],
        how="left",
    )

    columns = [
        DATE_COL,
        STRATEGY_COL,
        CATEGORY_COL,
        "portfolio_weight",
        "benchmark_weight",
        "portfolio_category_return",
        "benchmark_category_return",
        "portfolio_contrib",
        "benchmark_contrib",
        "active_contrib",
        "allocation",
        "selection",
        "interaction",
        "total_effect",
        "portfolio_return",
        "benchmark_return",
        "daily_active_return",
        "daily_attribution_total",
        "reconcile_residual",
    ]
    return (
        combined[columns].sort_values([DATE_COL, STRATEGY_COL, CATEGORY_COL]).reset_index(drop=True)
    )


def summarize_brinson(
    brinson_daily: pd.DataFrame,
    group_cols: Sequence[str] = (STRATEGY_COL, CATEGORY_COL),
) -> pd.DataFrame:
    """Summarize daily Brinson rows across the requested grouping columns."""
    _require_dataframe(brinson_daily, "brinson_daily")
    group_cols = tuple(group_cols)
    _require_columns(brinson_daily, group_cols, "brinson_daily")
    _require_columns(
        brinson_daily,
        (
            "portfolio_weight",
            "benchmark_weight",
            "allocation",
            "selection",
            "interaction",
            "total_effect",
        ),
        "brinson_daily",
    )

    summary = (
        brinson_daily.groupby(list(group_cols), as_index=False)
        .agg(
            avg_portfolio_weight=("portfolio_weight", "mean"),
            avg_benchmark_weight=("benchmark_weight", "mean"),
            max_portfolio_weight=("portfolio_weight", "max"),
            brinson_allocation=("allocation", "sum"),
            brinson_selection=("selection", "sum"),
            brinson_interaction=("interaction", "sum"),
            brinson_total=("total_effect", "sum"),
            n_days=(DATE_COL, "nunique")
            if DATE_COL in brinson_daily.columns
            else ("total_effect", "size"),
        )
        .sort_values(list(group_cols))
        .reset_index(drop=True)
    )
    summary["period"] = "full"
    ordered_cols = list(group_cols) + [
        "period",
        "avg_portfolio_weight",
        "avg_benchmark_weight",
        "max_portfolio_weight",
        "brinson_allocation",
        "brinson_selection",
        "brinson_interaction",
        "brinson_total",
        "n_days",
    ]
    return summary[ordered_cols]


def _require_dataframe(value: Any, name: str) -> None:
    if not isinstance(value, pd.DataFrame):
        raise ValueError(f"{name} must be a pandas DataFrame")


def _require_columns(df: pd.DataFrame, required_cols: Sequence[str], df_name: str) -> None:
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"{df_name} is missing required columns: {', '.join(missing)}")


def _is_long_weight_ledger(weights: pd.DataFrame) -> bool:
    return DATE_COL in weights.columns and SYMBOL_COL in weights.columns


def _choose_column(
    df: pd.DataFrame,
    preferred_col: str,
    *,
    fallback_cols: Sequence[str],
    df_name: str,
) -> str:
    if preferred_col in df.columns:
        return preferred_col
    for col in fallback_cols:
        if col in df.columns:
            return col
    expected = ", ".join((preferred_col, *fallback_cols))
    raise ValueError(f"{df_name} is missing required columns: {expected}")


def _resolve_strategy_id(weights: pd.DataFrame, strategy_id: str | None) -> Any:
    if STRATEGY_COL in weights.columns and strategy_id is None:
        return weights[STRATEGY_COL].to_numpy()
    if strategy_id is not None:
        return strategy_id
    return DEFAULT_STRATEGY_ID


def _normalize_wide_weights(weights: pd.DataFrame, strategy_id: str | None) -> pd.DataFrame:
    frame = weights.copy()
    reset = frame.reset_index()
    date_col = _detect_date_column(reset)
    excluded_cols = {date_col, STRATEGY_COL}
    if (
        date_col != "index"
        and "index" in reset.columns
        and weights.index.name is None
        and isinstance(weights.index, pd.RangeIndex)
    ):
        excluded_cols.add("index")
    value_cols = [col for col in reset.columns if col not in excluded_cols]
    if not value_cols:
        raise ValueError("weights does not contain symbol weight columns")

    out = reset.melt(
        id_vars=[date_col],
        value_vars=value_cols,
        var_name=SYMBOL_COL,
        value_name="weight",
    )
    out = out.rename(columns={date_col: DATE_COL})
    out[DATE_COL] = pd.to_datetime(out[DATE_COL])
    out[STRATEGY_COL] = strategy_id if strategy_id is not None else DEFAULT_STRATEGY_ID
    return out


def _detect_date_column(reset_frame: pd.DataFrame) -> str:
    if DATE_COL in reset_frame.columns:
        return DATE_COL
    if "eob" in reset_frame.columns:
        return "eob"
    if "index" in reset_frame.columns:
        return "index"
    return reset_frame.columns[0]


def _prepare_weight_frame(
    weights: pd.DataFrame,
    *,
    weight_col: str,
    output_col: str,
    df_name: str,
    strategy_id: str | None = None,
) -> pd.DataFrame:
    if _is_long_weight_ledger(weights):
        selected_weight_col = _choose_column(
            weights,
            weight_col,
            fallback_cols=("weight", "w_exec", "w_target"),
            df_name=df_name,
        )
        out = weights[[DATE_COL, SYMBOL_COL, selected_weight_col]].copy()
        out = out.rename(columns={selected_weight_col: output_col})
        out[STRATEGY_COL] = _resolve_strategy_id(weights, strategy_id)
    else:
        out = normalize_weight_ledger(weights, strategy_id=strategy_id, weight_col="weight")
        out = out.rename(columns={"weight": output_col})

    return (
        out[[DATE_COL, STRATEGY_COL, SYMBOL_COL, output_col]]
        .dropna(subset=[output_col])
        .groupby([DATE_COL, STRATEGY_COL, SYMBOL_COL], as_index=False)[output_col]
        .sum()
    )


def _prepare_benchmark_weight_frame(benchmark_weights: pd.DataFrame) -> pd.DataFrame:
    if _is_long_weight_ledger(benchmark_weights):
        selected_weight_col = _choose_column(
            benchmark_weights,
            "weight",
            fallback_cols=("w_bench", "w_benchmark", "w_exec"),
            df_name="benchmark_weights",
        )
        out = benchmark_weights[[DATE_COL, SYMBOL_COL, selected_weight_col]].copy()
        out = out.rename(columns={selected_weight_col: "benchmark_weight"})
    else:
        out = normalize_weight_ledger(
            benchmark_weights,
            strategy_id="benchmark",
            weight_col="weight",
        ).rename(columns={"weight": "benchmark_weight"})
        out = out[[DATE_COL, SYMBOL_COL, "benchmark_weight"]]

    return (
        out[[DATE_COL, SYMBOL_COL, "benchmark_weight"]]
        .dropna(subset=["benchmark_weight"])
        .groupby([DATE_COL, SYMBOL_COL], as_index=False)["benchmark_weight"]
        .sum()
    )


def _prepare_cost_frame(
    executed_weights: pd.DataFrame,
    *,
    cost: pd.DataFrame | None,
    cost_col: str,
    strategy_id: str | None,
) -> pd.DataFrame | None:
    if cost is None and cost_col not in executed_weights.columns:
        return None

    if cost is None:
        source = executed_weights
        df_name = "executed_weights"
    else:
        _require_dataframe(cost, "cost")
        source = cost
        df_name = "cost"

    _require_columns(source, (DATE_COL, SYMBOL_COL, cost_col), df_name)
    cols = [DATE_COL, SYMBOL_COL, cost_col]
    out = source[cols].copy()
    if STRATEGY_COL in source.columns:
        out[STRATEGY_COL] = _resolve_strategy_id(source, strategy_id)
        group_cols = [DATE_COL, STRATEGY_COL, SYMBOL_COL]
    else:
        group_cols = [DATE_COL, SYMBOL_COL]

    out = out.rename(columns={cost_col: "cost_contrib"})
    return out.groupby(group_cols, as_index=False)["cost_contrib"].sum()


def _daily_return_reconcile(
    symbol_pnl: pd.DataFrame,
    *,
    portfolio_returns: pd.DataFrame | None,
    gross_return_col: str,
    net_return_col: str,
) -> pd.DataFrame:
    daily = (
        symbol_pnl.groupby([DATE_COL, STRATEGY_COL], as_index=False)
        .agg(
            gross_return=("gross_contrib", "sum"),
            cost_contrib=("cost_contrib", "sum"),
            net_return=("net_contrib", "sum"),
            symbol_net_contrib=("net_contrib", "sum"),
        )
        .sort_values([DATE_COL, STRATEGY_COL])
        .reset_index(drop=True)
    )

    if portfolio_returns is None:
        daily["reconcile_residual"] = 0.0
        return daily

    _require_dataframe(portfolio_returns, "portfolio_returns")
    _require_columns(portfolio_returns, (DATE_COL,), "portfolio_returns")
    available_return_cols = [
        col for col in (gross_return_col, net_return_col) if col in portfolio_returns.columns
    ]
    if not available_return_cols:
        raise ValueError(
            f"portfolio_returns is missing required columns: {gross_return_col} or {net_return_col}"
        )

    merge_cols = [DATE_COL]
    if STRATEGY_COL in portfolio_returns.columns:
        merge_cols.append(STRATEGY_COL)
    reported_cols = merge_cols + available_return_cols
    reported = portfolio_returns[reported_cols].copy()
    rename_map = {
        gross_return_col: "reported_gross_return",
        net_return_col: "reported_net_return",
    }
    reported = reported.rename(columns=rename_map)
    daily = daily.merge(reported, on=merge_cols, how="left")

    if "reported_net_return" in daily.columns:
        daily["reconcile_residual"] = daily["net_return"] - daily["reported_net_return"]
    else:
        daily["reconcile_residual"] = daily["gross_return"] - daily["reported_gross_return"]
    return daily


def _apply_eligibility(universe: pd.DataFrame, eligibility: pd.DataFrame) -> pd.DataFrame:
    _require_dataframe(eligibility, "eligibility")
    _require_columns(eligibility, (DATE_COL, SYMBOL_COL), "eligibility")
    eligibility_col = _find_first_existing(eligibility, ("eligible", "is_eligible", "is_tradable"))
    if eligibility_col is None:
        eligible_rows = eligibility[[DATE_COL, SYMBOL_COL]].drop_duplicates().copy()
        eligible_rows["eligible"] = True
    else:
        eligible_rows = eligibility[[DATE_COL, SYMBOL_COL, eligibility_col]].copy()
        eligible_rows = eligible_rows.rename(columns={eligibility_col: "eligible"})

    filtered = universe.merge(eligible_rows, on=[DATE_COL, SYMBOL_COL], how="left")
    filtered["eligible"] = filtered["eligible"].fillna(False).astype(bool)
    return filtered.loc[filtered["eligible"]].drop(columns=["eligible"])


def _find_first_existing(df: pd.DataFrame, cols: Sequence[str]) -> str | None:
    for col in cols:
        if col in df.columns:
            return col
    return None


def _raise_if_missing_values(df: pd.DataFrame, col: str, message: str) -> None:
    if df[col].isna().any():
        missing_count = int(df[col].isna().sum())
        raise ValueError(f"{message}; missing {col} rows: {missing_count}")


def _merge_weights_returns_categories(
    weights: pd.DataFrame,
    returns: pd.DataFrame,
    category_lookup: pd.DataFrame,
    *,
    weight_col: str,
    df_name: str,
) -> pd.DataFrame:
    merged = weights.merge(returns, on=[DATE_COL, SYMBOL_COL], how="left")
    _raise_if_missing_values(
        merged,
        "ret_1d_fwd",
        f"symbol_returns does not contain returns for {df_name} rows",
    )
    merged = merged.merge(category_lookup, on=SYMBOL_COL, how="left")
    _raise_if_missing_values(
        merged,
        CATEGORY_COL,
        f"category_map does not contain categories for {df_name} rows",
    )
    merged[f"{weight_col}_return_contrib"] = merged[weight_col] * merged["ret_1d_fwd"]
    return merged


def _category_returns(
    positions: pd.DataFrame,
    *,
    group_cols: Sequence[str],
    weight_col: str,
    contrib_col: str,
    return_col: str,
) -> pd.DataFrame:
    raw_contrib_col = f"{weight_col}_return_contrib"
    grouped = positions.groupby(list(group_cols), as_index=False).agg(
        **{
            weight_col: (weight_col, "sum"),
            contrib_col: (raw_contrib_col, "sum"),
        }
    )
    grouped[return_col] = np.where(
        grouped[weight_col].abs() > 0.0,
        grouped[contrib_col] / grouped[weight_col],
        np.nan,
    )
    return grouped


def _missing_key_rows(
    left: pd.DataFrame,
    right: pd.DataFrame,
    keys: Sequence[str],
) -> pd.DataFrame:
    probe = left.drop_duplicates().merge(
        right.drop_duplicates(),
        on=list(keys),
        how="left",
        indicator=True,
    )
    return probe.loc[probe["_merge"] == "left_only", list(keys)]


def _add_cash_rows_for_reconciliation(combined: pd.DataFrame) -> pd.DataFrame:
    working = combined.copy()
    numeric_cols = [
        "portfolio_weight",
        "portfolio_contrib",
        "portfolio_category_return",
        "benchmark_weight",
        "benchmark_contrib",
        "benchmark_category_return",
    ]
    for col in numeric_cols:
        if col not in working.columns:
            working[col] = np.nan

    totals = (
        working.groupby([DATE_COL, STRATEGY_COL], as_index=False)
        .agg(
            portfolio_total_weight=("portfolio_weight", "sum"),
            benchmark_total_weight=("benchmark_weight", "sum"),
        )
        .fillna(0.0)
    )
    target_total = np.maximum.reduce(
        [
            totals["portfolio_total_weight"].to_numpy(),
            totals["benchmark_total_weight"].to_numpy(),
            np.ones(len(totals), dtype=float),
        ]
    )
    totals["portfolio_cash_weight"] = target_total - totals["portfolio_total_weight"]
    totals["benchmark_cash_weight"] = target_total - totals["benchmark_total_weight"]
    cash = totals.loc[
        (totals["portfolio_cash_weight"].abs() > 1e-12)
        | (totals["benchmark_cash_weight"].abs() > 1e-12),
        [DATE_COL, STRATEGY_COL, "portfolio_cash_weight", "benchmark_cash_weight"],
    ].copy()
    if cash.empty:
        return working

    cash[CATEGORY_COL] = CASH_CATEGORY
    cash["portfolio_weight"] = cash["portfolio_cash_weight"]
    cash["benchmark_weight"] = cash["benchmark_cash_weight"]
    cash["portfolio_contrib"] = 0.0
    cash["benchmark_contrib"] = 0.0
    cash["portfolio_category_return"] = np.nan
    cash["benchmark_category_return"] = np.nan
    cash = cash[
        [
            DATE_COL,
            STRATEGY_COL,
            CATEGORY_COL,
            "portfolio_weight",
            "portfolio_contrib",
            "portfolio_category_return",
            "benchmark_weight",
            "benchmark_contrib",
            "benchmark_category_return",
        ]
    ]
    return pd.concat([working, cash], ignore_index=True)
