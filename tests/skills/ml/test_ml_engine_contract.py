from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from skills.ml import ml_engine
from skills.ml.estimators import encode_labels, make_estimator, make_pipeline, score
from skills.ml.ml_engine import MLEngine, ModelPredictor


def _table(rows=60, labels=(0, 1), seed=4):
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(rng.normal(size=(rows, 3)), columns=["a", "b", "c"])
    frame["label"] = np.where(frame["a"] + 0.3 * rng.normal(size=rows) > 0, *labels[::-1])
    return frame


def test_ml_model_registry_is_scoped_by_namespace(tmp_path) -> None:
    model_dir = tmp_path / "models" / "macro_weekly" / "model_1"
    model_dir.mkdir(parents=True)
    metadata = {"model_id": "model_1", "namespace": "macro_weekly", "created_at": "2026-07-22"}
    (model_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    assert MLEngine.list_models(namespace="macro_weekly", data_root=str(tmp_path)) == [metadata]


def test_engine_rejects_unknown_tasks_models_and_normalize_methods() -> None:
    with pytest.raises(ValueError, match="Unknown task"):
        MLEngine(task="ranking")
    with pytest.raises(ValueError, match="Supported: lr, ridge"):
        MLEngine(task="classification", model_name="catboost")
    with pytest.raises(ValueError, match="regression model 'gbc'"):
        MLEngine(task="regression", model_name="gbc")
    with pytest.raises(ValueError, match="normalize method"):
        MLEngine(normalize="quantile")


def test_cv_follows_pycaret_split_and_folds() -> None:
    """70/30 stratified shuffled split seeded by session_id, StratifiedKFold on the 70%."""
    from sklearn.base import clone
    from sklearn.model_selection import StratifiedKFold, train_test_split

    frame = _table(labels=(-1, 1))
    engine = MLEngine(task="classification", model_name="lr")
    _, cv = engine.setup_and_train(frame, target="label", session_id=7, folds=4)

    X, (y, _) = frame[["a", "b", "c"]], encode_labels(frame["label"])
    train_idx, _ = train_test_split(
        np.arange(len(X)), train_size=0.7, random_state=7, shuffle=True, stratify=y
    )
    pipeline = make_pipeline(make_estimator("classification", "lr", random_state=7))
    X_train, y_train = X.iloc[train_idx], y[train_idx]
    for fold, (fit_idx, test_idx) in enumerate(StratifiedKFold(4).split(X_train, y_train)):
        model = clone(pipeline).fit(X_train.iloc[fit_idx], y_train[fit_idx])
        expected = score("classification", model, X_train.iloc[test_idx], y_train[test_idx], 2)
        assert cv.loc[str(fold)].to_dict() == pytest.approx(expected, abs=5e-5)
    assert list(cv.index) == ["0", "1", "2", "3", "Mean", "Std"] and cv.index.name == "Fold"
    folds = cv.iloc[:4]
    assert cv.loc["Mean"].to_numpy() == pytest.approx(folds.mean().to_numpy(), abs=1e-4)
    assert cv.loc["Std"].to_numpy() == pytest.approx(folds.std(ddof=0).to_numpy(), abs=1e-4)


def test_predictions_keep_input_columns_and_original_labels(tmp_path) -> None:
    frame = _table(labels=(-1, 1))
    engine = MLEngine(task="classification", model_name="xgboost")
    engine.setup_and_train(frame, target="label", folds=3, model_params={"n_estimators": 20})
    rows = frame.drop(columns="label").head(9)
    preds = engine.predict(rows)
    assert list(preds.columns) == ["a", "b", "c", "prediction_label", "prediction_score"]
    pd.testing.assert_frame_equal(preds[["a", "b", "c"]], rows)
    assert set(preds["prediction_label"]) <= {-1, 1}
    assert preds["prediction_score"].between(0.5, 1).all()

    engine.save(tmp_path / "model")
    assert (tmp_path / "model.pkl").exists()
    predictor = ModelPredictor(str(tmp_path / "model"))
    with_gap = rows.copy()
    with_gap.iloc[0, 0] = np.nan
    result = predictor.predict(with_gap)
    assert list(result.columns) == ["prediction_label", "prediction_score"]
    pd.testing.assert_frame_equal(result, preds.iloc[1:][["prediction_label", "prediction_score"]])


def test_regression_engine_and_batch_train_sweep_pca() -> None:
    frame = _table().assign(label=lambda f: f["a"] * 2 + f["b"])
    engine = MLEngine(task="regression", model_name="ridge")
    sweep = engine.batch_train(frame, target="label", pca_range=[1, 3], folds=3)
    assert list(sweep.index) == [1, 3]
    assert list(sweep.columns) == ["MAE", "MSE", "RMSE", "R2", "RMSLE", "MAPE"]
    # Every component keeps the linear target fully explained; one does not.
    assert sweep.loc[3, "R2"] > 0.99 > sweep.loc[1, "R2"]
    preds = engine.predict(frame.drop(columns="label"))
    assert list(preds.columns)[-1] == "prediction_label"


def test_registry_refuses_pycaret_models(tmp_path) -> None:
    model_dir = tmp_path / "models" / "demo" / "old"
    model_dir.mkdir(parents=True)
    (model_dir / "model.pkl").write_bytes(b"not loaded")
    meta = {"model_id": "old", "namespace": "demo", "pycaret_version": "3.3.2"}
    (model_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    engine = MLEngine()
    with pytest.raises(ValueError, match="saved by PyCaret 3.3.2"):
        engine.load_from_registry("demo", "old", data_root=str(tmp_path))
    with pytest.raises(ValueError, match="expected 'quantspace-sklearn-v1'"):
        ml_engine.check_model_format({"model_id": "x", "format": "other"})


def test_loading_a_file_that_is_not_an_engine_model_fails(tmp_path) -> None:
    import joblib

    joblib.dump({"not": "a model"}, tmp_path / "other.pkl")
    with pytest.raises(ValueError, match="is not an MLEngine model"):
        ml_engine.load_model_file(tmp_path / "other.pkl")
