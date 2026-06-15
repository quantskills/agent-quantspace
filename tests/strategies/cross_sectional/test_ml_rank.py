from __future__ import annotations

import pandas as pd
import pytest

import strategies.cross_sectional.ml_rank as ml_rank
from strategies.cross_sectional.ml_rank import (
    cross_sectional_rank_labels,
    rank_scores_to_weights,
    xgboost_rank_weights,
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


def test_rank_weights_fail_on_empty_train_or_test() -> None:
    panel = pd.concat(
        [
            _bars([10.0, 11.0, 12.0]).assign(symbol="A").reset_index().set_index(["symbol", "eob"]),
            _bars([10.0, 9.0, 8.0]).assign(symbol="B").reset_index().set_index(["symbol", "eob"]),
        ]
    ).sort_index()

    with pytest.raises(ValueError, match="train and test"):
        xgboost_rank_weights(panel, split_date="2020-01-01", horizon=1, top_n=1)


def test_rank_scores_to_weights_selects_top_n_and_normalizes() -> None:
    index = pd.date_range("2024-01-01", periods=5, name="eob")
    score = pd.DataFrame({"A": [0, 1, 3, 3, 3], "B": [0, 3, 1, 1, 1]}, index=index)
    close = pd.DataFrame({"A": [10, 10, 11, 12, 13], "B": [10, 11, 12, 13, 14]}, index=index)

    weights = rank_scores_to_weights(score, close, top_n=1, vol_lookback=2)

    assert weights.iloc[-1]["A"] == pytest.approx(1.0)
    assert weights.iloc[-1]["B"] == pytest.approx(0.0)


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


def test_xgboost_rank_weights_purges_forward_label_window_before_split(monkeypatch) -> None:
    dates = pd.date_range("2024-01-01", periods=12, name="eob")
    symbols = ["A", "B"]
    index = pd.MultiIndex.from_product([symbols, dates], names=["symbol", "eob"])
    features = pd.DataFrame({"feature": range(len(index))}, index=index, dtype=float)
    labels = pd.Series(0.5, index=index, name="rank_label")
    captured = {}

    class FakeRegressor:
        def __init__(self, **kwargs) -> None:
            pass

        def fit(self, train_x, train_y) -> None:
            captured["train_dates"] = train_x.index.get_level_values("eob").unique()

        def predict(self, test_x):
            captured["test_dates"] = test_x.index.get_level_values("eob").unique()
            return [0.5] * len(test_x)

    def fake_rank_scores_to_weights(score_df, close, top_n=2, vol_lookback=60):
        return pd.DataFrame(0.0, index=score_df.index, columns=score_df.columns)

    panel = pd.DataFrame({"close": 1.0}, index=index)
    monkeypatch.setattr(ml_rank, "make_cross_sectional_features", lambda panel: features)
    monkeypatch.setattr(ml_rank, "cross_sectional_rank_labels", lambda panel, horizon: labels)
    monkeypatch.setattr(ml_rank, "XGBRegressor", FakeRegressor)
    monkeypatch.setattr(ml_rank, "rank_scores_to_weights", fake_rank_scores_to_weights)

    xgboost_rank_weights(panel, split_date="2024-01-09", horizon=3, top_n=1)

    assert captured["train_dates"].max() == pd.Timestamp("2024-01-05")
    assert captured["test_dates"].min() == pd.Timestamp("2024-01-09")
