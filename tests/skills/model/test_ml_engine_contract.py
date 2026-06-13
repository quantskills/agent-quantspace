from __future__ import annotations

import pytest


def test_ml_engine_lazy_import_error_is_actionable(monkeypatch) -> None:
    import skills.model.ml_engine as ml_engine

    def _raise_import_error(task: str):
        raise ImportError("missing pycaret")

    monkeypatch.setattr(ml_engine, "_get_pycaret", _raise_import_error)
    engine = ml_engine.MLEngine(task="classification", model_name="xgboost")

    with pytest.raises(ImportError, match="missing pycaret"):
        engine.setup_and_train(train_data=None, target="label")
