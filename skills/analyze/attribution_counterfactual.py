"""Counterfactual, drawdown, and cost attribution helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

RETURN_COLUMNS = ("net_return", "return", "returns", "gross_return")
DATE_COLUMNS = ("date", "eob", "timestamp")
PNL_COLUMNS = (
    "pnl",
    "contribution",
    "log_contrib",
    "return_contribution",
    "net_pnl",
    "gross_pnl",
)
COST_COLUMNS = ("cost", "cost_cash", "cost_effect", "execution_cost", "cost_contrib")


def performance_metrics(
    returns: pd.Series | np.ndarray | list[float], annualization: int = 252
) -> dict[str, float]:
    """Compute standard scalar metrics from a periodic return stream."""
    r = _as_return_series(returns)
    total_return = _compounded_return(r)
    max_dd = _max_drawdown(r)
    ann_return = _annualized_return(r, annualization)
    sharpe = _sharpe(r, annualization)
    calmar = _calmar(ann_return, max_dd)
    return {
        "ann_return": ann_return,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "sharpe": sharpe,
        "worst_20d": _worst_window_return(r, window=20),
        "total_return": total_return,
    }


def summarize_counterfactuals(
    counterfactual_returns: pd.DataFrame | Mapping[str, pd.Series | pd.DataFrame],
    base_variant: str = "full",
) -> pd.DataFrame:
    """Summarize each counterfactual variant and compute full-minus-variant deltas."""
    df = _prepare_counterfactual_frame(counterfactual_returns)
    if "variant_id" not in df.columns:
        raise ValueError("counterfactual_returns must contain variant_id")

    return_col = _pick_return_column(df)
    group_keys = ["strategy_id"] if "strategy_id" in df.columns else []
    summaries: list[pd.DataFrame] = []

    grouped = df.groupby(group_keys, sort=False, dropna=False) if group_keys else [((), df)]
    for key, group in grouped:
        variant_rows = [
            _summarize_variant(variant, variant_df, return_col)
            for variant, variant_df in group.groupby("variant_id", sort=False)
        ]
        summary = pd.DataFrame(variant_rows)
        if base_variant not in set(summary["variant_id"]):
            key_text = key if group_keys else "all data"
            raise ValueError(f"base variant {base_variant!r} not found for {key_text}")

        base = summary.loc[summary["variant_id"] == base_variant].iloc[0]
        for metric, delta_col in (
            ("ann_return", "delta_return"),
            ("max_drawdown", "delta_maxdd"),
            ("calmar", "delta_calmar"),
            ("sharpe", "delta_sharpe"),
            ("worst_20d", "delta_worst_20d"),
            ("total_turnover", "delta_turnover"),
            ("total_cost", "delta_cost"),
        ):
            summary[delta_col] = base[metric] - summary[metric]
        summaries.append(summary)

    return pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame()


def summarize_ablation_edges(summary: pd.DataFrame) -> pd.DataFrame:
    """Aggregate variant deltas into player-level marginal edges."""
    if summary.empty:
        return _empty_ablation_edges()
    if "removed_player" not in summary.columns:
        raise ValueError("summary must contain removed_player")

    df = summary.copy()
    mask = df["removed_player"].notna() & (df["removed_player"].astype(str) != "")
    df = df.loc[mask]
    if df.empty:
        return _empty_ablation_edges()

    if "ablation_type" not in df.columns:
        df["ablation_type"] = "unknown"

    grouped = df.groupby(["removed_player", "ablation_type"], dropna=False, sort=False)
    edges = grouped.agg(
        n_variants=("variant_id", "count")
        if "variant_id" in df.columns
        else ("removed_player", "size"),
        return_edge=("delta_return", "mean"),
        maxdd_edge=("delta_maxdd", "mean"),
        calmar_edge=("delta_calmar", "mean"),
        turnover_edge=("delta_turnover", "mean"),
        cost_edge=("delta_cost", "mean"),
    ).reset_index()
    edges["dd_relief"] = -edges["maxdd_edge"]
    edges["cost_saving"] = -edges["cost_edge"]
    edges["net_edge"] = edges["return_edge"]
    return edges


def find_drawdown_episodes(
    returns: pd.Series | np.ndarray | list[float],
    top_n: int = 5,
    min_depth: float = 0.0,
) -> pd.DataFrame:
    """Find peak-to-trough drawdown episodes sorted by depth."""
    r = _as_return_series(returns)
    columns = ["episode_id", "peak", "trough", "recovery", "maxdd", "episode_return"]
    if r.empty:
        return pd.DataFrame(columns=columns)

    dates = pd.Index(r.index)
    wealth = (1.0 + r).cumprod()
    peak_value = 1.0
    peak_date = dates[0]
    in_drawdown = False
    current: dict[str, Any] | None = None
    episodes: list[dict[str, Any]] = []

    for date, value in wealth.items():
        value = float(value)
        if value >= peak_value:
            if in_drawdown and current is not None:
                current["recovery"] = date
                _append_episode_if_deep(episodes, current, min_depth)
                current = None
                in_drawdown = False
            peak_value = value
            peak_date = date
            continue

        if not in_drawdown:
            current = {
                "peak": peak_date,
                "peak_value": peak_value,
                "trough": date,
                "trough_value": value,
                "recovery": pd.NaT,
            }
            in_drawdown = True
        elif current is not None and value < float(current["trough_value"]):
            current["trough"] = date
            current["trough_value"] = value

    if in_drawdown and current is not None:
        _append_episode_if_deep(episodes, current, min_depth)

    if not episodes:
        return pd.DataFrame(columns=columns)

    result = (
        pd.DataFrame(episodes)
        .sort_values("maxdd", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    result.insert(0, "episode_id", [f"dd_{i + 1}" for i in range(len(result))])
    return result[columns]


def attribute_drawdown_episode(
    episode: Mapping[str, Any] | pd.Series,
    symbol_pnl: pd.Series | pd.DataFrame | None = None,
    category_pnl: pd.Series | pd.DataFrame | None = None,
    rule_actions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Attribute one drawdown episode to symbol, category, action, and cost inputs."""
    start, end = _episode_bounds(episode)
    top_loss_symbols = _aggregate_pnl(symbol_pnl, "symbol", start, end)
    top_loss_categories = _aggregate_pnl(category_pnl, "category", start, end)
    actions = (
        _filter_by_date(rule_actions, start, end) if rule_actions is not None else pd.DataFrame()
    )
    cost_effect = _cost_effect(actions)
    return {
        "peak_date": start,
        "trough_date": end,
        "recovery_date": _episode_value(episode, "recovery", "recovery_date"),
        "maxdd": float(_episode_value(episode, "maxdd", "max_drawdown") or 0.0),
        "episode_return": float(_episode_value(episode, "episode_return") or 0.0),
        "top_loss_symbols": top_loss_symbols,
        "top_loss_categories": top_loss_categories,
        "rule_actions": actions.reset_index(drop=True) if not actions.empty else actions,
        "cost_effect": cost_effect,
        "root_cause_label": _root_cause_label(
            top_loss_symbols, top_loss_categories, cost_effect, actions
        ),
    }


