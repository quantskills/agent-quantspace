"""Train-only PCA transforms and regressor factories."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Lasso
from xgboost import XGBRegressor

ModelKind = Literal["lasso", "rf", "xgboost"]


@dataclass(frozen=True, slots=True)
class FoldTransformResult:
    """PCA-transformed train / predict matrices for one fold."""

    train_X: np.ndarray
    pred_X: np.ndarray
    pca_explained_variance_sum: float


def fit_fold_transform(
    train_X: np.ndarray,
    pred_X: np.ndarray,
    *,
    n_pca: int = 50,
    random_state: int = 42,
) -> FoldTransformResult:
    """Fit PCA on train only, then transform train and predict.

    LogDiff features are already on a comparable scale, so no StandardScaler is
    applied. ``sklearn.decomposition.PCA`` still mean-centers columns.
    """
    if train_X.ndim != 2 or pred_X.ndim != 2:
        raise ValueError("train_X and pred_X must be 2-D arrays.")
    if train_X.shape[1] != pred_X.shape[1]:
        raise ValueError("train_X and pred_X must share the same feature dimension.")

    n_components = min(n_pca, train_X.shape[0], train_X.shape[1])
    if n_components < 1:
        raise ValueError("train_X must contain at least one row and one feature.")

    pca = PCA(n_components=n_components, random_state=random_state)
    train_pca = pca.fit_transform(train_X)
    pred_pca = pca.transform(pred_X)

    return FoldTransformResult(
        train_X=train_pca,
        pred_X=pred_pca,
        pca_explained_variance_sum=float(pca.explained_variance_ratio_.sum()),
    )


def default_rf_n_jobs() -> int:
    """Use multiple cores for RF when not oversubscribed by outer process pools."""
    cpu = os.cpu_count() or 1
    return max(1, cpu)


def make_regressor(
    model: ModelKind,
    *,
    random_state: int = 42,
    rf_n_jobs: int | None = None,
) -> Any:
    """Build a frozen-default regressor for lesson-07 cross-sectional ML."""
    if model == "lasso":
        return Lasso(alpha=1e-3, random_state=random_state)
    if model == "rf":
        return RandomForestRegressor(
            n_estimators=200,
            max_depth=6,
            min_samples_leaf=5,
            n_jobs=default_rf_n_jobs() if rf_n_jobs is None else int(rf_n_jobs),
            random_state=random_state,
        )
    if model == "xgboost":
        return XGBRegressor(
            n_estimators=80,
            max_depth=2,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="reg:squarederror",
            n_jobs=1,
            random_state=random_state,
        )
    raise ValueError(f"unsupported model: {model!r}")


__all__ = [
    "FoldTransformResult",
    "ModelKind",
    "default_rf_n_jobs",
    "fit_fold_transform",
    "make_regressor",
]
