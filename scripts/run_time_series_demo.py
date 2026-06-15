"""Run the public time-series ML demo on local daily Parquet data."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.backtest import VectorBacktester  # noqa: E402
from skills.compute.label_maker import TripleBarrierLabelMaker  # noqa: E402
from skills.store.data_manager import DataManager  # noqa: E402
from strategies.time_series.features import make_price_volume_features  # noqa: E402

DEFAULT_TS_SYMBOL = "SHSE.510300"
DEFAULT_FREQUENCY = "1d"


def main() -> None:
    bars = DataManager().read_symbol(DEFAULT_TS_SYMBOL, frequency=DEFAULT_FREQUENCY)
    bars.index = pd.to_datetime(bars.index)

    features = make_price_volume_features(bars, diff_lookback=3)
    labels = TripleBarrierLabelMaker(
        data=bars,
        L=5,
        pt_sl=1.0,
        t_limit=10,
    ).generate_labels()

    dataset = features.join(labels[["state"]].rename(columns={"state": "label"})).dropna()
    split = int(len(dataset) * 0.7)
    train = dataset.iloc[:split]
    test = dataset.iloc[split:]

    model = LogisticRegression(max_iter=1000, multi_class="auto")
    model.fit(train.drop(columns=["label"]), train["label"])

    probabilities = model.predict_proba(test.drop(columns=["label"]))
    predictions = pd.DataFrame(
        {
            "prediction_label": model.predict(test.drop(columns=["label"])),
            "prediction_score": probabilities.max(axis=1),
        },
        index=test.index,
    )
    weights = predictions["prediction_label"].map({1: 1.0, 0: 0.0, -1: -1.0}).to_frame(
        DEFAULT_TS_SYMBOL
    )
    panel = bars.copy()
    panel["symbol"] = DEFAULT_TS_SYMBOL
    panel = panel.reset_index().set_index(["symbol", "eob"])
    result = VectorBacktester(
        panel,
        trade_at="close",
        signal_lag=1,
        commission=0.0002,
        slippage_bp=2.0,
    ).run(weights)

    print("Time-series demo metrics:")
    for key, value in result.metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
