"""Unified ML engine for classification and regression tasks.

Provides MLEngine for training/prediction and ModelPredictor for inference-only usage.
Models are scikit-learn pipelines (mean imputation, scaling, optional PCA, estimator)
built by :mod:`skills.ml.estimators`; scikit-learn and XGBoost load lazily.

Training follows PyCaret 3.3's defaults, which QuantSpace used before: a shuffled
70/30 split (stratified for classification) seeded by ``session_id``, k-fold
cross-validation on the 70% part (``StratifiedKFold`` for classification, ``KFold``
for regression, unshuffled), then a final fit on every row.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from skills.ml.estimators import (
    LABEL_COLUMN,
    SCORE_COLUMN,
    TrainedModel,
    check_model,
    check_normalize,
    check_task,
    cross_validation_table,
    encode_labels,
    feature_matrix,
    make_estimator,
    make_pipeline,
)
from skills.store.workspace import resolve_workspace_paths

logger = logging.getLogger(__name__)

TRAIN_SIZE = 0.7
MODEL_FORMAT = "quantspace-sklearn-v1"


def _get_data_root_path() -> Path:
    """Resolve data root: QUANTSPACE_DATA_ROOT or repo ``data/`` (same as DataManager)."""
    return resolve_workspace_paths().data_root


def _model_file(path) -> Path:
    """``path`` with a ``.pkl`` suffix (a stem such as ``models/model`` gets one appended)."""
    path = Path(path)
    return path if path.suffix == ".pkl" else path.with_name(path.name + ".pkl")


def check_model_format(meta: dict) -> None:
    """Raise ``ValueError`` unless registry metadata was written by this engine."""
    if meta.get("format") == MODEL_FORMAT:
        return
    model = f"{meta.get('namespace')}/{meta.get('model_id')}"
    if "pycaret_version" in meta:
        raise ValueError(
            f"Model {model} was saved by PyCaret {meta['pycaret_version']}, which QuantSpace "
            "no longer uses; train it again with `qs ml train --write`."
        )
    raise ValueError(
        f"Model {model} has format {meta.get('format')!r}, expected {MODEL_FORMAT!r}; "
        "train it again with `qs ml train --write`."
    )


def load_model_file(path) -> TrainedModel:
    """Load a model written by ``MLEngine.save`` or ``save_to_registry``."""
    import joblib

    try:
        model = joblib.load(_model_file(path))
    except ModuleNotFoundError as exc:
        raise ValueError(
            f"{_model_file(path)} needs module {exc.name!r} to load; models saved before "
            "QuantSpace dropped PyCaret must be trained again."
        ) from exc
    if not isinstance(model, TrainedModel):
        raise ValueError(f"{_model_file(path)} is not an MLEngine model.")
    return model


def _versions() -> dict:
    from importlib.metadata import PackageNotFoundError, version

    found = {}
    for package in ("scikit-learn", "xgboost"):
        try:
            found[package.replace("-", "_") + "_version"] = version(package)
        except PackageNotFoundError:
            found[package.replace("-", "_") + "_version"] = None
    return found


class MLEngine:
    """Unified scikit-learn / XGBoost ML interface — supports classification and regression.

    Parameters
    ----------
    task : str
        'classification' or 'regression'
    model_name : str
        Model id from ``skills.ml.estimators.MODEL_IDS[task]``, e.g. 'xgboost', 'lr', 'rf'
    normalize : str
        Feature scaling: 'zscore', 'minmax', 'maxabs', 'robust' or 'none'
    """

    def __init__(self, task="classification", model_name="xgboost", normalize="zscore"):
        self.task = check_task(task)
        self.model_name = check_model(task, model_name)
        self.normalize = check_normalize(normalize)
        self.model = None
        self.model_dir = None
        self.session_id = None
        self.folds = None
        self.model_params = {}

    def setup_and_train(
        self,
        train_data,
        target="label",
        pca_components=None,
        session_id=369,
        n_jobs=1,
        folds=10,
        model_params=None,
    ):
        """Cross-validate on the 70% split, then fit the model on every row.

        Parameters
        ----------
        train_data : pd.DataFrame
            Training data with target column; every other column is a numeric feature.
        target : str
            Target column name.
        pca_components : int, optional
            Number of PCA components. None to disable.
        session_id : int
            Random seed for the split, the PCA, and the estimator.
        n_jobs : int
            Parallel jobs for estimators that support them.
        folds : int
            Cross-validation folds.
        model_params : dict, optional
            Estimator constructor arguments overriding the defaults (e.g. n_estimators).

        Returns
        -------
        tuple
            (trained model, cv_metrics_df) where cv_metrics_df is indexed by fold
            ``"0".."k-1"``, ``"Mean"``, ``"Std"``.
        """
        from sklearn.base import clone
        from sklearn.model_selection import KFold, StratifiedKFold, train_test_split

        if target not in train_data.columns:
            raise ValueError(f"train_data requires target column {target!r}")
        features = [column for column in train_data.columns if column != target]
        X = feature_matrix(train_data, features)
        y = train_data[target]
        if y.isna().any():
            raise ValueError(f"{int(y.isna().sum())} missing values in target column {target!r}")
        estimator = make_estimator(
            self.task, self.model_name, random_state=session_id, n_jobs=n_jobs, params=model_params
        )
        pipeline = make_pipeline(
            estimator,
            normalize=self.normalize,
            pca_components=pca_components,
            random_state=session_id,
        )
        classes = None
        if self.task == "classification":
            y, classes = encode_labels(y)
            cv = StratifiedKFold(folds)
        else:
            y = y.to_numpy()
            cv = KFold(folds)
        train_idx, test_idx = train_test_split(
            np.arange(len(X)),
            train_size=TRAIN_SIZE,
            random_state=session_id,
            shuffle=True,
            stratify=y if self.task == "classification" else None,
        )
        cv_metrics = cross_validation_table(
            pipeline, X.iloc[train_idx], y[train_idx], task=self.task, cv=cv
        )
        logger.info("CV metrics:\n%s", cv_metrics.loc[["Mean"]])

        # Final fit on every row, training split first (PyCaret's finalize_model order).
        order = np.concatenate([train_idx, test_idx])
        fitted = clone(pipeline).fit(X.iloc[order], y[order])
        self.model = TrainedModel(self.task, fitted, features, classes)
        self.session_id, self.folds = session_id, folds
        self.model_params = dict(model_params or {})
        return self.model, cv_metrics

    def predict(self, data):
        """Run prediction using the trained model.

        Parameters
        ----------
        data : pd.DataFrame
            Data to predict on; it must hold the training feature columns.

        Returns
        -------
        pd.DataFrame
            ``data`` plus prediction_label (and prediction_score if classification).
        """
        if self.model is None:
            raise ValueError("No model trained. Call setup_and_train() first.")
        return self.model.predict(data)

    def save(self, path):
        """Save the trained model to ``path`` (``.pkl`` is appended to a bare stem)."""
        import joblib

        if self.model is None:
            raise ValueError("No model to save.")
        joblib.dump(self.model, _model_file(path))
        logger.info("Model saved to %s", _model_file(path))

    def load(self, path):
        """Load a model saved by ``save``."""
        self.model = load_model_file(path)
        logger.info("Model loaded from %s", _model_file(path))
        return self.model

    def save_to_registry(
        self,
        namespace: str,
        train_data: pd.DataFrame = None,
        target: str = "label",
        metrics: dict = None,
        pca_components: int = None,
        data_root: str = None,
    ) -> str:
        """Save trained model under ``data/models/{namespace}/{model_id}/`` with metadata."""
        if self.model is None:
            raise ValueError("No model to save.")
        root = Path(data_root) if data_root else _get_data_root_path()
        model_id = f"{self.task}_{self.model_name}_{datetime.now():%Y%m%d_%H%M%S}"
        out_dir = root / "models" / namespace / model_id
        out_dir.mkdir(parents=True, exist_ok=True)
        self.save(out_dir / "model.pkl")

        features = None
        if train_data is not None:
            features = [c for c in train_data.columns if c != target]

        meta = {
            "model_id": model_id,
            "namespace": namespace,
            "format": MODEL_FORMAT,
            "task": self.task,
            "model_name": self.model_name,
            "model_params": self.model_params,
            "target": target,
            "features": features,
            "metrics": metrics if metrics is not None else {},
            "pca_components": pca_components,
            "normalize": self.normalize,
            "session_id": self.session_id,
            "folds": self.folds,
            "created_at": datetime.now().isoformat(),
            **_versions(),
        }
        with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, default=str)

        logger.info("Model saved to registry: %s", out_dir)
        return model_id

    def load_from_registry(self, namespace: str, model_id: str, data_root: str = None) -> object:
        """Load model from ``data/models/{namespace}/{model_id}/model.pkl``."""
        root = Path(data_root) if data_root else _get_data_root_path()
        model_dir = root / "models" / namespace / model_id
        with open(model_dir / "metadata.json", encoding="utf-8") as f:
            check_model_format(json.load(f))
        self.model = load_model_file(model_dir / "model.pkl")
        logger.info("Model loaded from registry: %s", model_dir)
        return self.model

    @staticmethod
    def list_models(namespace: str, data_root: str = None) -> list[dict]:
        """List saved models for a namespace (metadata only), newest ``created_at`` first."""
        root = Path(data_root) if data_root else _get_data_root_path()
        namespace_dir = root / "models" / namespace
        if not namespace_dir.is_dir():
            return []
        metas = []
        for sub in namespace_dir.iterdir():
            if not sub.is_dir():
                continue
            meta_path = sub / "metadata.json"
            if meta_path.is_file():
                with open(meta_path, encoding="utf-8") as f:
                    metas.append(json.load(f))
        metas.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return metas

    def batch_train(
        self,
        train_data,
        target="label",
        pca_range=None,
        session_id=369,
        n_jobs=1,
        folds=10,
        model_params=None,
    ):
        """Sweep PCA dimensions and train a model for each, returning metrics.

        Parameters
        ----------
        train_data : pd.DataFrame
            Training data with target column.
        target : str
            Target column name.
        pca_range : iterable of int, optional
            PCA component counts to sweep.  Defaults to range(1, 51).
        session_id : int
            Random seed.
        n_jobs : int
            Parallel jobs for estimators that support them.
        folds : int
            Cross-validation folds.
        model_params : dict, optional
            Estimator constructor arguments forwarded to ``setup_and_train``.

        Returns
        -------
        pd.DataFrame
            Indexed by ``pca_components`` with metric columns (e.g. Accuracy, F1).
        """
        if pca_range is None:
            pca_range = range(1, 51)

        rows = []
        for pca_n in pca_range:
            try:
                _, cv_metrics = self.setup_and_train(
                    train_data,
                    target=target,
                    pca_components=pca_n,
                    session_id=session_id,
                    n_jobs=n_jobs,
                    folds=folds,
                    model_params=model_params,
                )
                row = cv_metrics.loc["Mean"].to_dict()
                row["pca_components"] = pca_n
                rows.append(row)
                logger.info(
                    "PCA=%d done: %s",
                    pca_n,
                    {k: f"{v:.4f}" for k, v in row.items() if isinstance(v, float)},
                )
            except Exception as e:
                logger.warning("PCA=%d failed: %s", pca_n, e)
                rows.append({"pca_components": pca_n})

        result = pd.DataFrame(rows).set_index("pca_components")
        return result


class ModelPredictor:
    """Inference-only wrapper: load a saved MLEngine model and predict on new data.

    Rows with missing values are dropped before predicting. Preprocessing (including
    PCA) is fitted inside the saved pipeline, so no training rows are needed.

    Parameters
    ----------
    model_path : str
        Path to the saved model, with or without the ``.pkl`` extension.
    """

    def __init__(self, model_path):
        self.model_path = model_path
        self.model = load_model_file(model_path)
        logger.info("Model loaded: %s", model_path)

    def predict(self, test_features):
        """Predict on test features.

        Parameters
        ----------
        test_features : pd.DataFrame
            New feature data to predict on.

        Returns
        -------
        pd.DataFrame
            Columns: prediction_label, prediction_score (if classification).
        """
        rows = test_features.dropna()
        if rows.empty:
            raise ValueError("test_features is empty after dropping NaN")
        preds = self.model.predict(rows)
        pred_cols = [LABEL_COLUMN]
        if SCORE_COLUMN in preds.columns:
            pred_cols.append(SCORE_COLUMN)
        return preds[pred_cols]
