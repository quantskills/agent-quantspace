from __future__ import annotations

import numpy as np
import pandas as pd

import strategies.time_series.workflows.run_demo as demo


def test_run_demo_reads_standard_panel_and_executes_target_weights(monkeypatch) -> None:
    dates = pd.date_range("2024-01-01", periods=10, name="eob")
    symbol = "SHSE.510300"
    bars = pd.DataFrame(
        {
            "open": np.arange(10.0, 20.0),
            "high": np.arange(11.0, 21.0),
            "low": np.arange(9.0, 19.0),
            "close": np.arange(10.0, 20.0),
            "volume": 1000.0,
        },
        index=dates,
    )
    panel = pd.concat({symbol: bars}, names=["symbol", "eob"])

    class MemoryReader:
        def __init__(self) -> None:
            self.calls: list[tuple[list[str], str]] = []

        def read_symbols(self, symbols: list[str], frequency: str = "1d") -> pd.DataFrame:
            self.calls.append((symbols, frequency))
            return panel

    class FakeLabelMaker:
        def __init__(self, **kwargs) -> None:
            pass

        def generate_labels(self) -> pd.DataFrame:
            return pd.DataFrame({"state": [1, 0, -1, 1, 0, -1, 1, 0, -1, 1]}, index=dates)

    class FakeClassifier:
        def __init__(self, **kwargs) -> None:
            pass

        def fit(self, features: pd.DataFrame, labels: pd.Series) -> None:
            assert len(features) == len(labels) == 7

        def predict(self, features: pd.DataFrame) -> np.ndarray:
            assert len(features) == 3
            return np.array([1.0, -1.0, 1.0])

    monkeypatch.setattr(
        demo,
        "make_price_volume_features",
        lambda frame, diff_lookback: pd.DataFrame({"feature": range(10)}, index=dates),
    )
    monkeypatch.setattr(demo, "TripleBarrierLabelMaker", FakeLabelMaker)
    monkeypatch.setattr(demo, "LogisticRegression", FakeClassifier)
    reader = MemoryReader()

    result = demo.run_demo(data_reader=reader, symbol=symbol)

    assert reader.calls == [([symbol], "1d")]
    assert result.executed_weights.columns.tolist() == [symbol]
    assert not result.result_df.empty
