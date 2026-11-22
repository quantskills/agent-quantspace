"""Model ids, preprocessing pipelines, and cross-validation metric tables.

The scikit-learn / XGBoost building blocks behind ``MLEngine`` and ``MLFactorEngine``.
Model ids and their default constructor arguments, the preprocessing order (mean
imputation, scaling, optional PCA) and the metric table layout (folds ``0..k-1`` then
``Mean`` and ``Std``, four decimals) follow PyCaret 3.3, which QuantSpace used before,
so cross-validation metrics stay comparable. scikit-learn and XGBoost are imported
lazily, when a model is built.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Literal

import numpy as np
import pandas as pd

Task = Literal["classification", "regression"]

CLASSIFICATION_MODELS = (
    "lr", "ridge", "knn", "nb", "dt", "rf", "et", "gbc", "ada", "lda", "qda", "dummy", "xgboost",
)  # fmt: skip
REGRESSION_MODELS = (
    "lr", "lasso", "ridge", "en", "br", "huber", "knn", "dt", "rf", "et", "gbr", "ada", "dummy",
    "xgboost",
)  # fmt: skip
MODEL_IDS: dict[str, tuple[str, ...]] = {
    "classification": CLASSIFICATION_MODELS,
    "regression": REGRESSION_MODELS,
}
NORMALIZE_METHODS = ("zscore", "minmax", "maxabs", "robust", "none")
CLASSIFICATION_METRICS = ("Accuracy", "AUC", "Recall", "Prec.", "F1", "Kappa", "MCC")
REGRESSION_METRICS = ("MAE", "MSE", "RMSE", "R2", "RMSLE", "MAPE")
METRIC_DECIMALS = 4
LABEL_COLUMN = "prediction_label"
SCORE_COLUMN = "prediction_score"

_XGBOOST = {"verbosity": 0, "booster": "gbtree", "tree_method": "hist"}
# id -> (module, class, takes random_state, takes n_jobs, fixed arguments)
_SPECS: dict[str, dict[str, tuple[str, str, bool, bool, dict[str, Any]]]] = {
    "classification": {
        "lr": ("sklearn.linear_model", "LogisticRegression", True, False, {"max_iter": 1000}),
        "ridge": ("sklearn.linear_model", "RidgeClassifier", True, False, {}),
        "knn": ("sklearn.neighbors", "KNeighborsClassifier", False, True, {}),
        "nb": ("sklearn.naive_bayes", "GaussianNB", False, False, {}),
        "dt": ("sklearn.tree", "DecisionTreeClassifier", True, False, {}),
        "rf": ("sklearn.ensemble", "RandomForestClassifier", True, True, {}),
        "et": ("sklearn.ensemble", "ExtraTreesClassifier", True, True, {}),
        "gbc": ("sklearn.ensemble", "GradientBoostingClassifier", True, False, {}),
        "ada": ("sklearn.ensemble", "AdaBoostClassifier", True, False, {}),
        "lda": ("sklearn.discriminant_analysis", "LinearDiscriminantAnalysis", False, False, {}),
        "qda": ("sklearn.discriminant_analysis", "QuadraticDiscriminantAnalysis", False, False, {}),
        "dummy": ("sklearn.dummy", "DummyClassifier", True, False, {"strategy": "prior"}),
        "xgboost": ("xgboost", "XGBClassifier", True, True, _XGBOOST),
    },
    "regression": {
        "lr": ("sklearn.linear_model", "LinearRegression", False, True, {}),
        "lasso": ("sklearn.linear_model", "Lasso", True, False, {}),
        "ridge": ("sklearn.linear_model", "Ridge", True, False, {}),
        "en": ("sklearn.linear_model", "ElasticNet", True, False, {}),
        "br": ("sklearn.linear_model", "BayesianRidge", False, False, {}),
        "huber": ("sklearn.linear_model", "HuberRegressor", False, False, {}),
        "knn": ("sklearn.neighbors", "KNeighborsRegressor", False, True, {}),
        "dt": ("sklearn.tree", "DecisionTreeRegressor", True, False, {}),
        "rf": ("sklearn.ensemble", "RandomForestRegressor", True, True, {}),
        "et": ("sklearn.ensemble", "ExtraTreesRegressor", True, True, {}),
        "gbr": ("sklearn.ensemble", "GradientBoostingRegressor", True, False, {}),
        "ada": ("sklearn.ensemble", "AdaBoostRegressor", True, False, {}),
        "dummy": ("sklearn.dummy", "DummyRegressor", False, False, {"strategy": "mean"}),
        "xgboost": ("xgboost", "XGBRegressor", True, True, _XGBOOST),
    },
}


def check_task(task: str) -> str:
    if task not in MODEL_IDS:
        raise ValueError(f"Unknown task: {task!r}. Use 'classification' or 'regression'.")
    return task


def check_model(task: str, model: str) -> str:
    """Return ``model`` if it is a supported id for ``task``; otherwise raise ``ValueError``."""
    if model not in MODEL_IDS[check_task(task)]:
        raise ValueError(
            f"Unknown {task} model {model!r}. Supported: {', '.join(MODEL_IDS[task])}."
        )
    return model


def check_normalize(method: str) -> str:
    if method not in NORMALIZE_METHODS:
        raise ValueError(
            f"Unknown normalize method {method!r}. Supported: {', '.join(NORMALIZE_METHODS)}."
        )
    return method


def make_estimator(
    task: str,
    model: str,
    *,
    random_state: int | None = None,
    n_jobs: int | None = 1,
    params: dict[str, Any] | None = None,
):
    """Build an unfitted estimator with PyCaret's defaults for ``model``, then ``params``.

    ``random_state`` and ``n_jobs`` go to the estimators that accept them; ``params`` are
    constructor arguments that override the defaults. Unknown ids or parameter names
    raise ``ValueError``.
    """
    module, name, seeded, parallel, fixed = _SPECS[task][check_model(task, model)]
    cls = getattr(import_module(module), name)
    params = dict(params or {})
    valid = set(cls().get_params())
    unknown = sorted(set(params) - valid)
    if unknown:
        raise ValueError(
            f"Unknown parameters for {task} model {model!r}: {unknown}. "
            f"Valid parameters: {', '.join(sorted(valid))}."
        )
    kwargs = dict(fixed)
    if seeded:
        kwargs["random_state"] = random_state
    if parallel:
        kwargs["n_jobs"] = n_jobs
    kwargs.update(params)
    return cls(**kwargs)


def make_pipeline(
    estimator,
    *,
    normalize: str = "zscore",
    pca_components: int | None = None,
    random_state: int | None = None,
):
    """Mean imputation, then scaling (unless ``normalize='none'``), optional PCA, estimator."""
    from sklearn.decomposition import PCA
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import MaxAbsScaler, MinMaxScaler, RobustScaler, StandardScaler

    scalers = {
        "zscore": StandardScaler,
        "minmax": MinMaxScaler,
        "maxabs": MaxAbsScaler,
        "robust": RobustScaler,
    }
    steps = [("imputer", SimpleImputer(strategy="mean"))]
    if check_normalize(normalize) != "none":
        steps.append(("scaler", scalers[normalize]()))
    if pca_components is not None:
        steps.append(("pca", PCA(n_components=pca_components, random_state=random_state)))
    steps.append(("model", estimator))
    return Pipeline(steps)


def feature_matrix(data: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """The numeric feature columns of ``data``; missing or non-numeric columns raise."""
    missing = [column for column in features if column not in data.columns]
    if missing:
        raise ValueError(f"data is missing feature columns: {missing}")
    X = data[features]
    text = [
        column
        for column in features
        if not (pd.api.types.is_numeric_dtype(X[column]) or pd.api.types.is_bool_dtype(X[column]))
    ]
    if text:
        raise ValueError(f"feature columns must be numeric: {text}")
    return X


def encode_labels(y) -> tuple[np.ndarray, np.ndarray]:
    """Encode class labels to ``0..k-1``; returns ``(encoded, classes)``."""
    from sklearn.preprocessing import LabelEncoder

    encoder = LabelEncoder().fit(y)
    return encoder.transform(y), encoder.classes_


def _scores(model, X):
    """(class probabilities or None, decision values or None)."""
    proba = model.predict_proba(X) if hasattr(model, "predict_proba") else None
    decision = model.decision_function(X) if hasattr(model, "decision_function") else None
    return proba, decision


def classification_scores(model, X, y, n_classes: int) -> dict[str, float]:
    """PyCaret's classification metrics on encoded labels ``y`` in ``0..n_classes-1``.

    Two classes use binary averaging with the larger label as the positive class;
    more classes use weighted averaging and one-vs-rest AUC on the probabilities.
    AUC is NaN when it is undefined (one class in ``y``, or no probabilities).
    """
    from sklearn import metrics

    y = np.asarray(y)
    pred = model.predict(X)
    proba, decision = _scores(model, X)
    if n_classes == 2:
        average = {"average": "binary", "pos_label": 1}
        score = decision if decision is not None else None
        if score is None and proba is not None:
            score = proba[:, 1]
        auc_args = {}
    else:
        average = {"average": "weighted"}
        score = proba
        auc_args = {"multi_class": "ovr", "average": "weighted", "labels": np.arange(n_classes)}
    try:
        auc = np.nan if score is None else metrics.roc_auc_score(y, score, **auc_args)
    except ValueError:
        auc = np.nan
    return {
        "Accuracy": metrics.accuracy_score(y, pred),
        "AUC": auc,
        "Recall": metrics.recall_score(y, pred, zero_division=0, **average),
        "Prec.": metrics.precision_score(y, pred, zero_division=0, **average),
        "F1": metrics.f1_score(y, pred, zero_division=0, **average),
        "Kappa": metrics.cohen_kappa_score(y, pred),
        "MCC": metrics.matthews_corrcoef(y, pred),
    }


def regression_scores(y, pred) -> dict[str, float]:
    """PyCaret's regression metrics: RMSLE on absolute values, MAPE over nonzero targets."""
    from sklearn import metrics

    y = np.asarray(y, dtype=np.float64)
    pred = np.asarray(pred, dtype=np.float64)
    mse = metrics.mean_squared_error(y, pred)
    nonzero = y != 0
    return {
        "MAE": metrics.mean_absolute_error(y, pred),
        "MSE": mse,
        "RMSE": float(np.sqrt(mse)),
        "R2": metrics.r2_score(y, pred),
        "RMSLE": float(np.sqrt(metrics.mean_squared_log_error(np.abs(y), np.abs(pred)))),
        "MAPE": float(np.mean(np.abs(pred[nonzero] - y[nonzero]) / np.abs(y[nonzero])))
        if nonzero.any()
        else np.nan,
    }


