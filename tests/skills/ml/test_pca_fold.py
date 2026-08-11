from __future__ import annotations

import numpy as np
import pytest
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from skills.ml.pca_fold import fit_fold_transform, make_regressor


def test_fit_fold_transform_does_not_fit_pca_on_pred(monkeypatch) -> None:
    train_X = np.arange(12, dtype=float).reshape(4, 3)
    pred_X = np.arange(6, dtype=float).reshape(2, 3)
    fit_calls: list[np.ndarray] = []

    class TrackingPCA(PCA):
        def fit_transform(self, X, y=None):  # noqa: N803
            fit_calls.append(np.asarray(X))
            return super().fit_transform(X, y)

    monkeypatch.setattr("skills.ml.pca_fold.PCA", TrackingPCA)

    result = fit_fold_transform(train_X, pred_X, n_pca=2, random_state=42)

    assert len(fit_calls) == 1
    assert fit_calls[0].shape == train_X.shape
    assert result.train_X.shape == (4, 2)
    assert result.pred_X.shape == (2, 2)
    assert 0.0 < result.pca_explained_variance_sum <= 1.0


def test_fit_fold_transform_does_not_use_standard_scaler(monkeypatch) -> None:
    train_X = np.arange(12, dtype=float).reshape(4, 3)
    pred_X = np.arange(6, dtype=float).reshape(2, 3)

    def boom(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("StandardScaler must not be used for LogDiff PCA folds")

    monkeypatch.setattr(StandardScaler, "fit", boom)
    monkeypatch.setattr(StandardScaler, "fit_transform", boom)

    result = fit_fold_transform(train_X, pred_X, n_pca=2, random_state=42)
    assert result.train_X.shape[1] == 2


def test_make_regressor_builds_frozen_defaults() -> None:
    lasso = make_regressor("lasso", random_state=7)
    rf = make_regressor("rf", random_state=7, rf_n_jobs=4)
    xgb = make_regressor("xgboost", random_state=7)

    assert lasso.alpha == pytest.approx(1e-3)
    assert rf.n_estimators == 200
    assert rf.max_depth == 6
    assert rf.min_samples_leaf == 5
    assert rf.n_jobs == 4
    assert xgb.n_estimators == 80
    assert xgb.max_depth == 2
    assert xgb.learning_rate == pytest.approx(0.05)


def test_make_regressor_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="unsupported model"):
        make_regressor("lightgbm")  # type: ignore[arg-type]
