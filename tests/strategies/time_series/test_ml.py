from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import strategies.time_series.ml as ts_ml
from strategies.time_series.ml import (
    class_probability,
    probability_spread_weights,
    xgboost_triple_barrier_weights,
)


def test_probability_spread_weights_require_both_classes() -> None:
    probabilities = np.array([[0.7, 0.1, 0.2], [0.1, 0.1, 0.8]])
    index = pd.date_range("2024-01-01", periods=2, name="eob")

    weights = probability_spread_weights(
        probabilities,
        classes=np.array([0, 1, 2]),
        index=index,
        symbol="CFFEX.IF99",
        threshold=0.15,
    )

    assert weights["CFFEX.IF99"].tolist() == [-1.0, 1.0]

    with pytest.raises(ValueError, match="required encoded label"):
        probability_spread_weights(
            probabilities[:, :2],
            classes=np.array([1, 2]),
            index=index,
            symbol="CFFEX.IF99",
        )


def test_class_probability_extracts_requested_column() -> None:
    probabilities = np.array([[0.2, 0.3, 0.5], [0.6, 0.3, 0.1]])

    result = class_probability(probabilities, classes=np.array([0, 1, 2]), encoded_label=2)

    assert result.tolist() == [0.5, 0.1]


def test_xgboost_triple_barrier_weights_purges_label_window_before_split(monkeypatch) -> None:
    dates = pd.date_range("2024-01-01", periods=12, name="eob")
    features = pd.DataFrame({"feature": range(len(dates))}, index=dates, dtype=float)
    labels = pd.DataFrame({"state": [1, -1, 0, 1, -1, 0, 1, -1, 0, 1, -1, 0]}, index=dates)
    captured = {}

    class FakeLabelMaker:
        def __init__(self, **kwargs) -> None:
            pass

        def generate_labels(self):
            return labels

    class FakeClassifier:
        classes_ = np.array([0, 1, 2])

        def __init__(self, **kwargs) -> None:
            pass

        def fit(self, train_x, train_y) -> None:
            captured["train_dates"] = train_x.index

        def predict_proba(self, test_x):
            captured["test_dates"] = test_x.index
            return np.tile(np.array([[0.2, 0.6, 0.2]]), (len(test_x), 1))

    monkeypatch.setattr(ts_ml, "make_price_volume_features", lambda bars, diff_lookback: features)
    monkeypatch.setattr(ts_ml, "TripleBarrierLabelMaker", FakeLabelMaker)
    monkeypatch.setattr(ts_ml, "XGBClassifier", FakeClassifier)
    bars = pd.DataFrame(
        {
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
        },
        index=dates,
    )

    xgboost_triple_barrier_weights(
        bars,
        symbol="CFFEX.IF99",
        split_date="2024-01-09",
        label_t_limit=3,
    )

    assert captured["train_dates"].max() == pd.Timestamp("2024-01-05")
    assert captured["test_dates"].min() == pd.Timestamp("2024-01-09")