def turnover_cost_attribution(
    counterfactual_returns: pd.DataFrame | Mapping[str, pd.Series | pd.DataFrame],
    base_variant: str = "full",
) -> pd.DataFrame:
    """Compute turnover, cost saving, opportunity cost, and net value by player."""
    df = _prepare_counterfactual_frame(counterfactual_returns)
    if "variant_id" not in df.columns:
        raise ValueError("counterfactual_returns must contain variant_id")

    group_keys = ["strategy_id"] if "strategy_id" in df.columns else []
    rows: list[dict[str, Any]] = []
    grouped = df.groupby(group_keys, sort=False, dropna=False) if group_keys else [((), df)]

    for key, group in grouped:
        if base_variant not in set(group["variant_id"]):
            key_text = key if group_keys else "all data"
            raise ValueError(f"base variant {base_variant!r} not found for {key_text}")
        full = group.loc[group["variant_id"] == base_variant]
        full_turnover = _sum_column(full, "turnover")
        full_cost = _sum_column(full, "cost")
        full_gross = _total_return_from_column(full, "gross_return")
        full_net = _total_return_from_column(full, _pick_return_column(full))

        for variant, variant_df in group.groupby("variant_id", sort=False):
            if variant == base_variant:
                continue
            without_turnover = _sum_column(variant_df, "turnover")
            without_cost = _sum_column(variant_df, "cost")
            without_gross = _total_return_from_column(variant_df, "gross_return")
            without_net = _total_return_from_column(variant_df, _pick_return_column(variant_df))
            cost_saving = without_cost - full_cost
            opportunity_cost = without_gross - full_gross
            row: dict[str, Any] = {
                "variant_id": variant,
                "ablation_type": _first_value(variant_df, "ablation_type"),
                "player_name": _player_name(variant_df, variant),
                "turnover_full": full_turnover,
                "turnover_without_player": without_turnover,
                "turnover_edge": full_turnover - without_turnover,
                "cost_full": full_cost,
                "cost_without_player": without_cost,
                "cost_saving": cost_saving,
                "opportunity_cost": opportunity_cost,
                "gross_opportunity_cost": opportunity_cost,
                "net_edge": full_net - without_net,
                "net_value": cost_saving - opportunity_cost,
            }
            if group_keys:
                row["strategy_id"] = _first_value(variant_df, "strategy_id")
            rows.append(row)

    return pd.DataFrame(rows)


