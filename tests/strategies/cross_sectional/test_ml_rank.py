from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import strategies.cross_sectional.ml_rank as ml_rank
from strategies.cross_sectional.ml_rank import (
    ExpandingPCAModelResult,
    cross_sectional_rank_labels,
    expanding_pca_model_scores,
    expanding_pca_model_weights,
    rank_scores_to_weights,
)


def _bars(prices: list[float]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(prices), name="eob")
    close = pd.Series(prices, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000.0,
        },
        index=index,
    )


def test_rank_weights_fail_without_expanding_folds() -> None:
    panel = pd.concat(
        [
            _bars([10.0, 11.0, 12.0]).assign(symbol="A").reset_index().set_index(["symbol", "eob"]),
            _bars([10.0, 9.0, 8.0]).assign(symbol="B").reset_index().set_index(["symbol", "eob"]),
        ]
    ).sort_index()

    with pytest.raises(ValueError, match="at least one expanding fold"):
        expanding_pca_model_weights(panel, horizon=1, min_train=2, retrain_step=1, top_n=1)


def test_rank_scores_to_weights_selects_top_n_and_normalizes() -> None:
    index = pd.date_range("2024-01-01", periods=5, name="eob")
    score = pd.DataFrame({"A": [0, 1, 3, 3, 3], "B": [0, 3, 1, 1, 1]}, index=index)
    close = pd.DataFrame({"A": [10, 10, 11, 12, 13], "B": [10, 11, 12, 13, 14]}, index=index)

    weights = rank_scores_to_weights(score, close, top_n=1, vol_lookback=2)

    assert weights.iloc[-1]["A"] == pytest.approx(1.0)
    assert weights.iloc[-1]["B"] == pytest.approx(0.0)


def test_rank_scores_to_weights_equal_top_n_splits_evenly() -> None:
    index = pd.date_range("2024-01-01", periods=3, name="eob")
    score = pd.DataFrame(
        {"A": [3.0, 3.0, 3.0], "B": [2.0, 2.0, 2.0], "C": [1.0, 1.0, 1.0]},
        index=index,
    )
    close = pd.DataFrame(
        {"A": [10, 11, 12], "B": [10, 11, 12], "C": [10, 11, 12]},
        index=index,
    )

    weights = rank_scores_to_weights(score, close, top_n=2, weighting="equal")

    assert weights.iloc[-1]["A"] == pytest.approx(1 / 2)
    assert weights.iloc[-1]["B"] == pytest.approx(1 / 2)
    assert weights.iloc[-1]["C"] == pytest.approx(0.0)


def test_rank_scores_to_weights_equal_constraints() -> None:
    index = pd.date_range("2024-01-01", periods=8, name="eob")
    rng = np.random.default_rng(0)
    symbols = ["A", "B", "C", "D", "E"]
    score = pd.DataFrame(rng.normal(size=(len(index), len(symbols))), index=index, columns=symbols)
    close = pd.DataFrame(
        np.cumprod(1 + rng.normal(0.001, 0.01, size=(len(index), len(symbols))), axis=0) * 10,
        index=index,
        columns=symbols,
    )
    top_n = 3

    weights = rank_scores_to_weights(score, close, top_n=top_n, weighting="equal")

    assert (weights >= 0.0).all().all()
    assert (weights.gt(0.0).sum(axis=1) <= top_n).all()
    row_sums = weights.sum(axis=1)
    assert ((row_sums == 0.0) | np.isclose(row_sums, 1.0)).all()


def test_cross_sectional_rank_labels_align_to_panel_index() -> None:
    panel = pd.concat(
        [
            _bars([10.0, 11.0, 12.0]).assign(symbol="A").reset_index().set_index(["symbol", "eob"]),
            _bars([10.0, 9.0, 8.0]).assign(symbol="B").reset_index().set_index(["symbol", "eob"]),
        ]
    ).sort_index()

    labels = cross_sectional_rank_labels(panel, horizon=1)

    assert labels.index.names == ["symbol", "eob"]
    assert labels.dropna().index.isin(panel.index).all()


def test_cross_sectional_rank_labels_drop_tail_without_full_horizon() -> None:
    panel = pd.concat(
        [
            _bars([10.0, 11.0, 12.0, 13.0]).assign(symbol="A").reset_index().set_index(["symbol", "eob"]),
            _bars([10.0, 9.0, 8.0, 7.0]).assign(symbol="B").reset_index().set_index(["symbol", "eob"]),
        ]
    ).sort_index()

    labels = cross_sectional_rank_labels(panel, horizon=2)
    label_dates = labels.index.get_level_values("eob").unique()

    assert panel.index.get_level_values("eob").max() not in label_dates
    assert panel.index.get_level_values("eob").unique()[-2] not in label_dates
    assert panel.index.get_level_values("eob").unique()[-3] in label_dates


