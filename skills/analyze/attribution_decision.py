"""Decision-edge attribution for factor ranks and vote thresholds."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

DATE_COL = "date"
EOB_COL = "eob"
SYMBOL_COL = "symbol"
STRATEGY_COL = "strategy_id"
CATEGORY_COL = "category"
DEFAULT_STRATEGY_ID = "default"

PLAYER_NAME_COL = "player_name"
PLAYER_TYPE_COL = "player_type"
FACTOR_PLAYER_TYPE = "factor"
VOTE_PLAYER_TYPE = "vote"

EDGE_BOOL_COLS = (
    "topk_entry_edge",
    "exit_prevent_edge",
    "eligible_full",
    "eligible_without_vote",
    "entry_critical",
    "exit_critical",
    "hold_critical",
    "topk_edge",
)

DECISION_EDGE_COLUMNS = [
    DATE_COL,
    STRATEGY_COL,
    SYMBOL_COL,
    CATEGORY_COL,
    PLAYER_NAME_COL,
    PLAYER_TYPE_COL,
    "rank_full",
    "rank_without_player",
    "rank_push",
    "topk_entry_edge",
    "exit_prevent_edge",
    "score_full",
    "score_without_player",
    "score_share",
    "factor_rank_pct",
    "vote_value",
    "vote_count_full",
    "vote_count_without_vote",
    "eligible_full",
    "eligible_without_vote",
    "entry_critical",
    "exit_critical",
    "hold_critical",
    "topk_edge",
    "valid_player_count",
    "player_coverage",
    "status",
    "skip_reason",
]


def factor_rank_edge_attribution(
    factor_snapshot: pd.DataFrame,
    factor_cols: Sequence[str],
    top_k: int,
    exit_rank: int | None = None,
    strategy_id: str | None = None,
) -> pd.DataFrame:
    """Attribute top-k and exit-rank decision edges to leave-one-factor-out rank shifts."""
    _require_dataframe(factor_snapshot, "factor_snapshot")
    factor_cols = _normalize_name_list(factor_cols, "factor_cols")
    _validate_positive_int(top_k, "top_k")
    if exit_rank is not None:
        _validate_positive_int(exit_rank, "exit_rank")

    snapshot = _prepare_snapshot(factor_snapshot, strategy_id)
    if snapshot.empty:
        return _empty_decision_edges()

    existing_factor_cols = [col for col in factor_cols if col in snapshot.columns]
    rows: list[pd.DataFrame] = []
    for (_, _), group in snapshot.groupby([DATE_COL, STRATEGY_COL], sort=True, dropna=False):
        rows.extend(
            _factor_group_edges(
                group=group,
                factor_cols=factor_cols,
                existing_factor_cols=existing_factor_cols,
                top_k=top_k,
                exit_rank=exit_rank,
            )
        )

    if not rows:
        return _empty_decision_edges()
    result = pd.concat(rows, ignore_index=True)
    return _finalize_edge_table(result)


def vote_criticality_attribution(
    vote_snapshot: pd.DataFrame,
    vote_cols: Sequence[str],
    threshold: int = 5,
    selected_col: str | None = None,
    held_col: str | None = None,
    strategy_id: str | None = None,
) -> pd.DataFrame:
    """Attribute vote threshold eligibility to leave-one-vote-out criticality."""
    _require_dataframe(vote_snapshot, "vote_snapshot")
    vote_cols = _normalize_name_list(vote_cols, "vote_cols")
    _validate_positive_int(threshold, "threshold")

    snapshot = _prepare_snapshot(vote_snapshot, strategy_id)
    if snapshot.empty:
        return _empty_decision_edges()

    existing_vote_cols = [col for col in vote_cols if col in snapshot.columns]
    vote_values = pd.DataFrame(index=snapshot.index)
    for col in existing_vote_cols:
        vote_values[col] = _coerce_vote_series(snapshot[col])

    valid_vote_count = (
        vote_values.notna().sum(axis=1)
        if existing_vote_cols
        else pd.Series(0, index=snapshot.index)
    )
    vote_count_full = (
        vote_values.fillna(0.0).sum(axis=1)
        if existing_vote_cols
        else pd.Series(0.0, index=snapshot.index)
    )
    eligible_full = vote_count_full >= float(threshold)
    selected = _coerce_optional_flag(snapshot, selected_col, eligible_full)
    held = _coerce_optional_flag(snapshot, held_col, pd.Series(False, index=snapshot.index))

    rows = []
    base = snapshot[_identity_columns(snapshot)].copy()
    base["valid_player_count"] = valid_vote_count.astype(int).to_numpy()
    base["vote_count_full"] = vote_count_full.astype(float).to_numpy()
    base["eligible_full"] = eligible_full.to_numpy()

    for vote_col in vote_cols:
        current = base.copy()
        current[PLAYER_NAME_COL] = vote_col
        current[PLAYER_TYPE_COL] = VOTE_PLAYER_TYPE
        if vote_col not in vote_values.columns:
            current["vote_value"] = np.nan
            current["vote_count_without_vote"] = np.nan
            current["eligible_without_vote"] = False
            current["entry_critical"] = False
            current["exit_critical"] = False
            current["hold_critical"] = False
            current["topk_edge"] = False
            current["topk_entry_edge"] = False
            current["exit_prevent_edge"] = False
            current["score_share"] = np.nan
            current["status"] = "skipped"
            current["skip_reason"] = "missing_player"
        else:
            vote_value = vote_values[vote_col]
            vote_without = vote_count_full - vote_value.fillna(0.0)
            eligible_without = vote_without >= float(threshold)
            critical = eligible_full & ~eligible_without
            entry_critical = selected & critical
            hold_critical = held & critical

            current["vote_value"] = vote_value.to_numpy(dtype=float)
            current["vote_count_without_vote"] = vote_without.to_numpy(dtype=float)
            current["eligible_without_vote"] = eligible_without.to_numpy()
            current["entry_critical"] = entry_critical.to_numpy()
            current["exit_critical"] = hold_critical.to_numpy()
            current["hold_critical"] = hold_critical.to_numpy()
            current["topk_edge"] = entry_critical.to_numpy()
            current["topk_entry_edge"] = entry_critical.to_numpy()
            current["exit_prevent_edge"] = hold_critical.to_numpy()
            current["score_share"] = _safe_share(vote_value, vote_count_full).to_numpy(dtype=float)
            current["status"] = np.where(vote_value.notna(), "ok", "skipped")
            current["skip_reason"] = np.where(vote_value.notna(), "", "player_value_missing")

        current["rank_full"] = np.nan
        current["rank_without_player"] = np.nan
        current["rank_push"] = np.nan
        current["score_full"] = current["vote_count_full"].astype(float)
        current["score_without_player"] = current["vote_count_without_vote"].astype(float)
        current["factor_rank_pct"] = np.nan
        current["player_coverage"] = _coverage_value(current["vote_value"])
        rows.append(current)

    if not rows:
        return _empty_decision_edges()
    result = pd.concat(rows, ignore_index=True)
    return _finalize_edge_table(result)


def summarize_decision_edges(
    edge_table: pd.DataFrame,
    group_cols: Sequence[str] = (STRATEGY_COL, PLAYER_NAME_COL),
) -> pd.DataFrame:
    """Summarize decision-edge counts and average rank push by player."""
    _require_dataframe(edge_table, "edge_table")
    group_cols = tuple(group_cols)
    _require_columns(edge_table, group_cols, "edge_table")

    columns = list(group_cols) + [
        "rows",
        "ok_rows",
        "skipped_rows",
        "topk_entry_edge_count",
        "exit_prevent_edge_count",
        "entry_critical_count",
        "exit_critical_count",
        "hold_critical_count",
        "topk_edge_count",
        "critical_count",
        "avg_rank_push",
        "positive_rank_push_count",
    ]
    if edge_table.empty:
        return pd.DataFrame(columns=columns)

    data = edge_table.copy()
    for col in EDGE_BOOL_COLS:
        if col not in data.columns:
            data[col] = False
        data[col] = _as_bool_series(data[col])
    if "status" not in data.columns:
        data["status"] = ""
    if "rank_push" not in data.columns:
        data["rank_push"] = np.nan
    data["rank_push"] = pd.to_numeric(data["rank_push"], errors="coerce")
    data["_is_ok"] = data["status"].eq("ok")
    data["_is_critical"] = data[["entry_critical", "exit_critical", "hold_critical"]].any(axis=1)
    data["_is_decision_edge"] = data[
        [
            "topk_entry_edge",
            "exit_prevent_edge",
            "topk_edge",
            "entry_critical",
            "exit_critical",
            "hold_critical",
        ]
    ].any(axis=1)
    data["_positive_rank_push"] = data["rank_push"] > 0.0
    data["_edge_rank_push"] = data["rank_push"].where(data["_is_decision_edge"])

    summary = (
        data.groupby(list(group_cols), dropna=False, sort=True)
        .agg(
            rows=(PLAYER_NAME_COL, "size"),
            ok_rows=("_is_ok", "sum"),
            topk_entry_edge_count=("topk_entry_edge", "sum"),
            exit_prevent_edge_count=("exit_prevent_edge", "sum"),
            entry_critical_count=("entry_critical", "sum"),
            exit_critical_count=("exit_critical", "sum"),
            hold_critical_count=("hold_critical", "sum"),
            topk_edge_count=("topk_edge", "sum"),
            critical_count=("_is_critical", "sum"),
            avg_rank_push=("_edge_rank_push", "mean"),
            positive_rank_push_count=("_positive_rank_push", "sum"),
        )
        .reset_index()
    )
    summary["skipped_rows"] = summary["rows"] - summary["ok_rows"]
    return summary[columns]


def _factor_group_edges(
    *,
    group: pd.DataFrame,
    factor_cols: Sequence[str],
    existing_factor_cols: Sequence[str],
    top_k: int,
    exit_rank: int | None,
) -> list[pd.DataFrame]:
    base = group.drop_duplicates(SYMBOL_COL, keep="last").copy()
    base_cols = _identity_columns(base)
    output_base = base[base_cols].copy()

    ranks = pd.DataFrame(index=base.index)
    for col in existing_factor_cols:
        ranks[col] = pd.to_numeric(base[col], errors="coerce").rank(pct=True, method="average")

    valid_player_count = (
        ranks.notna().sum(axis=1) if existing_factor_cols else pd.Series(0, index=base.index)
    )
    score_full = (
        ranks.mean(axis=1, skipna=True)
        if existing_factor_cols
        else pd.Series(np.nan, index=base.index)
    )
    rank_full = _rank_desc(score_full)
    factor_coverage = {
        col: _coverage_value(pd.to_numeric(base[col], errors="coerce"))
        for col in existing_factor_cols
    }
    constant_factors = {
        col
        for col in existing_factor_cols
        if pd.to_numeric(base[col], errors="coerce").nunique(dropna=True) <= 1
    }

    rows: list[pd.DataFrame] = []
    for factor_col in factor_cols:
        current = output_base.copy()
        current[PLAYER_NAME_COL] = factor_col
        current[PLAYER_TYPE_COL] = FACTOR_PLAYER_TYPE
        current["score_full"] = score_full.to_numpy(dtype=float)
        current["rank_full"] = rank_full.to_numpy(dtype=float)
        current["valid_player_count"] = valid_player_count.astype(int).to_numpy()
        current["vote_value"] = np.nan
        current["vote_count_full"] = np.nan
        current["vote_count_without_vote"] = np.nan
        current["eligible_full"] = False
        current["eligible_without_vote"] = False
        current["entry_critical"] = False
        current["exit_critical"] = False
        current["hold_critical"] = False
        current["topk_edge"] = False

        if factor_col not in ranks.columns:
            current["factor_rank_pct"] = np.nan
            current["score_without_player"] = np.nan
            current["rank_without_player"] = np.nan
            current["rank_push"] = np.nan
            current["topk_entry_edge"] = False
            current["exit_prevent_edge"] = False
            current["score_share"] = np.nan
            current["player_coverage"] = 0.0
            current["status"] = "skipped"
            current["skip_reason"] = "missing_player"
            rows.append(current)
            continue

        without_cols = [col for col in existing_factor_cols if col != factor_col]
        score_without = (
            ranks[without_cols].mean(axis=1, skipna=True)
            if without_cols
            else pd.Series(np.nan, index=base.index)
        )
        rank_without = _rank_desc(score_without)
        rank_push = rank_without - rank_full
        factor_rank = ranks[factor_col]
        topk_entry_edge = (rank_full <= top_k) & (rank_without > top_k)
        if exit_rank is None:
            exit_prevent_edge = pd.Series(False, index=base.index)
        else:
            exit_prevent_edge = (rank_full <= exit_rank) & (rank_without > exit_rank)

        current["factor_rank_pct"] = factor_rank.to_numpy(dtype=float)
        current["score_without_player"] = score_without.to_numpy(dtype=float)
        current["rank_without_player"] = rank_without.to_numpy(dtype=float)
        current["rank_push"] = rank_push.to_numpy(dtype=float)
        current["topk_entry_edge"] = topk_entry_edge.fillna(False).to_numpy()
        current["exit_prevent_edge"] = exit_prevent_edge.fillna(False).to_numpy()
        current["score_share"] = _safe_share(factor_rank, ranks.sum(axis=1, skipna=True)).to_numpy(
            dtype=float
        )
        current["player_coverage"] = factor_coverage[factor_col]

        status, skip_reason = _factor_row_status(
            factor_col=factor_col,
            factor_rank=factor_rank,
            score_full=score_full,
            score_without=score_without,
            constant_factors=constant_factors,
        )
        current["status"] = status.to_numpy()
        current["skip_reason"] = skip_reason.to_numpy()
        rows.append(current)

    return rows


def _factor_row_status(
    *,
    factor_col: str,
    factor_rank: pd.Series,
    score_full: pd.Series,
    score_without: pd.Series,
    constant_factors: set[str],
) -> tuple[pd.Series, pd.Series]:
    status = pd.Series("ok", index=factor_rank.index, dtype=object)
    reason = pd.Series("", index=factor_rank.index, dtype=object)

    if factor_col in constant_factors:
        status.loc[:] = "skipped"
        reason.loc[:] = "constant_or_all_nan_factor"
        return status, reason

    missing_player = factor_rank.isna()
    no_full_score = score_full.isna()
    no_without_score = score_without.isna()

    status.loc[missing_player | no_full_score | no_without_score] = "skipped"
    reason.loc[missing_player] = "player_value_missing"
    reason.loc[no_full_score] = "no_valid_factor_score"
    reason.loc[no_without_score] = "no_without_score"
    return status, reason


def _prepare_snapshot(snapshot: pd.DataFrame, strategy_id: str | None) -> pd.DataFrame:
    _require_columns(snapshot, (SYMBOL_COL,), "snapshot")
    date_col = _detect_date_column(snapshot)
    if date_col is None:
        raise ValueError("snapshot is missing required columns: date or eob")

    keep_cols = [date_col, SYMBOL_COL]
    if STRATEGY_COL in snapshot.columns:
        keep_cols.append(STRATEGY_COL)
    if CATEGORY_COL in snapshot.columns:
        keep_cols.append(CATEGORY_COL)
    value_cols = [col for col in snapshot.columns if col not in set(keep_cols)]
    out = snapshot[keep_cols + value_cols].copy()
    out = out.rename(columns={date_col: DATE_COL})
    out[DATE_COL] = pd.to_datetime(out[DATE_COL])
    if STRATEGY_COL not in out.columns:
        out[STRATEGY_COL] = strategy_id if strategy_id is not None else DEFAULT_STRATEGY_ID
    elif strategy_id is not None:
        out[STRATEGY_COL] = strategy_id
    if CATEGORY_COL not in out.columns:
        out[CATEGORY_COL] = ""
    return out


def _identity_columns(frame: pd.DataFrame) -> list[str]:
    return [DATE_COL, STRATEGY_COL, SYMBOL_COL, CATEGORY_COL]


def _detect_date_column(frame: pd.DataFrame) -> str | None:
    if DATE_COL in frame.columns:
        return DATE_COL
    if EOB_COL in frame.columns:
        return EOB_COL
    return None


def _rank_desc(score: pd.Series) -> pd.Series:
    return pd.to_numeric(score, errors="coerce").rank(ascending=False, method="min")


def _safe_share(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    return num.div(den.where(den.ne(0.0)))


def _coverage_value(values: pd.Series) -> float:
    if len(values) == 0:
        return 0.0
    return float(pd.to_numeric(values, errors="coerce").notna().mean())


def _coerce_vote_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)

    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any():
        return numeric.where(numeric.isna(), (numeric > 0.0).astype(float))

    text = series.astype("string").str.strip().str.lower()
    mapped = text.map({"true": 1.0, "false": 0.0, "yes": 1.0, "no": 0.0})
    return pd.to_numeric(mapped, errors="coerce")


def _coerce_optional_flag(
    frame: pd.DataFrame,
    col: str | None,
    default: pd.Series,
) -> pd.Series:
    if col is None or col not in frame.columns:
        return default.astype(bool)
    values = _coerce_vote_series(frame[col])
    return values.fillna(0.0).astype(bool)


def _as_bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0.0).ne(0.0)
    return series.fillna(False).map(bool)


def _finalize_edge_table(result: pd.DataFrame) -> pd.DataFrame:
    for col in DECISION_EDGE_COLUMNS:
        if col not in result.columns:
            result[col] = np.nan
    for col in EDGE_BOOL_COLS:
        if col in result.columns:
            result[col] = _as_bool_series(result[col]).map(bool).astype(object)
    result["status"] = result["status"].fillna("skipped").astype(str)
    result["skip_reason"] = result["skip_reason"].fillna("").astype(str)
    numeric_cols = [
        "rank_full",
        "rank_without_player",
        "rank_push",
        "score_full",
        "score_without_player",
        "score_share",
        "factor_rank_pct",
        "vote_value",
        "vote_count_full",
        "vote_count_without_vote",
        "valid_player_count",
        "player_coverage",
    ]
    for col in numeric_cols:
        result[col] = pd.to_numeric(result[col], errors="coerce")

    sort_cols = [DATE_COL, STRATEGY_COL, SYMBOL_COL, PLAYER_TYPE_COL, PLAYER_NAME_COL]
    return result[DECISION_EDGE_COLUMNS].sort_values(sort_cols).reset_index(drop=True)


def _empty_decision_edges() -> pd.DataFrame:
    return pd.DataFrame(columns=DECISION_EDGE_COLUMNS)


def _require_dataframe(value: Any, name: str) -> None:
    if not isinstance(value, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame.")


def _require_columns(frame: pd.DataFrame, cols: Sequence[str], frame_name: str) -> None:
    missing = [col for col in cols if col not in frame.columns]
    if missing:
        raise ValueError(f"{frame_name} is missing required columns: {', '.join(missing)}")


def _normalize_name_list(names: Sequence[str], name: str) -> list[str]:
    if isinstance(names, str) or not isinstance(names, Sequence):
        raise TypeError(f"{name} must be a sequence of column names.")
    out = [str(item) for item in names]
    if not out:
        raise ValueError(f"{name} must contain at least one column name.")
    return out


def _validate_positive_int(value: int, name: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")


__all__ = [
    "factor_rank_edge_attribution",
    "vote_criticality_attribution",
    "summarize_decision_edges",
]