def _as_return_series(returns: pd.Series | np.ndarray | list[float]) -> pd.Series:
    if isinstance(returns, pd.Series):
        series = returns.copy()
    else:
        series = pd.Series(returns)
    series = pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)
    if isinstance(series.index, pd.DatetimeIndex):
        series = series.sort_index()
    return series


def _compounded_return(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    return float(np.prod(1.0 + returns.to_numpy(dtype=float)) - 1.0)


def _annualized_return(returns: pd.Series, annualization: int) -> float:
    if returns.empty:
        return 0.0
    terminal = 1.0 + _compounded_return(returns)
    if terminal <= 0.0:
        return -1.0
    return float(terminal ** (annualization / len(returns)) - 1.0)


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    wealth = np.concatenate([[1.0], np.cumprod(1.0 + returns.to_numpy(dtype=float))])
    peaks = np.maximum.accumulate(wealth)
    drawdowns = wealth / peaks - 1.0
    return float(abs(np.min(drawdowns)))


def _sharpe(returns: pd.Series, annualization: int) -> float:
    if returns.empty:
        return 0.0
    std = float(returns.std(ddof=1))
    mean = float(returns.mean())
    if std == 0.0 or np.isnan(std):
        if mean > 0.0:
            return float("inf")
        if mean < 0.0:
            return float("-inf")
        return 0.0
    return float(mean / std * np.sqrt(annualization))


def _calmar(ann_return: float, max_drawdown: float) -> float:
    if max_drawdown > 0.0:
        return float(ann_return / max_drawdown)
    if ann_return > 0.0:
        return float("inf")
    if ann_return < 0.0:
        return float("-inf")
    return 0.0


def _worst_window_return(returns: pd.Series, window: int) -> float:
    if returns.empty:
        return 0.0
    actual_window = min(window, len(returns))
    rolling = (1.0 + returns).rolling(actual_window, min_periods=actual_window).apply(
        np.prod, raw=True
    ) - 1.0
    return (
        float(rolling.dropna().min()) if not rolling.dropna().empty else _compounded_return(returns)
    )


def _prepare_counterfactual_frame(
    data: pd.DataFrame | Mapping[str, pd.Series | pd.DataFrame],
) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        result = data.copy()
    elif isinstance(data, Mapping):
        frames = []
        for variant_id, value in data.items():
            if isinstance(value, pd.Series):
                frame = value.rename("return").reset_index()
                if frame.columns[0] != "date":
                    frame = frame.rename(columns={frame.columns[0]: "date"})
            elif isinstance(value, pd.DataFrame):
                frame = value.copy().reset_index() if value.index.name is not None else value.copy()
            else:
                raise TypeError("mapping values must be Series or DataFrame")
            frame["variant_id"] = variant_id
            frames.append(frame)
        result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    else:
        raise TypeError("counterfactual_returns must be a DataFrame or mapping")

    date_col = _find_date_column(result)
    if date_col is not None:
        result[date_col] = pd.to_datetime(result[date_col])
        sort_cols = ["variant_id", date_col] if "variant_id" in result.columns else [date_col]
        result = result.sort_values(sort_cols)
    return result


def _pick_return_column(df: pd.DataFrame) -> str:
    for col in RETURN_COLUMNS:
        if col in df.columns:
            return col
    raise ValueError(f"counterfactual_returns must contain one of {RETURN_COLUMNS}")


def _summarize_variant(variant: str, df: pd.DataFrame, return_col: str) -> dict[str, Any]:
    metrics = performance_metrics(df[return_col])
    row: dict[str, Any] = {
        "variant_id": variant,
        "n_obs": int(len(df)),
        "total_turnover": _sum_column(df, "turnover"),
        "total_cost": _sum_column(df, "cost"),
        "gross_total_return": _total_return_from_column(df, "gross_return"),
        "net_total_return": _total_return_from_column(df, return_col),
    }
    for col in ("strategy_id", "ablation_type", "removed_player", "coalition_id", "notes"):
        if col in df.columns:
            row[col] = _first_value(df, col)
    row.update(metrics)
    return row


def _sum_column(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return np.nan
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum())


def _total_return_from_column(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return np.nan
    return _compounded_return(pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float))


def _first_value(df: pd.DataFrame, col: str) -> Any:
    if col not in df.columns:
        return np.nan
    values = df[col].dropna()
    return values.iloc[0] if not values.empty else np.nan


def _empty_ablation_edges() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "removed_player",
            "ablation_type",
            "n_variants",
            "return_edge",
            "maxdd_edge",
            "calmar_edge",
            "turnover_edge",
            "cost_edge",
            "dd_relief",
            "cost_saving",
            "net_edge",
        ]
    )


