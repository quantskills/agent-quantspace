"""Signal-to-trade and action-day attribution helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import reduce

import numpy as np
import pandas as pd

DATE_COLUMNS = ("date", "eob", "trade_date", "signal_date")
SYMBOL_COLUMNS = ("symbol", "ticker", "code")
STRATEGY_ID = "strategy_id"
DEFAULT_STRATEGY_ID = "default"


def build_action_day_ledger(
    target_weights: pd.DataFrame | pd.Series,
    executed_weights: pd.DataFrame | pd.Series | None = None,
    decision_ledger: pd.DataFrame | None = None,
    threshold: float = 1e-9,
) -> pd.DataFrame:
    """Build an action-day ledger from target or executed weight changes."""
    target = _normalize_panel(
        target_weights,
        value_name="w_target",
        value_candidates=("w_target", "target_weight", "weight", "value"),
    )

    if executed_weights is not None:
        executed = _normalize_panel(
            executed_weights,
            value_name="w_exec",
            value_candidates=("w_exec", "executed_weight", "weight", "value"),
        )
        ledger = target.merge(
            executed,
            on=[STRATEGY_ID, "date", "symbol"],
            how="outer",
            validate="one_to_one",
        )
        ledger["current_weight"] = ledger["w_exec"].where(
            ledger["w_exec"].notna(), ledger["w_target"]
        )
        weight_source = "executed"
    else:
        ledger = target.copy()
        ledger["w_exec"] = np.nan
        ledger["current_weight"] = ledger["w_target"]
        weight_source = "target"

    ledger["w_target"] = ledger["w_target"].fillna(0.0)
    ledger["current_weight"] = ledger["current_weight"].fillna(0.0)
    ledger = ledger.sort_values([STRATEGY_ID, "symbol", "date"]).reset_index(drop=True)
    ledger["previous_weight"] = (
        ledger.groupby([STRATEGY_ID, "symbol"], sort=False)["current_weight"].shift(1).fillna(0.0)
    )
    ledger["trade_weight"] = ledger["current_weight"] - ledger["previous_weight"]
    ledger["turnover_abs"] = ledger["trade_weight"].abs()
    ledger["action"] = _classify_actions(
        ledger["previous_weight"],
        ledger["current_weight"],
        threshold=threshold,
    )

    ledger["primary_reason"] = _default_primary_reason(ledger["action"])

    if decision_ledger is not None:
        decision = _normalize_metadata(decision_ledger)
        ledger_strategies = set(ledger[STRATEGY_ID].dropna().unique())
        decision_strategies = decision[STRATEGY_ID].dropna().unique()
        if ledger_strategies == {DEFAULT_STRATEGY_ID} and len(decision_strategies) == 1:
            ledger[STRATEGY_ID] = decision_strategies[0]
        ledger = ledger.merge(
            decision,
            on=[STRATEGY_ID, "date", "symbol"],
            how="left",
            suffixes=("", "_decision"),
        )
        if "primary_reason_decision" in ledger.columns:
            ledger["primary_reason"] = ledger["primary_reason_decision"].where(
                ledger["primary_reason_decision"].notna(), ledger["primary_reason"]
            )
            ledger = ledger.drop(columns=["primary_reason_decision"])

    ledger["weight_source"] = weight_source
    ordered = [
        "date",
        STRATEGY_ID,
        "symbol",
        "action",
        "primary_reason",
        "previous_weight",
        "current_weight",
        "w_target",
        "w_exec",
        "trade_weight",
        "turnover_abs",
        "weight_source",
    ]
    extra = [col for col in ledger.columns if col not in ordered]
    return (
        ledger[ordered + extra].sort_values([STRATEGY_ID, "date", "symbol"]).reset_index(drop=True)
    )


def compute_forward_action_returns(
    action_ledger: pd.DataFrame,
    symbol_returns: pd.DataFrame | pd.Series,
    windows: Sequence[int] = (1, 5, 20),
) -> pd.DataFrame:
    """Attach forward cumulative symbol returns to each action row."""
    if not windows:
        return action_ledger.copy()

    returns = _normalize_panel(
        symbol_returns,
        value_name="return",
        value_candidates=("return", "ret", "symbol_return", "value"),
    )
    returns = returns.sort_values(["symbol", "date"]).reset_index(drop=True)
    forward_frames = []
    for symbol, group in returns.groupby("symbol", sort=False):
        out = group[["date", "symbol"]].copy()
        out["symbol"] = symbol
        daily = group["return"].astype(float)
        for window in windows:
            if window <= 0:
                raise ValueError("Forward windows must be positive integers.")
            gross = (1.0 + daily).shift(-1)
            fwd = (
                gross.iloc[::-1]
                .rolling(window=window, min_periods=window)
                .apply(np.prod, raw=True)
                .iloc[::-1]
                - 1.0
            )
            out[f"forward_return_{window}d"] = fwd.to_numpy()
        forward_frames.append(out)

    forward = pd.concat(forward_frames, ignore_index=True) if forward_frames else pd.DataFrame()
    enriched = action_ledger.copy()
    enriched["date"] = pd.to_datetime(enriched["date"])
    enriched = enriched.merge(forward, on=["date", "symbol"], how="left")
    if "trade_weight" in enriched.columns:
        for window in windows:
            ret_col = f"forward_return_{window}d"
            enriched[f"forward_pnl_{window}d"] = enriched["trade_weight"] * enriched[ret_col]
    return enriched


def factor5_snapshot_from_components(
    components: Mapping[str, pd.DataFrame | pd.Series] | pd.DataFrame,
    category_map: Mapping[str, str] | pd.Series | pd.DataFrame | None = None,
    min_components: int = 3,
) -> pd.DataFrame:
    """Create a factor5 raw/rank snapshot from component values."""
    if min_components <= 0:
        raise ValueError("min_components must be positive.")

    base, component_names = _component_table(
        components,
        value_candidates=("value", "raw", "factor_value", "score"),
    )
    if not component_names:
        raise ValueError("At least one component is required.")

    snapshot = base[[STRATEGY_ID, "date", "symbol"]].copy()
    rank_pct_cols: list[str] = []
    for name in component_names:
        raw_col = f"{name}_raw"
        rank_pct_col = f"{name}_rank_pct"
        rank_col = f"{name}_rank"
        snapshot[raw_col] = base[name]
        snapshot[rank_pct_col] = _rank_pct(base, name)
        snapshot[rank_col] = _rank_desc(base, name)
        rank_pct_cols.append(rank_pct_col)

    snapshot["valid_factor_count"] = (
        snapshot[[f"{name}_raw" for name in component_names]].notna().sum(axis=1)
    )
    enough = snapshot["valid_factor_count"] >= min_components
    snapshot["factor5_score"] = snapshot[rank_pct_cols].mean(axis=1, skipna=True).where(enough)
    total_components = len(component_names)
    snapshot["coverage_flag"] = np.select(
        [
            snapshot["valid_factor_count"] < min_components,
            snapshot["valid_factor_count"] < total_components,
        ],
        ["missing", "partial"],
        default="full",
    )
    snapshot["coverage_reason"] = np.select(
        [
            snapshot["valid_factor_count"] < min_components,
            snapshot["valid_factor_count"] < total_components,
        ],
        ["insufficient_components", "partial_components"],
        default="full_components",
    )
    snapshot["cross_section_rank_pct"] = _rank_pct(snapshot, "factor5_score")
    snapshot["cross_section_rank"] = _rank_desc(snapshot, "factor5_score")
    snapshot = _attach_category(snapshot, category_map)
    return _order_snapshot_columns(snapshot, component_names, raw_suffix="_raw")


def nsind3_vote_snapshot(
    votes: Mapping[str, pd.DataFrame | pd.Series] | pd.DataFrame,
    score_parts: Mapping[str, pd.DataFrame | pd.Series] | pd.DataFrame | None = None,
    category_map: Mapping[str, str] | pd.Series | pd.DataFrame | None = None,
    threshold: int = 5,
) -> pd.DataFrame:
    """Create an ns_ind3 vote snapshot with eligibility and tie-break ranks."""
    vote_table, vote_names = _component_table(
        votes,
        value_candidates=("value", "vote", "signal", "raw"),
    )
    if not vote_names:
        raise ValueError("At least one vote is required.")

    snapshot = vote_table[[STRATEGY_ID, "date", "symbol"]].copy()
    for name in vote_names:
        snapshot[name] = _as_vote(vote_table[name])

    vote_values = snapshot[vote_names].astype(int)
    snapshot["vote_score"] = vote_values.sum(axis=1)
    snapshot["eligible"] = snapshot["vote_score"] >= threshold
    snapshot["vote_rank_pct"] = _rank_pct(snapshot, "vote_score")
    snapshot["vote_rank"] = _rank_desc(snapshot, "vote_score")

    score_part_names: list[str] = []
    if score_parts is not None:
        part_table, score_part_names = _component_table(
            score_parts,
            value_candidates=("value", "raw", "score", "factor_value"),
        )
        snapshot = snapshot.merge(
            part_table[[STRATEGY_ID, "date", "symbol", *score_part_names]],
            on=[STRATEGY_ID, "date", "symbol"],
            how="left",
            validate="one_to_one",
        )
        part_rank_cols = []
        for name in score_part_names:
            raw_col = f"{name}_raw"
            rank_pct_col = f"{name}_rank_pct"
            rank_col = f"{name}_rank"
            snapshot[raw_col] = snapshot[name]
            snapshot[rank_pct_col] = _rank_pct(snapshot, raw_col)
            snapshot[rank_col] = _rank_desc(snapshot, raw_col)
            snapshot = snapshot.drop(columns=[name])
            part_rank_cols.append(rank_pct_col)
        tie_break = snapshot[part_rank_cols].mean(axis=1, skipna=True).fillna(0.0)
        snapshot["final_score"] = snapshot["vote_score"].astype(float) + tie_break
    else:
        snapshot["final_score"] = snapshot["vote_score"].astype(float)

    snapshot["final_rank_pct"] = _rank_pct(snapshot, "final_score")
    snapshot["final_rank"] = _rank_desc(snapshot, "final_score")
    eligible_score = snapshot["final_score"].where(snapshot["eligible"])
    snapshot["top_rank_pct"] = _rank_pct(
        snapshot.assign(_eligible_score=eligible_score), "_eligible_score"
    )
    snapshot["top_rank"] = _rank_desc(
        snapshot.assign(_eligible_score=eligible_score), "_eligible_score"
    )
    snapshot = _attach_category(snapshot, category_map)

    leading = [
        "date",
        STRATEGY_ID,
        "symbol",
        "category",
        *vote_names,
        "vote_score",
        "eligible",
        "vote_rank_pct",
        "vote_rank",
    ]
    part_cols = []
    for name in score_part_names:
        part_cols.extend([f"{name}_raw", f"{name}_rank_pct", f"{name}_rank"])
    trailing = ["final_score", "final_rank_pct", "final_rank", "top_rank_pct", "top_rank"]
    return _select_existing(snapshot, leading + part_cols + trailing)


def summarize_actions(
    action_ledger: pd.DataFrame,
    group_cols: Sequence[str] = (STRATEGY_ID, "action"),
) -> pd.DataFrame:
    """Summarize action counts, forward returns, and turnover by group."""
    ledger = action_ledger.copy()
    if STRATEGY_ID in group_cols and STRATEGY_ID not in ledger.columns:
        ledger[STRATEGY_ID] = DEFAULT_STRATEGY_ID

    group_cols = list(group_cols)
    grouped = ledger.groupby(group_cols, dropna=False, sort=True)
    summary = grouped.size().rename("action_count").reset_index()
    summary["trigger_count"] = summary["action_count"]

    if "turnover_abs" in ledger.columns:
        turnover = grouped["turnover_abs"].agg(["sum", "mean"]).reset_index()
        turnover = turnover.rename(columns={"sum": "turnover_abs_sum", "mean": "turnover_abs_mean"})
        summary = summary.merge(turnover, on=group_cols, how="left")

    metric_cols = [
        col
        for col in ledger.columns
        if col.startswith("forward_return_") or col.startswith("forward_pnl_")
    ]
    for col in metric_cols:
        mean_col = f"avg_{col}"
        values = grouped[col].mean().rename(mean_col).reset_index()
        summary = summary.merge(values, on=group_cols, how="left")
        if col.startswith("forward_pnl_"):
            sum_col = f"sum_{col}"
            values = grouped[col].sum(min_count=1).rename(sum_col).reset_index()
            summary = summary.merge(values, on=group_cols, how="left")
    return summary


def _normalize_panel(
    data: pd.DataFrame | pd.Series,
    value_name: str,
    value_candidates: Sequence[str],
) -> pd.DataFrame:
    if isinstance(data, pd.Series):
        frame = data.to_frame(name=data.name or value_name)
    elif isinstance(data, pd.DataFrame):
        frame = data.copy()
    else:
        raise TypeError("Input must be a pandas DataFrame or Series.")

    if isinstance(frame.index, pd.MultiIndex):
        frame = frame.reset_index()

    date_col = _find_column(frame, DATE_COLUMNS)
    symbol_col = _find_column(frame, SYMBOL_COLUMNS)
    if date_col is not None and symbol_col is not None:
        value_col = _find_value_column(frame, value_name, value_candidates)
        if value_col is None:
            raise ValueError(f"Could not infer value column for {value_name}.")
        strategy_col = _find_column(frame, (STRATEGY_ID,))
        out = frame[
            [date_col, symbol_col, value_col] + ([strategy_col] if strategy_col else [])
        ].copy()
        out = out.rename(
            columns={
                date_col: "date",
                symbol_col: "symbol",
                value_col: value_name,
                **({strategy_col: STRATEGY_ID} if strategy_col else {}),
            }
        )
        if STRATEGY_ID not in out.columns:
            out[STRATEGY_ID] = DEFAULT_STRATEGY_ID
        out["date"] = pd.to_datetime(out["date"])
        return (
            out[[STRATEGY_ID, "date", "symbol", value_name]]
            .sort_values([STRATEGY_ID, "date", "symbol"])
            .reset_index(drop=True)
        )

    if date_col is not None and symbol_col is None:
        strategy_col = _find_column(frame, (STRATEGY_ID,))
        id_vars = [date_col] + ([strategy_col] if strategy_col else [])
        value_vars = [col for col in frame.columns if col not in set(id_vars)]
        if not value_vars:
            raise ValueError(f"Wide input does not contain symbol columns for {value_name}.")
        out = frame.melt(
            id_vars=id_vars,
            value_vars=value_vars,
            var_name="symbol",
            value_name=value_name,
        )
        rename_map = {date_col: "date"}
        if strategy_col is not None:
            rename_map[strategy_col] = STRATEGY_ID
        out = out.rename(columns=rename_map)
        if STRATEGY_ID not in out.columns:
            out[STRATEGY_ID] = DEFAULT_STRATEGY_ID
        out["date"] = pd.to_datetime(out["date"])
        return (
            out[[STRATEGY_ID, "date", "symbol", value_name]]
            .sort_values([STRATEGY_ID, "date", "symbol"])
            .reset_index(drop=True)
        )

    if frame.index.nlevels != 1:
        raise ValueError("Wide input must have a one-level date index.")
    wide = frame.copy()
    wide.index = pd.to_datetime(wide.index)
    out = wide.stack(dropna=False).rename(value_name).reset_index()
    out = out.rename(columns={out.columns[0]: "date", out.columns[1]: "symbol"})
    out[STRATEGY_ID] = DEFAULT_STRATEGY_ID
    return (
        out[[STRATEGY_ID, "date", "symbol", value_name]]
        .sort_values([STRATEGY_ID, "date", "symbol"])
        .reset_index(drop=True)
    )


def _normalize_metadata(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    if isinstance(frame.index, pd.MultiIndex):
        frame = frame.reset_index()
    date_col = _find_column(frame, DATE_COLUMNS)
    symbol_col = _find_column(frame, SYMBOL_COLUMNS)
    if date_col is None or symbol_col is None:
        raise ValueError("Metadata must include date and symbol columns.")
    strategy_col = _find_column(frame, (STRATEGY_ID,))
    rename_map = {date_col: "date", symbol_col: "symbol"}
    if strategy_col is not None:
        rename_map[strategy_col] = STRATEGY_ID
    frame = frame.rename(columns=rename_map)
    if STRATEGY_ID not in frame.columns:
        frame[STRATEGY_ID] = DEFAULT_STRATEGY_ID
    frame["date"] = pd.to_datetime(frame["date"])
    keys = [STRATEGY_ID, "date", "symbol"]
    cols = keys + [col for col in frame.columns if col not in keys]
    return frame[cols].drop_duplicates(keys, keep="last")


def _component_table(
    data: Mapping[str, pd.DataFrame | pd.Series] | pd.DataFrame,
    value_candidates: Sequence[str],
) -> tuple[pd.DataFrame, list[str]]:
    if isinstance(data, Mapping):
        frames = []
        names = []
        for name, panel in data.items():
            normalized = _normalize_panel(
                panel,
                value_name=name,
                value_candidates=(name, *value_candidates),
            )
            frames.append(normalized)
            names.append(name)
        merged = reduce(
            lambda left, right: left.merge(
                right,
                on=[STRATEGY_ID, "date", "symbol"],
                how="outer",
                validate="one_to_one",
            ),
            frames,
        )
        return merged.sort_values([STRATEGY_ID, "date", "symbol"]).reset_index(drop=True), names

    frame = data.copy()
    if isinstance(frame.index, pd.MultiIndex):
        frame = frame.reset_index()
    date_col = _find_column(frame, DATE_COLUMNS)
    symbol_col = _find_column(frame, SYMBOL_COLUMNS)
    if date_col is None or symbol_col is None:
        raise ValueError("Component table must include date and symbol columns.")
    strategy_col = _find_column(frame, (STRATEGY_ID,))
    component_col = _find_column(frame, ("component", "factor", "name", "vote"))
    if strategy_col is None:
        frame[STRATEGY_ID] = DEFAULT_STRATEGY_ID
        strategy_col = STRATEGY_ID
    frame = frame.rename(
        columns={date_col: "date", symbol_col: "symbol", strategy_col: STRATEGY_ID}
    )
    frame["date"] = pd.to_datetime(frame["date"])

    if component_col is not None:
        value_search_frame = frame.drop(columns=[component_col])
        value_col = _find_value_column(value_search_frame, "value", value_candidates)
        if value_col is None:
            raise ValueError("Long component table must include a value column.")
        table = (
            frame.pivot_table(
                index=[STRATEGY_ID, "date", "symbol"],
                columns=component_col,
                values=value_col,
                aggfunc="last",
            )
            .reset_index()
            .rename_axis(columns=None)
        )
        names = [col for col in table.columns if col not in {STRATEGY_ID, "date", "symbol"}]
        return table.sort_values([STRATEGY_ID, "date", "symbol"]).reset_index(drop=True), names

    excluded = {STRATEGY_ID, "date", "symbol", "category"}
    names = [col for col in frame.columns if col not in excluded]
    return frame[[STRATEGY_ID, "date", "symbol", *names]].sort_values(
        [STRATEGY_ID, "date", "symbol"]
    ).reset_index(drop=True), names


def _find_column(frame: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    columns = {str(col).lower(): col for col in frame.columns}
    for candidate in candidates:
        found = columns.get(candidate.lower())
        if found is not None:
            return found
    return None


def _find_value_column(
    frame: pd.DataFrame,
    value_name: str,
    value_candidates: Sequence[str],
) -> str | None:
    for candidate in (value_name, *value_candidates):
        found = _find_column(frame, (candidate,))
        if found is not None:
            return found
    key_cols = set(DATE_COLUMNS) | set(SYMBOL_COLUMNS) | {STRATEGY_ID, "category"}
    candidates = [
        col
        for col in frame.columns
        if str(col).lower() not in key_cols and pd.api.types.is_numeric_dtype(frame[col])
    ]
    return candidates[0] if len(candidates) == 1 else None


def _classify_actions(
    previous_weight: pd.Series,
    current_weight: pd.Series,
    threshold: float,
) -> pd.Series:
    previous = previous_weight.astype(float)
    current = current_weight.astype(float)
    delta = current - previous
    changed = delta.abs() > threshold
    prev_active = previous.abs() > threshold
    current_active = current.abs() > threshold

    actions = np.select(
        [
            ~changed & ~current_active,
            ~changed & current_active,
            changed & ~prev_active & current_active,
            changed & prev_active & ~current_active,
            changed & current_active & (current.abs() > previous.abs()),
            changed & current_active & (current.abs() <= previous.abs()),
        ],
        ["no_action", "hold", "buy", "sell", "add", "reduce"],
        default="no_action",
    )
    return pd.Series(actions, index=previous_weight.index, dtype="object")


def _default_primary_reason(actions: pd.Series) -> pd.Series:
    reason_map = {
        "buy": "entered_position",
        "sell": "exited_position",
        "add": "increased_weight",
        "reduce": "reduced_weight",
        "hold": "held_weight",
        "no_action": "no_position",
    }
    return actions.map(reason_map).fillna("unknown")


def _rank_pct(frame: pd.DataFrame, value_col: str) -> pd.Series:
    return frame.groupby([STRATEGY_ID, "date"], dropna=False, sort=False)[value_col].transform(
        lambda series: series.rank(method="average", pct=True)
    )


def _rank_desc(frame: pd.DataFrame, value_col: str) -> pd.Series:
    ranked = frame.groupby([STRATEGY_ID, "date"], dropna=False, sort=False)[value_col].transform(
        lambda series: series.rank(method="min", ascending=False)
    )
    return ranked.astype("Int64")


def _as_vote(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return numeric > 0


def _attach_category(
    frame: pd.DataFrame,
    category_map: Mapping[str, str] | pd.Series | pd.DataFrame | None,
) -> pd.DataFrame:
    out = frame.copy()
    if category_map is None:
        return out
    if isinstance(category_map, pd.DataFrame):
        category = category_map.copy()
        symbol_col = _find_column(category, SYMBOL_COLUMNS)
        category_col = _find_column(category, ("category",))
        if symbol_col is None or category_col is None:
            raise ValueError("category_map DataFrame must include symbol and category columns.")
        category = category[[symbol_col, category_col]].rename(
            columns={symbol_col: "symbol", category_col: "category"}
        )
        out = out.merge(category.drop_duplicates("symbol"), on="symbol", how="left")
    else:
        mapping = (
            category_map.to_dict() if isinstance(category_map, pd.Series) else dict(category_map)
        )
        out["category"] = out["symbol"].map(mapping)
    return out


def _order_snapshot_columns(
    frame: pd.DataFrame,
    component_names: Sequence[str],
    raw_suffix: str,
) -> pd.DataFrame:
    leading = ["date", STRATEGY_ID, "symbol", "category"]
    component_cols = []
    for name in component_names:
        component_cols.extend([f"{name}{raw_suffix}", f"{name}_rank_pct", f"{name}_rank"])
    trailing = [
        "valid_factor_count",
        "factor5_score",
        "coverage_flag",
        "coverage_reason",
        "cross_section_rank_pct",
        "cross_section_rank",
    ]
    return _select_existing(frame, leading + component_cols + trailing)


def _select_existing(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    selected = [col for col in columns if col in frame.columns]
    extra = [col for col in frame.columns if col not in selected]
    return (
        frame[selected + extra].sort_values([STRATEGY_ID, "date", "symbol"]).reset_index(drop=True)
    )
