from __future__ import annotations

import contextlib
import io

import numpy as np
import pandas as pd
import pytest

from skills.compute.indicators import roc, rsi
from skills.ml.ml_factor import MLFactorEngine, make_precomputed_factor
from tests.fixtures.market_data import make_ohlcv


def test_make_precomputed_factor_reads_pivot_value_for_group_dates() -> None:
    dates = pd.date_range("2024-01-01", periods=2, name="eob")
    pivot = pd.DataFrame({"AAA": [0.2, 0.8]}, index=dates)
    factor = make_precomputed_factor(pivot, name="ml_rank")
    group = pd.DataFrame(
        {"close": [10.0, 11.0]},
        index=pd.MultiIndex.from_product([["AAA"], dates], names=["symbol", "eob"]),
    )

    result = factor(group)

    assert result.tolist() == [0.2, 0.8]
    assert factor.__name__ == "ml_rank"


def test_eval_summary_averages_metrics_past_the_text_model_column() -> None:
    engine = MLFactorEngine.__new__(MLFactorEngine)
    engine.eval_df = pd.DataFrame({"ic": [0.1, 0.3], "period_type": ["out_of_sample"] * 2})
    engine.cv_metrics_list = [
        pd.DataFrame({"MAE": [0.1, 0.3], "R2": [0.2, 0.4]}, index=["Mean", "Std"]),
        pd.DataFrame({"MAE": [0.3, 0.1], "R2": [0.4, 0.2]}, index=["Mean", "Std"]),
    ]
    # Holdout metrics carry the estimator name as text.
    engine.holdout_metrics_list = [
        pd.DataFrame({"Model": ["Extreme Gradient Boosting"], "MAE": [0.1]}),
        pd.DataFrame({"Model": ["Extreme Gradient Boosting"], "MAE": [0.3]}),
    ]

    summary = engine.get_eval_summary()

    assert summary["holdout_metrics_mean"] == pytest.approx({"MAE": 0.2})
    assert summary["cv_metrics_mean"] == pytest.approx({"MAE": 0.2, "R2": 0.3})
    assert summary["out_of_sample"]["ic_mean"] == pytest.approx(0.2)


def _panel(symbols=6, periods=140, seed=11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = [
        make_ohlcv(100 * np.exp(np.cumsum(rng.normal(0, 0.01, periods))), symbol=f"S{i}")
        for i in range(symbols)
    ]
    return pd.concat(frames).sort_index()


CONFIGS = [
    {"func": roc, "kwargs": {"period": 5}, "name": "roc5"},
    {"func": rsi, "kwargs": {"period": 14}, "name": "rsi"},
]


def _generate(**kwargs) -> MLFactorEngine:
    engine = MLFactorEngine(data=_panel(), factor_configs=CONFIGS, **kwargs)
    with contextlib.redirect_stdout(io.StringIO()):
        engine.generate()
    return engine


def test_fixed_mode_uses_time_series_folds_and_pycaret_metric_tables() -> None:
    from sklearn.base import clone
    from sklearn.model_selection import TimeSeriesSplit

    from skills.ml.estimators import make_estimator, make_pipeline, score

    engine = _generate(model_type="lr", train_mode="fixed", n_folds=3)
    (cv,) = engine.cv_metrics_list
    (holdout,) = engine.holdout_metrics_list
    assert list(cv.index) == ["0", "1", "2", "Mean", "Std"]
    assert list(holdout.columns) == ["Model", "MAE", "MSE", "RMSE", "R2", "RMSLE", "MAPE"]
    assert holdout["Model"].iloc[0] == "LinearRegression"

    df = engine._feature_df
    train = df[df["eob"] < engine.oos_start_date].reset_index(drop=True)
    X, y = train[["roc5", "rsi"]], train["forward_rank"].to_numpy()
    pipeline = make_pipeline(make_estimator("regression", "lr", random_state=42, n_jobs=-1))
    for fold, (fit_idx, test_idx) in enumerate(TimeSeriesSplit(3).split(X)):
        model = clone(pipeline).fit(X.iloc[fit_idx], y[fit_idx])
        expected = score("regression", model, X.iloc[test_idx], y[test_idx])
        assert cv.loc[str(fold)].to_dict() == pytest.approx(expected, abs=5e-5)

    rank = engine.prediction_rank_pivot
    assert rank.index.min() == df["eob"].min() and rank.index.max() == df["eob"].max()
    assert np.nanmin(rank.to_numpy()) > 0 and np.nanmax(rank.to_numpy()) <= 1
    summary = engine.get_eval_summary()
    assert set(summary["cv_metrics_mean"]) == {"MAE", "MSE", "RMSE", "R2", "RMSLE", "MAPE"}
    assert summary["out_of_sample"]["n_dates"] > 0
    assert engine.feature_importance_df is None  # linear models report none


def test_rolling_mode_averages_importances_and_honours_model_params() -> None:
    engine = _generate(
        model_type="xgboost",
        train_mode="rolling",
        train_window=60,
        retrain_freq=30,
        model_params={"n_estimators": 15, "max_depth": 2},
    )
    assert len(engine.models) == len(engine.cv_metrics_list) == len(engine.holdout_metrics_list)
    assert len(engine.models) >= 2
    assert {model[-1].get_params()["n_estimators"] for model in engine.models} == {15}
    assert engine.prediction_rank_pivot.index.min() == engine.oos_start_date
    importance = engine.get_feature_importance()
    assert sorted(importance["feature"]) == ["roc5", "rsi"]
    assert importance["importance"].sum() == pytest.approx(1.0, abs=1e-6)


def test_unknown_models_and_params_fail_before_training() -> None:
    with pytest.raises(ValueError, match="Unknown regression model 'lightgbm'"):
        MLFactorEngine(data=None, factor_configs=CONFIGS, model_type="lightgbm")
    with pytest.raises(ValueError, match="depth"):
        MLFactorEngine(data=None, factor_configs=CONFIGS, model_params={"depth": 3})