def score(task: str, model, X, y, n_classes: int | None = None) -> dict[str, float]:
    if task == "classification":
        return classification_scores(model, X, y, n_classes or len(np.unique(y)))
    return regression_scores(y, model.predict(X))


def metric_table(rows: list[dict[str, float]], task: str) -> pd.DataFrame:
    """Per-fold rows, then ``Mean`` and ``Std`` (population), rounded like PyCaret's ``pull()``."""
    columns = CLASSIFICATION_METRICS if task == "classification" else REGRESSION_METRICS
    folds = pd.DataFrame(rows, columns=list(columns), dtype=np.float64)
    summary = pd.DataFrame([folds.mean(), folds.std(ddof=0)], columns=folds.columns)
    table = pd.concat([folds, summary], ignore_index=True)
    table.index = pd.Index([str(i) for i in range(len(folds))] + ["Mean", "Std"], name="Fold")
    return table.round(METRIC_DECIMALS)


def cross_validation_table(pipeline, X: pd.DataFrame, y, *, task: str, cv) -> pd.DataFrame:
    """Fit a clone of ``pipeline`` on each training fold of ``cv`` and score its test fold."""
    from sklearn.base import clone

    y = np.asarray(y)
    n_classes = len(np.unique(y)) if task == "classification" else None
    rows = []
    for train_idx, test_idx in cv.split(X, y):
        model = clone(pipeline).fit(X.iloc[train_idx], y[train_idx])
        rows.append(score(task, model, X.iloc[test_idx], y[test_idx], n_classes))
    return metric_table(rows, task)