def _append_episode_if_deep(
    episodes: list[dict[str, Any]], episode: dict[str, Any], min_depth: float
) -> None:
    peak_value = float(episode["peak_value"])
    trough_value = float(episode["trough_value"])
    maxdd = 1.0 - trough_value / peak_value if peak_value != 0.0 else 0.0
    if maxdd < min_depth:
        return
    episodes.append(
        {
            "peak": episode["peak"],
            "trough": episode["trough"],
            "recovery": episode["recovery"],
            "maxdd": float(maxdd),
            "episode_return": float(trough_value / peak_value - 1.0) if peak_value != 0.0 else 0.0,
        }
    )


def _episode_bounds(
    episode: Mapping[str, Any] | pd.Series,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    start = _episode_value(episode, "peak", "peak_date", "start", "start_date")
    end = _episode_value(episode, "trough", "trough_date", "end", "end_date")
    return _to_timestamp_or_none(start), _to_timestamp_or_none(end)


def _episode_value(episode: Mapping[str, Any] | pd.Series, *names: str) -> Any:
    for name in names:
        if name in episode and pd.notna(episode[name]):
            return episode[name]
    return None


def _to_timestamp_or_none(value: Any) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value)


def _aggregate_pnl(
    table: pd.Series | pd.DataFrame | None,
    group_col: str,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    top_n: int = 5,
) -> pd.DataFrame:
    columns = [group_col, "pnl"]
    if table is None:
        return pd.DataFrame(columns=columns)
    if isinstance(table, pd.Series):
        return _aggregate_series_pnl(table, group_col, start, end, top_n)

    filtered = _filter_by_date(table, start, end)
    if filtered.empty:
        return pd.DataFrame(columns=columns)

    if group_col in filtered.columns:
        pnl_col = _pick_pnl_column(filtered, exclude={group_col})
        result = (
            filtered.assign(_pnl=pd.to_numeric(filtered[pnl_col], errors="coerce").fillna(0.0))
            .groupby(group_col, dropna=False)["_pnl"]
            .sum()
            .reset_index(name="pnl")
        )
    else:
        numeric_cols = filtered.select_dtypes(include=[np.number]).columns
        result = filtered[numeric_cols].sum().rename_axis(group_col).reset_index(name="pnl")

    return result.sort_values("pnl", ascending=True).head(top_n).reset_index(drop=True)


def _aggregate_series_pnl(
    series: pd.Series,
    group_col: str,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    top_n: int,
) -> pd.DataFrame:
    s = pd.to_numeric(series, errors="coerce").fillna(0.0)
    if isinstance(s.index, pd.MultiIndex):
        date_level = _find_datetime_level(s.index)
        if date_level is not None:
            dates = pd.to_datetime(s.index.get_level_values(date_level))
            mask = _date_mask(dates, start, end)
            s = s.loc[mask]
        group_level = (
            group_col if group_col in s.index.names else _first_non_date_level(s.index, date_level)
        )
        grouped = s.groupby(level=group_level).sum()
    else:
        grouped = s
    return (
        grouped.rename("pnl")
        .rename_axis(group_col)
        .reset_index()
        .sort_values("pnl", ascending=True)
        .head(top_n)
        .reset_index(drop=True)
    )


