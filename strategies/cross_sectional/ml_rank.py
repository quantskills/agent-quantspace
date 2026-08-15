"""Cross-sectional ML rank helpers: LogDiff features, PCA folds, and model scores."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error, r2_score

from skills.backtest.weighting import risk_parity
from skills.compute.features import make_logdiff_panel_features
from skills.ml.pca_fold import ModelKind, SUPPORTED_MODELS, fit_fold_transform, make_regressor
from skills.ml.walk_forward import date_level_mask, expanding_purged_folds
from skills.strategy.cross_sectional import top_n_weights

# ~5 Expanding folds on the 18ETF daily sample (was 126 ≈ 15 folds).
DEFAULT_RETRAIN_STEP = 370


@dataclass(frozen=True, slots=True)
class ExpandingPCAModelResult:
    """Out-of-sample scores and regression diagnostics from expanding PCA folds."""

    scores: pd.Series
    fold_metrics: pd.DataFrame
    overall_metrics: dict[str, float]


def cross_sectional_rank_labels(panel: pd.DataFrame, horizon: int = 20) -> pd.Series:
    """Percentile rank of each symbol's forward return within each date.

    Forward return is ``close.shift(-horizon) / close - 1``. Rows without a full
    ``horizon`` of future prices are dropped because the label is undefined.
    """
    if horizon < 1:
        raise ValueError("horizon must be positive.")
    close = panel["close"].unstack(level="symbol").sort_index()
    forward_return = close.shift(-horizon).div(close).sub(1.0)
    rank_label = forward_return.rank(axis=1, pct=True).stack(future_stack=True).rename("rank_label")
    rank_label.index.names = ["eob", "symbol"]
    rank_label = rank_label.reorder_levels(["symbol", "eob"]).sort_index()
    return rank_label.dropna()


WeightingMethod = Literal["equal", "risk_parity"]


def rank_scores_to_weights(
    score_df: pd.DataFrame,
    close: pd.DataFrame,
    top_n: int = 2,
    vol_lookback: int = 60,
    weighting: WeightingMethod = "equal",
) -> pd.DataFrame:
    """Convert predicted rank scores into top-N portfolio weights."""
    if top_n < 1:
        raise ValueError("top_n must be positive.")
    if weighting == "equal":
        return top_n_weights(score_df, top_n=top_n)
    if weighting != "risk_parity":
        raise ValueError(f"unsupported weighting: {weighting!r}")
    votes = top_n_weights(score_df, top_n=top_n).gt(0.0).astype(float)
    returns = close.reindex(columns=score_df.columns).pct_change(fill_method=None)
    return risk_parity(
        votes,
        returns_df=returns,
        lookback=vol_lookback,
        min_periods=vol_lookback,
    ).fillna(0.0)


def _regression_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float]:
    aligned = pd.concat([y_true.rename("y_true"), y_pred.rename("y_pred")], axis=1).dropna()
    if aligned.empty:
        return {"mse": np.nan, "rmse": np.nan, "r2": np.nan}
    mse = float(mean_squared_error(aligned["y_true"], aligned["y_pred"]))
    return {
        "mse": mse,
        "rmse": float(np.sqrt(mse)),
        "r2": float(r2_score(aligned["y_true"], aligned["y_pred"])),
    }


def _mean_rank_ic(scores: pd.Series, labels: pd.Series) -> float:
    combined = pd.concat([scores.rename("score"), labels.rename("rank_label")], axis=1).dropna()
    if combined.empty:
        return np.nan

    def _daily_ic(group: pd.DataFrame) -> float:
        if len(group) < 2:
            return np.nan
        return float(group["score"].corr(group["rank_label"], method="spearman"))

    daily_ic = combined.groupby(level="eob", group_keys=False).apply(_daily_ic)
    return float(daily_ic.mean()) if not daily_ic.empty else np.nan


def _lasso_nnz_coef(estimator: Any) -> float | None:
    coef = getattr(estimator, "coef_", None)
    if coef is None:
        return None
    return float(np.count_nonzero(coef))


def _finalize_model_result(
    *,
    model: ModelKind,
    score_parts: list[pd.Series],
    fold_rows: list[dict[str, float | int | None]],
    labels: pd.Series,
) -> ExpandingPCAModelResult:
    if not score_parts:
        raise ValueError("expanding PCA model requires non-empty train and predict datasets.")
    scores = pd.concat(score_parts).sort_index()
    fold_metrics = pd.DataFrame(fold_rows)
    overall = _regression_metrics(labels.reindex(scores.index), scores)
    overall["rank_ic"] = _mean_rank_ic(scores, labels)
    overall["pca_explained_variance_sum"] = (
        float(fold_metrics["pca_explained_variance_sum"].mean())
        if not fold_metrics.empty
        else np.nan
    )
    if model == "lasso" and "lasso_nnz_coef" in fold_metrics.columns:
        overall["lasso_nnz_coef"] = float(fold_metrics["lasso_nnz_coef"].mean())
    return ExpandingPCAModelResult(
        scores=scores,
        fold_metrics=fold_metrics,
        overall_metrics=overall,
    )


def expanding_pca_multi_model_scores(
    panel: pd.DataFrame,
    *,
    models: Sequence[ModelKind] = ("ols", "lasso", "rf", "xgboost"),
    horizon: int = 20,
    min_train: int = 250,
    retrain_step: int = DEFAULT_RETRAIN_STEP,
    n_pca: int = 50,
    random_state: int = 42,
    features: pd.DataFrame | None = None,
    rf_n_jobs: int | None = None,
) -> dict[str, ExpandingPCAModelResult]:
    """Walk-forward scores for several models that share each fold's train-only PCA."""
    model_list = tuple(models)
    if not model_list:
        raise ValueError("models cannot be empty.")
    for model in model_list:
        if model not in SUPPORTED_MODELS:
            raise ValueError(f"unsupported model: {model!r}")

    if features is None:
        features = make_logdiff_panel_features(panel)
    labels = cross_sectional_rank_labels(panel, horizon=horizon)

    label_values = labels.reindex(features.index).to_numpy(dtype=float)
    labeled = ~np.isnan(label_values)
    row_dates = pd.DatetimeIndex(features.index.get_level_values("eob"))
    folds = expanding_purged_folds(
        row_dates[labeled].unique().sort_values(),
        min_train=min_train,
        retrain_step=retrain_step,
        purge=horizon,
    )
    if not folds:
        raise ValueError("expanding_pca_multi_model_scores requires at least one expanding fold.")

    feature_values = features.to_numpy(dtype=float)
    score_parts: dict[str, list[pd.Series]] = {model: [] for model in model_list}
    fold_rows: dict[str, list[dict[str, float | int | None]]] = {model: [] for model in model_list}

    for fold in folds:
        train_mask = labeled & date_level_mask(features.index, fold.train_dates)
        pred_mask = date_level_mask(features.index, fold.pred_dates)
        if not train_mask.any() or not pred_mask.any():
            continue

        transform = fit_fold_transform(
            feature_values[train_mask],
            feature_values[pred_mask],
            n_pca=n_pca,
            random_state=random_state,
        )
        train_y = label_values[train_mask]
        pred_index = features.index[pred_mask]

        for model in model_list:
            estimator = make_regressor(model, random_state=random_state, rf_n_jobs=rf_n_jobs)
            estimator.fit(transform.train_X, train_y)
            pred_scores = pd.Series(
                estimator.predict(transform.pred_X),
                index=pred_index,
                name="score",
            )
            score_parts[model].append(pred_scores)
            pred_labels = labels.reindex(pred_scores.index)
            metrics = _regression_metrics(pred_labels, pred_scores)
            fold_rows[model].append(
                {
                    "fold_id": fold.fold_id,
                    "n_train": int(train_mask.sum()),
                    "n_pred": len(pred_scores),
                    "pca_explained_variance_sum": transform.pca_explained_variance_sum,
                    "mse": metrics["mse"],
                    "rmse": metrics["rmse"],
                    "r2": metrics["r2"],
                    "rank_ic": _mean_rank_ic(pred_scores, pred_labels),
                    "lasso_nnz_coef": _lasso_nnz_coef(estimator),
                }
            )

    return {
        model: _finalize_model_result(
            model=model,
            score_parts=score_parts[model],
            fold_rows=fold_rows[model],
            labels=labels,
        )
        for model in model_list
    }


