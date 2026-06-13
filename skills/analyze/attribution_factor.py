"""Cross-sectional factor regression attribution for ETF portfolios."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

DATE_COL = "date"
SYMBOL_COL = "symbol"
STRATEGY_COL = "strategy_id"
RETURN_COL = "ret_1d_fwd"
CATEGORY_COL = "category"
DEFAULT_STRATEGY_ID = "default"
INTERCEPT_TERM = "intercept"
MODEL_TERM = "model"

RESERVED_FACTOR_COLUMNS = {
    DATE_COL,
    STRATEGY_COL,
    SYMBOL_COL,
    RETURN_COL,
    CATEGORY_COL,
    "age_days",
    "valid_factor_count",
    "w_exec",
    "weight",
    "w_target",
}


@dataclass(frozen=True)
class DesignMatrix:
    values: pd.DataFrame
    term_types: dict[str, str]
    skipped_factors: dict[str, str]


def cross_sectional_factor_attribution(
    factor_snapshot: pd.DataFrame,
    symbol_returns: pd.DataFrame,
    portfolio_weights: pd.DataFrame,
    *,
    benchmark_weights: pd.DataFrame | None = None,
    factor_cols: Sequence[str] | None = None,
    return_col: str = RETURN_COL,
    portfolio_weight_col: str = "w_exec",
    benchmark_weight_col: str = "weight",
    include_category: bool = False,
    include_controls: bool = True,
    control_cols: Sequence[str] | None = None,
    min_obs: int = 3,
    ridge_alpha: float = 1e-6,
    regression_weight_col: str | None = None,
    strategy_id: str | None = None,
) -> pd.DataFrame:
    """Run daily cross-sectional factor regression attribution.

    The returned table contains one row per date, strategy, and model term. Factor rows have
    `term_type == "factor"` and carry the factor beta, active exposure, and contribution.
    Diagnostic rows use `term == "model"`.
    """
    _require_dataframe(factor_snapshot, "factor_snapshot")
    _require_dataframe(symbol_returns, "symbol_returns")
    _require_dataframe(portfolio_weights, "portfolio_weights")
    _require_columns(factor_snapshot, (DATE_COL, SYMBOL_COL), "factor_snapshot")
    _require_columns(symbol_returns, (DATE_COL, SYMBOL_COL, return_col), "symbol_returns")
    if min_obs <= 0:
        raise ValueError("min_obs must be positive.")
    if ridge_alpha < 0:
        raise ValueError("ridge_alpha must be non-negative.")

    factors = _prepare_factor_snapshot(factor_snapshot, strategy_id)
    returns = _prepare_returns(symbol_returns, return_col)
    portfolio = _prepare_weight_frame(
        portfolio_weights,
        weight_col=portfolio_weight_col,
        output_col="portfolio_weight",
        df_name="portfolio_weights",
        strategy_id=strategy_id,
    )
    benchmark = (
        _prepare_weight_frame(
            benchmark_weights,
            weight_col=benchmark_weight_col,
            output_col="benchmark_weight",
            df_name="benchmark_weights",
            strategy_id=None,
            keep_strategy=False,
        )
        if benchmark_weights is not None
        else None
    )

    selected_factor_cols = _resolve_factor_cols(factors, factor_cols)
    selected_control_cols = _resolve_control_cols(factors, control_cols, include_controls)

    base = factors.merge(returns, on=[DATE_COL, SYMBOL_COL], how="inner")
    if base.empty:
        return _empty_result()

    results: list[pd.DataFrame] = []
    group_cols = [DATE_COL, STRATEGY_COL]
    for (date, current_strategy), group in base.groupby(group_cols, sort=True):
        portfolio_slice = _slice_strategy_weights(
            portfolio, date, current_strategy, "portfolio_weight"
        )
        benchmark_slice = (
            _slice_benchmark_weights(benchmark, date)
            if benchmark is not None
            else _equal_weight_benchmark(group)
        )
        rows = _attribute_one_day(
            group=group,
            date=date,
            strategy_id=current_strategy,
            portfolio_weights=portfolio_slice,
            benchmark_weights=benchmark_slice,
            factor_cols=selected_factor_cols,
            control_cols=selected_control_cols,
            return_col=return_col,
            include_category=include_category,
            min_obs=min_obs,
            ridge_alpha=ridge_alpha,
            regression_weight_col=regression_weight_col,
        )
        results.append(rows)

    if not results:
        return _empty_result()
    return (
        pd.concat(results, ignore_index=True)
        .sort_values([DATE_COL, STRATEGY_COL, "term_type", "term"])
        .reset_index(drop=True)
    )


def summarize_factor_attribution(
    attribution: pd.DataFrame,
    *,
    group_cols: Sequence[str] = (STRATEGY_COL, "term"),
    term_type: str = "factor",
) -> pd.DataFrame:
    """Summarize factor attribution rows across dates."""
    _require_dataframe(attribution, "attribution")
    _require_columns(
        attribution,
        (
            DATE_COL,
            "term",
            "term_type",
            "status",
            "beta",
            "active_exposure",
            "contribution",
        ),
        "attribution",
    )
    group_cols = tuple(group_cols)
    _require_columns(attribution, group_cols, "attribution")

    rows = attribution.loc[attribution["term_type"] == term_type].copy()
    if rows.empty:
        columns = list(group_cols) + [
            "period",
            "avg_beta",
            "avg_active_exposure",
            "total_contribution",
            "avg_contribution",
            "ok_days",
            "skipped_days",
            "n_days",
        ]
        return pd.DataFrame(columns=columns)

    rows["is_ok"] = rows["status"].eq("ok")
    summary = (
        rows.groupby(list(group_cols), as_index=False)
        .agg(
            avg_beta=("beta", "mean"),
            avg_active_exposure=("active_exposure", "mean"),
            total_contribution=("contribution", "sum"),
            avg_contribution=("contribution", "mean"),
            ok_days=("is_ok", "sum"),
            n_days=(DATE_COL, "nunique"),
        )
        .sort_values(list(group_cols))
        .reset_index(drop=True)
    )
    summary["skipped_days"] = summary["n_days"] - summary["ok_days"]
    summary["period"] = "full"
    ordered = list(group_cols) + [
        "period",
        "avg_beta",
        "avg_active_exposure",
        "total_contribution",
        "avg_contribution",
        "ok_days",
        "skipped_days",
        "n_days",
    ]
    return summary[ordered]


def _attribute_one_day(
    *,
    group: pd.DataFrame,
    date: Any,
    strategy_id: Any,
    portfolio_weights: pd.DataFrame,
    benchmark_weights: pd.DataFrame,
    factor_cols: Sequence[str],
    control_cols: Sequence[str],
    return_col: str,
    include_category: bool,
    min_obs: int,
    ridge_alpha: float,
    regression_weight_col: str | None,
) -> pd.DataFrame:
    data = group.copy()
    data[DATE_COL] = pd.to_datetime(data[DATE_COL])
    data = data.dropna(subset=[return_col]).drop_duplicates(SYMBOL_COL, keep="last")
    data = data.merge(portfolio_weights, on=SYMBOL_COL, how="left")
    data = data.merge(benchmark_weights, on=SYMBOL_COL, how="left")
    data[["portfolio_weight", "benchmark_weight"]] = data[
        ["portfolio_weight", "benchmark_weight"]
    ].fillna(0.0)

    n_obs = len(data)
    design = _build_design_matrix(
        data,
        factor_cols=factor_cols,
        control_cols=control_cols,
        include_category=include_category,
    )
    diagnostics = _daily_diagnostics(
        data=data,
        return_col=return_col,
    )

    if n_obs < min_obs:
        return _skipped_rows(
            date=date,
            strategy_id=strategy_id,
            factor_cols=factor_cols,
            skipped_factors=dict.fromkeys(factor_cols, "insufficient_observations"),
            diagnostics=diagnostics,
            status="skipped",
            skip_reason="insufficient_observations",
        )

    if not design.values.columns.difference([INTERCEPT_TERM]).any():
        reason = "no_valid_factor_terms"
        return _skipped_rows(
            date=date,
            strategy_id=strategy_id,
            factor_cols=factor_cols,
            skipped_factors={col: design.skipped_factors.get(col, reason) for col in factor_cols},
            diagnostics=diagnostics,
            status="skipped",
            skip_reason=reason,
        )

    y = data[return_col].astype(float).to_numpy()
    weights = _regression_weights(data, regression_weight_col)
    beta = _ridge_wls(design.values.to_numpy(dtype=float), y, weights, ridge_alpha)
    if beta is None:
        return _skipped_rows(
            date=date,
            strategy_id=strategy_id,
            factor_cols=factor_cols,
            skipped_factors=dict.fromkeys(factor_cols, "singular_design"),
            diagnostics=diagnostics,
            status="skipped",
            skip_reason="singular_design",
        )

    active_weight = (
        data["portfolio_weight"].astype(float) - data["benchmark_weight"].astype(float)
    ).to_numpy()
    exposure = design.values.mul(active_weight, axis=0).sum(axis=0)
    rows = []
    beta_by_term = dict(zip(design.values.columns, beta, strict=True))
    for term in design.values.columns:
        term_beta = float(beta_by_term[term])
        term_exposure = float(exposure.loc[term])
        rows.append(
            {
                DATE_COL: date,
                STRATEGY_COL: strategy_id,
                "term": term,
                "term_type": design.term_types[term],
                "beta": term_beta,
                "active_exposure": term_exposure,
                "contribution": term_beta * term_exposure,
                "status": "ok",
                "skip_reason": "",
                "n_obs": n_obs,
                "n_terms": len(design.values.columns),
                **diagnostics,
            }
        )

    for factor, reason in design.skipped_factors.items():
        if factor not in design.values.columns:
            rows.append(
                {
                    DATE_COL: date,
                    STRATEGY_COL: strategy_id,
                    "term": factor,
                    "term_type": "factor",
                    "beta": np.nan,
                    "active_exposure": np.nan,
                    "contribution": np.nan,
                    "status": "skipped",
                    "skip_reason": reason,
                    "n_obs": n_obs,
                    "n_terms": len(design.values.columns),
                    **diagnostics,
                }
            )

    model_total = float(sum(row["contribution"] for row in rows if row["status"] == "ok"))
    for row in rows:
        row["daily_attribution_total"] = model_total
        row["reconcile_residual"] = row["active_return"] - model_total

    model_row = {
        DATE_COL: date,
        STRATEGY_COL: strategy_id,
        "term": MODEL_TERM,
        "term_type": "diagnostic",
        "beta": np.nan,
        "active_exposure": np.nan,
        "contribution": model_total,
        "status": "ok",
        "skip_reason": "",
        "n_obs": n_obs,
        "n_terms": len(design.values.columns),
        **diagnostics,
    }
    model_row["daily_attribution_total"] = model_total
    model_row["reconcile_residual"] = model_row["active_return"] - model_total
    return pd.DataFrame([*rows, model_row])


def _build_design_matrix(
    data: pd.DataFrame,
    *,
    factor_cols: Sequence[str],
    control_cols: Sequence[str],
    include_category: bool,
) -> DesignMatrix:
    matrix = pd.DataFrame(index=data.index)
    matrix[INTERCEPT_TERM] = 1.0
    term_types = {INTERCEPT_TERM: "intercept"}
    skipped_factors: dict[str, str] = {}

    for col in factor_cols:
        z = _zscore(data[col])
        if z is None:
            skipped_factors[col] = "constant_or_all_nan_factor"
            continue
        matrix[col] = z
        term_types[col] = "factor"

    for col in control_cols:
        if col not in data.columns:
            continue
        z = _zscore(data[col])
        if z is None:
            continue
        matrix[col] = z
        term_types[col] = "control"

    if include_category and CATEGORY_COL in data.columns:
        dummies = _category_dummies(
            data[CATEGORY_COL], max_dummies=max(len(data) - len(matrix.columns), 0)
        )
        for col in dummies.columns:
            matrix[col] = dummies[col]
            term_types[col] = "category"

    return DesignMatrix(values=matrix, term_types=term_types, skipped_factors=skipped_factors)


def _zscore(series: pd.Series) -> pd.Series | None:
    values = pd.to_numeric(series, errors="coerce").astype(float)
    if values.notna().sum() < 2:
        return None
    mean = values.mean(skipna=True)
    std = values.std(ddof=0, skipna=True)
    if not np.isfinite(std) or std <= 0.0:
        return None
    return ((values - mean) / std).fillna(0.0)


def _category_dummies(categories: pd.Series, *, max_dummies: int) -> pd.DataFrame:
    if max_dummies <= 0:
        return pd.DataFrame(index=categories.index)
    clean = categories.astype("object").where(categories.notna(), "missing")
    dummies = pd.get_dummies(clean, prefix="category", prefix_sep=":", dtype=float)
    if dummies.shape[1] <= 1:
        return pd.DataFrame(index=categories.index)
    dummies = dummies.reindex(sorted(dummies.columns), axis=1)
    return dummies.iloc[:, 1 : max_dummies + 1]


def _ridge_wls(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    ridge_alpha: float,
) -> np.ndarray | None:
    valid = np.isfinite(y) & np.isfinite(x).all(axis=1) & np.isfinite(weights) & (weights > 0.0)
    if valid.sum() == 0:
        return None
    x_valid = x[valid]
    y_valid = y[valid]
    w_sqrt = np.sqrt(weights[valid])
    xw = x_valid * w_sqrt[:, None]
    yw = y_valid * w_sqrt
    penalty = np.eye(xw.shape[1]) * ridge_alpha
    penalty[0, 0] = 0.0
    lhs = xw.T @ xw + penalty
    rhs = xw.T @ yw
    try:
        return np.linalg.solve(lhs, rhs)
    except np.linalg.LinAlgError:
        if ridge_alpha == 0.0:
            return np.linalg.pinv(lhs) @ rhs
        return None


def _regression_weights(data: pd.DataFrame, regression_weight_col: str | None) -> np.ndarray:
    if regression_weight_col is None or regression_weight_col not in data.columns:
        return np.ones(len(data), dtype=float)
    weights = pd.to_numeric(data[regression_weight_col], errors="coerce").astype(float)
    return weights.fillna(0.0).clip(lower=0.0).to_numpy()


def _daily_diagnostics(
    *,
    data: pd.DataFrame,
    return_col: str,
) -> dict[str, float | int]:
    portfolio_return = float((data["portfolio_weight"] * data[return_col]).sum())
    benchmark_return = float((data["benchmark_weight"] * data[return_col]).sum())
    return {
        "portfolio_return": portfolio_return,
        "benchmark_return": benchmark_return,
        "active_return": portfolio_return - benchmark_return,
        "portfolio_total_weight": float(data["portfolio_weight"].sum()),
        "benchmark_total_weight": float(data["benchmark_weight"].sum()),
        "daily_active_return": portfolio_return - benchmark_return,
        "daily_attribution_total": np.nan,
        "reconcile_residual": np.nan,
    }


def _skipped_rows(
    *,
    date: Any,
    strategy_id: Any,
    factor_cols: Sequence[str],
    skipped_factors: dict[str, str],
    diagnostics: dict[str, Any],
    status: str,
    skip_reason: str,
) -> pd.DataFrame:
    rows = []
    for factor in factor_cols:
        rows.append(
            {
                DATE_COL: date,
                STRATEGY_COL: strategy_id,
                "term": factor,
                "term_type": "factor",
                "beta": np.nan,
                "active_exposure": np.nan,
                "contribution": np.nan,
                "status": status,
                "skip_reason": skipped_factors.get(factor, skip_reason),
                "n_obs": np.nan,
                "n_terms": np.nan,
                **diagnostics,
            }
        )
    rows.append(
        {
            DATE_COL: date,
            STRATEGY_COL: strategy_id,
            "term": MODEL_TERM,
            "term_type": "diagnostic",
            "beta": np.nan,
            "active_exposure": np.nan,
            "contribution": np.nan,
            "status": status,
            "skip_reason": skip_reason,
            "n_obs": np.nan,
            "n_terms": np.nan,
            **diagnostics,
        }
    )
    return pd.DataFrame(rows)


def _prepare_factor_snapshot(
    factor_snapshot: pd.DataFrame, strategy_id: str | None
) -> pd.DataFrame:
    out = factor_snapshot.copy()
    out[DATE_COL] = pd.to_datetime(out[DATE_COL])
    if STRATEGY_COL not in out.columns:
        out[STRATEGY_COL] = strategy_id if strategy_id is not None else DEFAULT_STRATEGY_ID
    elif strategy_id is not None:
        out[STRATEGY_COL] = strategy_id
    return out


def _prepare_returns(symbol_returns: pd.DataFrame, return_col: str) -> pd.DataFrame:
    returns = symbol_returns[[DATE_COL, SYMBOL_COL, return_col]].copy()
    returns[DATE_COL] = pd.to_datetime(returns[DATE_COL])
    return returns.drop_duplicates([DATE_COL, SYMBOL_COL], keep="last")


def _prepare_weight_frame(
    weights: pd.DataFrame,
    *,
    weight_col: str,
    output_col: str,
    df_name: str,
    strategy_id: str | None,
    keep_strategy: bool = True,
) -> pd.DataFrame:
    _require_dataframe(weights, df_name)
    if DATE_COL in weights.columns and SYMBOL_COL in weights.columns:
        selected = _choose_column(
            weights,
            weight_col,
            fallback_cols=("weight", "w_exec", "w_target", "w_bench", "w_benchmark"),
            df_name=df_name,
        )
        cols = [DATE_COL, SYMBOL_COL, selected]
        out = weights[cols].copy().rename(columns={selected: output_col})
        if keep_strategy:
            if STRATEGY_COL in weights.columns and strategy_id is None:
                out[STRATEGY_COL] = weights[STRATEGY_COL].to_numpy()
            else:
                out[STRATEGY_COL] = strategy_id if strategy_id is not None else DEFAULT_STRATEGY_ID
    else:
        out = _normalize_wide_weights(weights, output_col=output_col)
        if keep_strategy:
            out[STRATEGY_COL] = strategy_id if strategy_id is not None else DEFAULT_STRATEGY_ID

    out[DATE_COL] = pd.to_datetime(out[DATE_COL])
    out[output_col] = pd.to_numeric(out[output_col], errors="coerce")
    group_cols = [DATE_COL, SYMBOL_COL]
    if keep_strategy:
        group_cols.insert(1, STRATEGY_COL)
    return (
        out[group_cols + [output_col]]
        .dropna(subset=[output_col])
        .groupby(group_cols, as_index=False)[output_col]
        .sum()
    )


def _normalize_wide_weights(weights: pd.DataFrame, *, output_col: str) -> pd.DataFrame:
    reset = weights.copy().reset_index()
    date_col = _detect_date_column(reset)
    excluded = {date_col, STRATEGY_COL}
    if (
        date_col != "index"
        and "index" in reset.columns
        and isinstance(weights.index, pd.RangeIndex)
        and weights.index.name is None
    ):
        excluded.add("index")
    value_cols = [col for col in reset.columns if col not in excluded]
    if not value_cols:
        raise ValueError("weights does not contain symbol weight columns")
    out = reset.melt(
        id_vars=[date_col], value_vars=value_cols, var_name=SYMBOL_COL, value_name=output_col
    )
    return out.rename(columns={date_col: DATE_COL})


def _detect_date_column(reset_frame: pd.DataFrame) -> str:
    if DATE_COL in reset_frame.columns:
        return DATE_COL
    if "eob" in reset_frame.columns:
        return "eob"
    if "index" in reset_frame.columns:
        return "index"
    return reset_frame.columns[0]


def _slice_strategy_weights(
    weights: pd.DataFrame,
    date: Any,
    strategy_id: Any,
    weight_col: str,
) -> pd.DataFrame:
    current = weights.loc[
        (weights[DATE_COL] == date) & (weights[STRATEGY_COL] == strategy_id),
        [SYMBOL_COL, weight_col],
    ].copy()
    return current.groupby(SYMBOL_COL, as_index=False)[weight_col].sum()


def _slice_benchmark_weights(benchmark: pd.DataFrame, date: Any) -> pd.DataFrame:
    current = benchmark.loc[benchmark[DATE_COL] == date, [SYMBOL_COL, "benchmark_weight"]].copy()
    return current.groupby(SYMBOL_COL, as_index=False)["benchmark_weight"].sum()


def _equal_weight_benchmark(group: pd.DataFrame) -> pd.DataFrame:
    symbols = group[SYMBOL_COL].drop_duplicates().sort_values()
    if symbols.empty:
        return pd.DataFrame(columns=[SYMBOL_COL, "benchmark_weight"])
    return pd.DataFrame({SYMBOL_COL: symbols.to_numpy(), "benchmark_weight": 1.0 / len(symbols)})


def _resolve_factor_cols(factors: pd.DataFrame, factor_cols: Sequence[str] | None) -> list[str]:
    if factor_cols is not None:
        missing = [col for col in factor_cols if col not in factors.columns]
        if missing:
            raise ValueError(f"factor_snapshot is missing factor columns: {', '.join(missing)}")
        return list(factor_cols)
    candidates = [
        col
        for col in factors.columns
        if col not in RESERVED_FACTOR_COLUMNS and pd.api.types.is_numeric_dtype(factors[col])
    ]
    if not candidates:
        raise ValueError("factor_snapshot does not contain numeric factor columns.")
    return candidates


def _resolve_control_cols(
    factors: pd.DataFrame,
    control_cols: Sequence[str] | None,
    include_controls: bool,
) -> list[str]:
    if not include_controls:
        return []
    if control_cols is not None:
        return [col for col in control_cols if col in factors.columns]
    return [col for col in ("age_days", "valid_factor_count") if col in factors.columns]


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


def _require_dataframe(value: Any, name: str) -> None:
    if not isinstance(value, pd.DataFrame):
        raise ValueError(f"{name} must be a pandas DataFrame")


def _require_columns(df: pd.DataFrame, required_cols: Sequence[str], df_name: str) -> None:
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"{df_name} is missing required columns: {', '.join(missing)}")


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            DATE_COL,
            STRATEGY_COL,
            "term",
            "term_type",
            "beta",
            "active_exposure",
            "contribution",
            "status",
            "skip_reason",
            "n_obs",
            "n_terms",
            "portfolio_return",
            "benchmark_return",
            "active_return",
            "portfolio_total_weight",
            "benchmark_total_weight",
            "daily_active_return",
            "daily_attribution_total",
            "reconcile_residual",
        ]
    )