def test_cross_sectional_rank_labels_percentile_within_date() -> None:
    panel = pd.concat(
        [
            _bars([10.0, 20.0]).assign(symbol="A").reset_index().set_index(["symbol", "eob"]),
            _bars([10.0, 10.0]).assign(symbol="B").reset_index().set_index(["symbol", "eob"]),
        ]
    ).sort_index()

    labels = cross_sectional_rank_labels(panel, horizon=1)

    first_date = panel.index.get_level_values("eob").unique()[0]
    day_labels = labels.xs(first_date, level="eob")
    assert day_labels.loc["A"] == pytest.approx(1.0)
    assert day_labels.loc["B"] == pytest.approx(0.5)


def test_expanding_pca_model_scores_uses_expanding_purged_folds(monkeypatch) -> None:
    dates = pd.date_range("2024-01-01", periods=12, name="eob")
    symbols = ["A", "B"]
    index = pd.MultiIndex.from_product([symbols, dates], names=["symbol", "eob"])
    features = pd.DataFrame({"feature": range(len(index))}, index=index, dtype=float)
    labels = pd.Series(0.5, index=index, name="rank_label")
    captured = {"train_dates": [], "pred_dates": [], "pred_x_shapes": []}

    class FakeRegressor:
        def __init__(self, **kwargs) -> None:
            pass

        def fit(self, train_x, train_y) -> None:
            captured["train_dates"].append(train_x.shape)

        def predict(self, test_x):
            captured["pred_x_shapes"].append(test_x.shape)
            return [0.5] * len(test_x)

    def fake_fit_fold_transform(train_x, pred_x, *, n_pca=50, random_state=42):
        captured["train_dates"].append(train_x.shape[0])
        captured["pred_dates"].append(pred_x.shape[0])
        return type(
            "Transform",
            (),
            {
                "train_X": train_x[:, :1],
                "pred_X": pred_x[:, :1],
                "pca_explained_variance_sum": 0.9,
            },
        )()

    panel = pd.DataFrame({"close": 1.0}, index=index)
    monkeypatch.setattr(ml_rank, "make_logdiff_panel_features", lambda panel: features)
    monkeypatch.setattr(ml_rank, "cross_sectional_rank_labels", lambda panel, horizon: labels)
    monkeypatch.setattr(ml_rank, "fit_fold_transform", fake_fit_fold_transform)
    monkeypatch.setattr(ml_rank, "make_regressor", lambda model, random_state=42, rf_n_jobs=None: FakeRegressor())

    result = expanding_pca_model_scores(
        panel,
        model="xgboost",
        horizon=3,
        min_train=6,
        retrain_step=3,
    )

    assert isinstance(result, ExpandingPCAModelResult)
    assert result.scores.index.names == ["symbol", "eob"]
    assert result.scores.name == "score"
    assert {"fold_id", "mse", "rmse", "r2", "rank_ic", "pca_explained_variance_sum"}.issubset(
        set(result.fold_metrics.columns)
    )
    assert {"mse", "rmse", "r2", "rank_ic", "pca_explained_variance_sum"}.issubset(
        set(result.overall_metrics)
    )
    assert captured["train_dates"][0] > 0
    assert captured["pred_dates"][0] > 0


@pytest.mark.parametrize("model", ["ols", "lasso", "rf", "xgboost"])
def test_expanding_pca_model_scores_schema_consistent_across_models(monkeypatch, model: str) -> None:
    dates = pd.date_range("2024-01-01", periods=10, name="eob")
    symbols = ["A", "B"]
    index = pd.MultiIndex.from_product([symbols, dates], names=["symbol", "eob"])
    features = pd.DataFrame({"feature": range(len(index))}, index=index, dtype=float)
    labels = pd.Series(0.5, index=index, name="rank_label")

    class FakeRegressor:
        def __init__(self, **kwargs) -> None:
            self.coef_ = [1.0]

        def fit(self, train_x, train_y) -> None:
            return None

        def predict(self, test_x):
            return [0.5] * len(test_x)

    def fake_fit_fold_transform(train_x, pred_x, *, n_pca=50, random_state=42):
        return type(
            "Transform",
            (),
            {
                "train_X": train_x[:, :1],
                "pred_X": pred_x[:, :1],
                "pca_explained_variance_sum": 0.8,
            },
        )()

    panel = pd.DataFrame({"close": 1.0}, index=index)
    monkeypatch.setattr(ml_rank, "make_logdiff_panel_features", lambda panel: features)
    monkeypatch.setattr(ml_rank, "cross_sectional_rank_labels", lambda panel, horizon: labels)
    monkeypatch.setattr(ml_rank, "fit_fold_transform", fake_fit_fold_transform)
    monkeypatch.setattr(ml_rank, "make_regressor", lambda model, random_state=42, rf_n_jobs=None: FakeRegressor())

    result = expanding_pca_model_scores(
        panel,
        model=model,  # type: ignore[arg-type]
        horizon=2,
        min_train=4,
        retrain_step=2,
    )

    assert result.scores.index.names == ["symbol", "eob"]
    assert set(result.fold_metrics.columns) >= {
        "fold_id",
        "mse",
        "rmse",
        "r2",
        "rank_ic",
        "pca_explained_variance_sum",
        "lasso_nnz_coef",
    }
    if model == "lasso":
        assert "lasso_nnz_coef" in result.overall_metrics


