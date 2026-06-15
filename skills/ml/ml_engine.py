"""Unified ML engine for classification and regression tasks.

Provides MLEngine for training/prediction and ModelPredictor for inference-only usage.
PyCaret is lazily imported to avoid slow startup.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def _get_data_root_path() -> Path:
    """Resolve data root: QUANTSPACE_DATA_ROOT or repo ``data/`` (same as DataManager)."""
    env_root = os.getenv("QUANTSPACE_DATA_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"


def _get_pycaret(task: str):
    """Lazily import PyCaret module based on task type."""
    if task == "classification":
        from pycaret.classification import (
            create_model,
            finalize_model,
            load_model,
            predict_model,
            pull,
            save_model,
            setup,
            tune_model,
        )
    elif task == "regression":
        from pycaret.regression import (
            create_model,
            finalize_model,
            load_model,
            predict_model,
            pull,
            save_model,
            setup,
            tune_model,
        )
    else:
        raise ValueError(f"Unknown task: {task}. Use 'classification' or 'regression'.")
    return (
        setup,
        create_model,
        finalize_model,
        predict_model,
        save_model,
        pull,
        load_model,
        tune_model,
    )


class MLEngine:
    """Unified PyCaret ML interface — supports classification and regression.

    Parameters
    ----------
    task : str
        'classification' or 'regression'
    model_name : str
        PyCaret model identifier, e.g. 'xgboost', 'catboost'
    normalize : str
        Normalization method for PyCaret setup
    """

    def __init__(self, task="classification", model_name="xgboost", normalize="zscore"):
        self.task = task
        self.model_name = model_name
        self.normalize = normalize
        self._pycaret = None
        self.model = None
        self.model_dir = None

    def _load_pycaret(self):
        if self._pycaret is None:
            self._pycaret = _get_pycaret(self.task)
        return self._pycaret

    def setup_and_train(
        self,
        train_data,
        target="label",
        pca_components=None,
        session_id=369,
        n_jobs=1,
        **create_kwargs,
    ):
        """Run PyCaret setup + create_model + finalize_model.

        Parameters
        ----------
        train_data : pd.DataFrame
            Training data with target column.
        target : str
            Target column name.
        pca_components : int, optional
            Number of PCA components. None to disable.
        session_id : int
            Random seed.
        n_jobs : int
            Number of parallel jobs.
        **create_kwargs
            Extra kwargs for create_model (e.g. objective, deterministic).

        Returns
        -------
        tuple
            (finalized_model, cv_metrics_df)
        """
        setup_fn, create_model, finalize_model, _, _, pull, _, _ = self._load_pycaret()

        setup_kwargs = {
            "data": train_data,
            "target": target,
            "session_id": session_id,
            "normalize": self.normalize,
            "n_jobs": n_jobs,
        }
        if pca_components is not None:
            setup_kwargs["pca"] = True
            setup_kwargs["pca_components"] = pca_components

        setup_fn(**setup_kwargs)

        if not create_kwargs:
            if self.task == "classification" and self.model_name in ("xgboost", "xgb"):
                create_kwargs = {
                    "deterministic": True,
                    "nthread": 1,
                    "n_jobs": 1,
                    "objective": "binary:logistic",
                }
            elif self.task == "classification" and self.model_name in ("catboost", "catb"):
                create_kwargs = {"nthread": 1, "objective": "Logloss"}

        model = create_model(self.model_name, **create_kwargs)
        cv_metrics = pull()
        cv_metrics.index = cv_metrics.index.astype(str)
        logger.info("CV metrics:\n%s", cv_metrics.loc[["Mean"]])

        self.model = finalize_model(model)
        return self.model, cv_metrics

    def predict(self, data):
        """Run prediction using the trained model.

        Parameters
        ----------
        data : pd.DataFrame
            Data to predict on.

        Returns
        -------
        pd.DataFrame
            Predictions with prediction_label (and prediction_score if classification).
        """
        _, _, _, predict_model, _, _, _, _ = self._load_pycaret()
        if self.model is None:
            raise ValueError("No model trained. Call setup_and_train() first.")
        return predict_model(self.model, data=data)

    def save(self, path):
        """Save the trained model."""
        _, _, _, _, save_model, _, _, _ = self._load_pycaret()
        if self.model is None:
            raise ValueError("No model to save.")
        save_model(self.model, path)
        logger.info("Model saved to %s", path)

    def load(self, path):
        """Load a previously saved model."""
        _, _, _, _, _, _, load_model, _ = self._load_pycaret()
        self.model = load_model(path)
        logger.info("Model loaded from %s", path)
        return self.model

    def save_to_registry(
        self,
        pool_id: str,
        train_data: pd.DataFrame = None,
        target: str = "label",
        metrics: dict = None,
        pca_components: int = None,
        data_root: str = None,
    ) -> str:
        """Save trained model under ``data/models/{pool_id}/{model_id}/`` with metadata."""
        if self.model is None:
            raise ValueError("No model to save.")
        root = Path(data_root) if data_root else _get_data_root_path()
        model_id = f"{self.task}_{self.model_name}_{datetime.now():%Y%m%d_%H%M%S}"
        out_dir = root / "models" / pool_id / model_id
        out_dir.mkdir(parents=True, exist_ok=True)

        _, _, _, _, save_model, _, _, _ = self._load_pycaret()
        model_stem = out_dir / "model"
        save_model(self.model, str(model_stem))

        features = None
        if train_data is not None:
            features = [c for c in train_data.columns if c != target]

        try:
            import pycaret as _pc

            pycaret_version = getattr(_pc, "__version__", "unknown")
        except Exception:
            pycaret_version = "unknown"

        meta = {
            "model_id": model_id,
            "pool_id": pool_id,
            "task": self.task,
            "model_name": self.model_name,
            "target": target,
            "features": features,
            "metrics": metrics if metrics is not None else {},
            "pca_components": pca_components,
            "normalize": self.normalize,
            "created_at": datetime.now().isoformat(),
            "pycaret_version": pycaret_version,
        }
        with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, default=str)

        logger.info("Model saved to registry: %s", out_dir)
        return model_id

    def load_from_registry(self, pool_id: str, model_id: str, data_root: str = None) -> object:
        """Load model from ``data/models/{pool_id}/{model_id}/model`` (PyCaret stem, adds .pkl)."""
        root = Path(data_root) if data_root else _get_data_root_path()
        model_stem = root / "models" / pool_id / model_id / "model"
        _, _, _, _, _, _, load_model, _ = self._load_pycaret()
        self.model = load_model(str(model_stem))
        logger.info("Model loaded from registry: %s", model_stem)
        return self.model

    @staticmethod
    def list_models(pool_id: str, data_root: str = None) -> list[dict]:
        """List saved models for a pool (metadata only), newest ``created_at`` first."""
        root = Path(data_root) if data_root else _get_data_root_path()
        pool_dir = root / "models" / pool_id
        if not pool_dir.is_dir():
            return []
        metas = []
        for sub in pool_dir.iterdir():
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
        **create_kwargs,
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
            Passed to PyCaret setup. Defaults to 1 (serial) because
            PyCaret ``setup()`` is not thread-safe.
        **create_kwargs
            Extra kwargs forwarded to ``setup_and_train``.

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
                    **create_kwargs,
                )
                mean_row = (
                    cv_metrics.loc["Mean"] if "Mean" in cv_metrics.index else cv_metrics.iloc[-1]
                )
                row = mean_row.to_dict()
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
    """Inference-only wrapper: load a saved PyCaret model and predict on new data.

    Handles PCA alignment by concatenating train features with test features
    (the "3-segment" trick from HZ_1).

    Parameters
    ----------
    model_path : str
        Path to the saved PyCaret model (without .pkl extension).
    train_features : pd.DataFrame
        Training features used during model training (needed for PCA alignment).
    task : str
        'classification' or 'regression'
    """

    def __init__(self, model_path, train_features, task="classification"):
        if task == "classification":
            from pycaret.classification import load_model, predict_model
        else:
            from pycaret.regression import load_model, predict_model
        self._predict_model = predict_model
        self.model_path = model_path
        self.model = load_model(os.path.splitext(model_path)[0])
        logger.info("Model loaded: %s", model_path)
        self.train_features = train_features
        self._another_train = train_features.copy()
        self._another_train.index = self._another_train.index + pd.DateOffset(years=100)

    def predict(self, test_features):
        """Predict on test features with PCA alignment.

        Parameters
        ----------
        test_features : pd.DataFrame
            New feature data to predict on.

        Returns
        -------
        pd.DataFrame
            Columns: prediction_label, prediction_score (if classification).
        """
        if test_features.dropna().empty:
            raise ValueError("test_features is empty after dropping NaN")
        pca_features = pd.concat([self.train_features, test_features, self._another_train]).dropna()
        pca_preds = self._predict_model(self.model, data=pca_features)
        inter_idx = pca_preds.index.intersection(test_features.index)
        if inter_idx.empty:
            raise ValueError("No intersection between predictions and test_features")
        pred_cols = ["prediction_label"]
        if "prediction_score" in pca_preds.columns:
            pred_cols.append("prediction_score")
        return pca_preds.loc[inter_idx][pred_cols]
