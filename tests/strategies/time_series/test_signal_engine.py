from __future__ import annotations

import pandas as pd

from strategies.time_series.signal_engine import SignalEngine


class FakeFeature:
    def __init__(self) -> None:
        self.values = pd.DataFrame()

    def set_data(self, data: pd.DataFrame) -> None:
        self.data = data

    def cal_values(self) -> pd.DataFrame:
        self.values = pd.DataFrame({"feature": [1.0]}, index=[self.data.index[-1]])
        return self.values


class FakePredictor:
    def __init__(self, model_path, train_df) -> None:
        self.train_df = train_df

    def predict(self, values: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"prediction_label": [1], "prediction_score": [0.9]}, index=values.index)


def test_signal_engine_emits_only_changed_target_position(tmp_path, monkeypatch) -> None:
    train_path = tmp_path / "train.parquet"
    pd.DataFrame(
        {
            "eob": pd.date_range("2024-01-01", periods=2),
            "feature": [0.1, 0.2],
        }
    ).to_parquet(train_path)
    monkeypatch.setattr("strategies.time_series.signal_engine.ModelPredictor", FakePredictor)

    engine = SignalEngine(FakeFeature(), str(train_path), "model")

    first = engine.feed_bar({"eob": "2024-01-03", "close": 100.0})
    second = engine.feed_bar({"eob": "2024-01-04", "close": 101.0})
    engine.reset()

    assert first == 1
    assert second is None
    assert len(engine.bar_buffer) == 0