def test_expanding_pca_model_scores_purges_by_label_horizon(monkeypatch) -> None:
    dates = pd.date_range("2024-01-01", periods=14, name="eob")
    symbols = ["A", "B"]
    index = pd.MultiIndex.from_product([symbols, dates], names=["symbol", "eob"])
    features = pd.DataFrame({"feature": range(len(index))}, index=index, dtype=float)
    labels = pd.Series(0.5, index=index, name="rank_label")
    captured: dict[str, object] = {}
    real_folds = ml_rank.expanding_purged_folds

    def spy_folds(fold_dates, **kwargs):
        captured.update(kwargs)
        folds = real_folds(fold_dates, **kwargs)
        captured["folds"] = folds
        return folds

    class FakeRegressor:
        def fit(self, train_x, train_y) -> None:
            return None

        def predict(self, test_x):
            return [0.5] * len(test_x)

    panel = pd.DataFrame({"close": 1.0}, index=index)
    monkeypatch.setattr(ml_rank, "make_logdiff_panel_features", lambda panel: features)
    monkeypatch.setattr(ml_rank, "cross_sectional_rank_labels", lambda panel, horizon: labels)
    monkeypatch.setattr(ml_rank, "expanding_purged_folds", spy_folds)
    monkeypatch.setattr(ml_rank, "make_regressor", lambda model, random_state=42, rf_n_jobs=None: FakeRegressor())

    result = expanding_pca_model_scores(panel, model="lasso", horizon=3, min_train=8, retrain_step=3)

    assert captured["purge"] == 3
    for fold in captured["folds"]:
        train_end = dates.get_loc(fold.train_dates.max())
        pred_start = dates.get_loc(fold.pred_dates.min())
        # The last training label resolves horizon days later, still before predict.
        assert train_end + 3 <= pred_start - 1
    scored_dates = set(result.scores.index.get_level_values("eob"))
    assert scored_dates.isdisjoint(set(captured["folds"][0].train_dates))


def test_expanding_pca_model_scores_default_protocol_params() -> None:
    signature = expanding_pca_model_scores.__kwdefaults__
    assert signature is not None
    assert signature["horizon"] == 20
    assert signature["min_train"] == 250
    assert signature["retrain_step"] == 370
    assert signature["n_pca"] == 50


def test_expanding_pca_multi_model_scores_shares_one_pca_per_fold(monkeypatch) -> None:
    dates = pd.date_range("2024-01-01", periods=20, name="eob")
    symbols = ["A", "B"]
    index = pd.MultiIndex.from_product([symbols, dates], names=["symbol", "eob"])
    features = pd.DataFrame(
        np.arange(len(index) * 4, dtype=float).reshape(len(index), 4),
        index=index,
        columns=["f0", "f1", "f2", "f3"],
    )
    labels = pd.Series(0.5, index=index, name="rank_label")
    pca_calls = {"n": 0}

    def fake_fit_fold_transform(train_x, pred_x, *, n_pca=50, random_state=42):
        del n_pca, random_state
        pca_calls["n"] += 1
        k = min(2, train_x.shape[1], train_x.shape[0])
        from skills.ml.pca_fold import FoldTransformResult

        return FoldTransformResult(
            train_X=np.asarray(train_x, dtype=float)[:, :k],
            pred_X=np.asarray(pred_x, dtype=float)[:, :k],
            pca_explained_variance_sum=0.9,
        )

    class FakeRegressor:
        def fit(self, train_x, train_y) -> None:
            return None

        def predict(self, test_x):
            return np.full(len(test_x), 0.5)

    panel = pd.DataFrame({"close": 1.0}, index=index)
    monkeypatch.setattr(ml_rank, "make_logdiff_panel_features", lambda panel: features)
    monkeypatch.setattr(ml_rank, "cross_sectional_rank_labels", lambda panel, horizon: labels)
    monkeypatch.setattr(ml_rank, "fit_fold_transform", fake_fit_fold_transform)
    monkeypatch.setattr(
        ml_rank,
        "make_regressor",
        lambda model, random_state=42, rf_n_jobs=None: FakeRegressor(),
    )

    results = ml_rank.expanding_pca_multi_model_scores(
        panel,
        models=("ols", "lasso", "rf", "xgboost"),
        horizon=2,
        min_train=6,
        retrain_step=4,
        n_pca=2,
    )
    n_folds = len(next(iter(results.values())).fold_metrics)
    assert pca_calls["n"] == n_folds
    assert set(results) == {"ols", "lasso", "rf", "xgboost"}
