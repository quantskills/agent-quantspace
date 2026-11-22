from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from skills.ml.estimators import (
    CLASSIFICATION_METRICS,
    MODEL_IDS,
    REGRESSION_METRICS,
    TrainedModel,
    cross_validation_table,
    encode_labels,
    feature_matrix,
    make_estimator,
    make_pipeline,
    metric_table,
)

# Constructor arguments PyCaret 3.3.2 used for each id (session_id=369, n_jobs=1). PyCaret
# passed tree_method="auto", device="cpu" to XGBoost; on XGBoost >= 2 "auto" is "hist".
PYCARET_ARGS = {
    ("classification", "lr"): ("LogisticRegression", {"max_iter": 1000, "random_state": 369}),
    ("classification", "ridge"): ("RidgeClassifier", {"random_state": 369}),
    ("classification", "knn"): ("KNeighborsClassifier", {"n_jobs": 1}),
    ("classification", "nb"): ("GaussianNB", {}),
    ("classification", "dt"): ("DecisionTreeClassifier", {"random_state": 369}),
    ("classification", "rf"): ("RandomForestClassifier", {"random_state": 369, "n_jobs": 1}),
    ("classification", "et"): ("ExtraTreesClassifier", {"random_state": 369, "n_jobs": 1}),
    ("classification", "gbc"): ("GradientBoostingClassifier", {"random_state": 369}),
    ("classification", "ada"): ("AdaBoostClassifier", {"random_state": 369}),
    ("classification", "lda"): ("LinearDiscriminantAnalysis", {}),
    ("classification", "qda"): ("QuadraticDiscriminantAnalysis", {}),
    ("classification", "dummy"): ("DummyClassifier", {"strategy": "prior", "random_state": 369}),
    ("classification", "xgboost"): (
        "XGBClassifier",
        {"random_state": 369, "n_jobs": 1, "verbosity": 0, "booster": "gbtree"},
    ),
    ("regression", "lr"): ("LinearRegression", {"n_jobs": 1}),
    ("regression", "lasso"): ("Lasso", {"random_state": 369}),
    ("regression", "ridge"): ("Ridge", {"random_state": 369}),
    ("regression", "en"): ("ElasticNet", {"random_state": 369}),
    ("regression", "br"): ("BayesianRidge", {}),
    ("regression", "huber"): ("HuberRegressor", {}),
    ("regression", "knn"): ("KNeighborsRegressor", {"n_jobs": 1}),
    ("regression", "dt"): ("DecisionTreeRegressor", {"random_state": 369}),
    ("regression", "rf"): ("RandomForestRegressor", {"random_state": 369, "n_jobs": 1}),
    ("regression", "et"): ("ExtraTreesRegressor", {"random_state": 369, "n_jobs": 1}),
    ("regression", "gbr"): ("GradientBoostingRegressor", {"random_state": 369}),
    ("regression", "ada"): ("AdaBoostRegressor", {"random_state": 369}),
    ("regression", "dummy"): ("DummyRegressor", {"strategy": "mean"}),
    ("regression", "xgboost"): (
        "XGBRegressor",
        {"random_state": 369, "n_jobs": 1, "verbosity": 0, "booster": "gbtree"},
    ),
}
CASES = [(task, model) for task, models in MODEL_IDS.items() for model in models]


def test_the_whitelist_is_exactly_the_pinned_pycaret_models() -> None:
    assert set(CASES) == set(PYCARET_ARGS)


@pytest.mark.parametrize(("task", "model"), CASES)
def test_defaults_match_pycaret_and_every_model_fits(task, model) -> None:
    name, expected = PYCARET_ARGS[(task, model)]
    estimator = make_estimator(task, model, random_state=369, n_jobs=1)
    assert type(estimator).__name__ == name
    params = estimator.get_params()
    assert {key: params[key] for key in expected} == expected

    rng = np.random.default_rng(1)
    X = pd.DataFrame(rng.normal(size=(60, 3)), columns=["a", "b", "c"])
    raw = X["a"] + 0.5 * rng.normal(size=60)
    y = np.digitize(raw, [-0.5, 0.5]) if task == "classification" else raw.to_numpy()
    from sklearn.model_selection import KFold

    table = cross_validation_table(make_pipeline(estimator), X, y, task=task, cv=KFold(3))
    columns = CLASSIFICATION_METRICS if task == "classification" else REGRESSION_METRICS
    assert list(table.columns) == list(columns)
    assert list(table.index) == ["0", "1", "2", "Mean", "Std"]


def test_model_params_override_defaults_and_unknown_names_fail() -> None:
    estimator = make_estimator("regression", "rf", random_state=1, params={"n_estimators": 7})
    assert (estimator.n_estimators, estimator.random_state) == (7, 1)
    with pytest.raises(
        ValueError, match=r"Unknown parameters for regression model 'rf': \['depth'\]"
    ):
        make_estimator("regression", "rf", params={"depth": 3})
    with pytest.raises(ValueError, match="Unknown classification model 'lightgbm'"):
        make_estimator("classification", "lightgbm")


def test_pipeline_steps_follow_normalize_and_pca() -> None:
    estimator = make_estimator("regression", "lr")
    steps = lambda **kw: [name for name, _ in make_pipeline(estimator, **kw).steps]  # noqa: E731
    assert steps() == ["imputer", "scaler", "model"]
    assert steps(normalize="none", pca_components=2) == ["imputer", "pca", "model"]
    scaler = make_pipeline(estimator, normalize="robust").named_steps["scaler"]
    assert type(scaler).__name__ == "RobustScaler"
    with pytest.raises(ValueError, match="normalize method"):
        make_pipeline(estimator, normalize="zscored")


def test_metric_table_rounds_after_mean_and_population_std() -> None:
    # Rounded folds average to 0.12343; the raw folds average to 0.12346.
    rows = [
        {"MAE": 0.12344, "MSE": 1.0},
        {"MAE": 0.12344, "MSE": 1.0},
        {"MAE": 0.12349, "MSE": 4.0},
    ]
    table = metric_table(rows, "regression")
    assert table.loc["Mean", "MAE"] == 0.1235 and table.loc["Std", "MSE"] == pytest.approx(1.4142)
    assert table.loc["0", "MAE"] == 0.1234 and np.isnan(table.loc["0", "R2"])


def test_trained_model_maps_encoded_classes_back_and_checks_features() -> None:
    from sklearn.linear_model import LogisticRegression

    X = pd.DataFrame({"a": [-2.0, -1.0, 1.0, 2.0], "b": [0.0, 1.0, 0.0, 1.0]})
    y, classes = encode_labels(pd.Series(["down", "down", "up", "up"]))
    pipeline = make_pipeline(LogisticRegression()).fit(X, y)
    model = TrainedModel("classification", pipeline, ["a", "b"], classes)
    preds = model.predict(X.assign(extra="kept"))
    assert preds["prediction_label"].tolist() == ["down", "down", "up", "up"]
    assert preds["extra"].tolist() == ["kept"] * 4
    with pytest.raises(ValueError, match=r"missing feature columns: \['b'\]"):
        model.predict(X[["a"]])
    with pytest.raises(ValueError, match="must be numeric"):
        feature_matrix(X.assign(b="x"), ["a", "b"])