class TrainedModel:
    """A fitted preprocessing + estimator pipeline with its feature list and class labels.

    This is what ``MLEngine`` pickles into the model registry. ``predict`` returns the
    input rows plus ``prediction_label`` (original class labels for classifiers) and, for
    classifiers with probabilities, ``prediction_score``: the probability of the predicted
    class, rounded to four decimals.
    """

    def __init__(self, task: str, pipeline, features: list[str], classes=None):
        self.task = check_task(task)
        self.pipeline = pipeline
        self.features = list(features)
        self.classes = None if classes is None else np.asarray(classes)

    @property
    def estimator(self):
        return self.pipeline[-1]

    def predict(self, data: pd.DataFrame) -> pd.DataFrame:
        X = feature_matrix(data, self.features)
        result = data.copy()
        pred = self.pipeline.predict(X)
        if self.task == "regression":
            result[LABEL_COLUMN] = pred
            return result
        pred = np.asarray(pred).astype(int)
        result[LABEL_COLUMN] = self.classes[pred]
        if hasattr(self.pipeline, "predict_proba"):
            proba = self.pipeline.predict_proba(X)
            score = proba[np.arange(len(pred)), pred]
            result[SCORE_COLUMN] = np.round(score, METRIC_DECIMALS)
        return result


__all__ = [
    "CLASSIFICATION_METRICS",
    "CLASSIFICATION_MODELS",
    "LABEL_COLUMN",
    "MODEL_IDS",
    "NORMALIZE_METHODS",
    "REGRESSION_METRICS",
    "REGRESSION_MODELS",
    "SCORE_COLUMN",
    "TrainedModel",
    "check_model",
    "check_normalize",
    "check_task",
    "cross_validation_table",
    "encode_labels",
    "feature_matrix",
    "make_estimator",
    "make_pipeline",
    "metric_table",
    "regression_scores",
    "score",
]