def _filter_by_date(
    df: pd.DataFrame, start: pd.Timestamp | None, end: pd.Timestamp | None
) -> pd.DataFrame:
    if df.empty or (start is None and end is None):
        return df.copy()

    date_col = _find_date_column(df)
    if date_col is not None:
        dates = pd.to_datetime(df[date_col])
        return df.loc[_date_mask(dates, start, end)].copy()

    if isinstance(df.index, pd.DatetimeIndex):
        dates = pd.to_datetime(df.index)
        return df.loc[_date_mask(dates, start, end)].copy()

    if isinstance(df.index, pd.MultiIndex):
        date_level = _find_datetime_level(df.index)
        if date_level is not None:
            dates = pd.to_datetime(df.index.get_level_values(date_level))
            return df.loc[_date_mask(dates, start, end)].copy()

    return df.copy()


def _date_mask(
    dates: pd.Index | pd.Series, start: pd.Timestamp | None, end: pd.Timestamp | None
) -> np.ndarray:
    date_values = pd.to_datetime(dates)
    mask = np.ones(len(date_values), dtype=bool)
    if start is not None:
        mask &= date_values >= start
    if end is not None:
        mask &= date_values <= end
    return mask


def _find_date_column(df: pd.DataFrame) -> str | None:
    for col in DATE_COLUMNS:
        if col in df.columns:
            return col
    return None


def _find_datetime_level(index: pd.MultiIndex) -> int | None:
    for level_no in range(index.nlevels):
        values = index.get_level_values(level_no)
        if isinstance(values, pd.DatetimeIndex) or np.issubdtype(values.dtype, np.datetime64):
            return level_no
    return None


def _first_non_date_level(index: pd.MultiIndex, date_level: int | None) -> int:
    for level_no in range(index.nlevels):
        if level_no != date_level:
            return level_no
    return 0


def _pick_pnl_column(df: pd.DataFrame, exclude: set[str] | None = None) -> str:
    exclude = exclude or set()
    for col in PNL_COLUMNS:
        if col in df.columns and col not in exclude:
            return col
    numeric_cols = [
        col for col in df.select_dtypes(include=[np.number]).columns if col not in exclude
    ]
    if not numeric_cols:
        raise ValueError("pnl table must contain a numeric pnl column")
    return numeric_cols[0]


def _cost_effect(actions: pd.DataFrame) -> float:
    if actions.empty:
        return 0.0
    for col in COST_COLUMNS:
        if col in actions.columns:
            values = pd.to_numeric(actions[col], errors="coerce").fillna(0.0)
            total = float(values.sum())
            return -total if (values >= 0.0).all() else total
    return 0.0


def _root_cause_label(
    top_loss_symbols: pd.DataFrame,
    top_loss_categories: pd.DataFrame,
    cost_effect: float,
    actions: pd.DataFrame,
) -> str:
    category_loss = _largest_loss(top_loss_categories)
    symbol_loss = _largest_loss(top_loss_symbols)
    cost_loss = min(cost_effect, 0.0)
    if category_loss < 0.0 and abs(category_loss) >= max(abs(symbol_loss), abs(cost_loss)):
        return "category"
    if symbol_loss < 0.0 and abs(symbol_loss) >= abs(cost_loss):
        return "market"
    if cost_loss < 0.0:
        return "execution"
    if not actions.empty:
        return "rule"
    return "market"


def _largest_loss(df: pd.DataFrame) -> float:
    if df.empty or "pnl" not in df.columns:
        return 0.0
    return float(pd.to_numeric(df["pnl"], errors="coerce").fillna(0.0).min())


def _player_name(df: pd.DataFrame, fallback: str) -> str:
    removed = _first_value(df, "removed_player")
    if pd.notna(removed) and str(removed) != "":
        return str(removed)
    return str(fallback)


__all__ = [
    "performance_metrics",
    "summarize_counterfactuals",
    "summarize_ablation_edges",
    "find_drawdown_episodes",
    "attribute_drawdown_episode",
    "turnover_cost_attribution",
]
