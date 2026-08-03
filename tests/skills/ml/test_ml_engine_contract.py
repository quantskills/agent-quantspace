from __future__ import annotations

import json

import pytest


def test_ml_engine_lazy_import_error_is_actionable(monkeypatch) -> None:
    import skills.ml.ml_engine as ml_engine

    def _raise_import_error(task: str):
        raise ImportError("missing pycaret")

    monkeypatch.setattr(ml_engine, "_get_pycaret", _raise_import_error)
    engine = ml_engine.MLEngine(task="classification", model_name="xgboost")

    with pytest.raises(ImportError, match="missing pycaret"):
        engine.setup_and_train(train_data=None, target="label")


def test_ml_model_registry_is_scoped_by_namespace(tmp_path) -> None:
    import skills.ml.ml_engine as ml_engine

    model_dir = tmp_path / "models" / "macro_weekly" / "model_1"
    model_dir.mkdir(parents=True)
    metadata = {"model_id": "model_1", "namespace": "macro_weekly", "created_at": "2026-07-22"}
    (model_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    assert ml_engine.MLEngine.list_models(namespace="macro_weekly", data_root=str(tmp_path)) == [
        metadata
    ]