def expanding_pca_model_scores(
    panel: pd.DataFrame,
    *,
    model: ModelKind = "xgboost",
    horizon: int = 20,
    min_train: int = 250,
    retrain_step: int = DEFAULT_RETRAIN_STEP,
    n_pca: int = 50,
    random_state: int = 42,
    features: pd.DataFrame | None = None,
    rf_n_jobs: int | None = None,
) -> ExpandingPCAModelResult:
    """Train expanding walk-forward models on PCA-reduced LogDiff features.

    Pass ``features`` from :func:`skills.compute.features.make_logdiff_panel_features`
    to reuse one already-cleaned LogDiff panel across horizons and models.

    For several models on the same horizon, prefer
    :func:`expanding_pca_multi_model_scores` so each fold's PCA is fit once.
    """
    return expanding_pca_multi_model_scores(
        panel,
        models=(model,),
        horizon=horizon,
        min_train=min_train,
        retrain_step=retrain_step,
        n_pca=n_pca,
        random_state=random_state,
        features=features,
        rf_n_jobs=rf_n_jobs,
    )[model]


def expanding_pca_model_weights(
    panel: pd.DataFrame,
    *,
    model: ModelKind = "xgboost",
    horizon: int = 20,
    min_train: int = 250,
    retrain_step: int = DEFAULT_RETRAIN_STEP,
    n_pca: int = 50,
    top_n: int = 2,
    vol_lookback: int = 60,
    weighting: WeightingMethod = "equal",
    random_state: int = 42,
    features: pd.DataFrame | None = None,
    rf_n_jobs: int | None = None,
) -> pd.DataFrame:
    """Convert expanding PCA model scores into top-N portfolio weights."""
    result = expanding_pca_model_scores(
        panel,
        model=model,
        horizon=horizon,
        min_train=min_train,
        retrain_step=retrain_step,
        n_pca=n_pca,
        random_state=random_state,
        features=features,
        rf_n_jobs=rf_n_jobs,
    )
    score_df = result.scores.unstack(level="symbol")
    close = panel["close"].unstack(level="symbol").sort_index()
    return rank_scores_to_weights(
        score_df,
        close,
        top_n=top_n,
        vol_lookback=vol_lookback,
        weighting=weighting,
    )


__all__ = [
    "DEFAULT_RETRAIN_STEP",
    "ExpandingPCAModelResult",
    "cross_sectional_rank_labels",
    "expanding_pca_model_scores",
    "expanding_pca_model_weights",
    "expanding_pca_multi_model_scores",
    "rank_scores_to_weights",
    "WeightingMethod",
]
