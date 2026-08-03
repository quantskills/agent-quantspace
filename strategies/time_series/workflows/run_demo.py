"""Run the public time-series ML demo on local daily Parquet data."""

from __future__ import annotations

import pandas as pd
from sklearn.linear_model import LogisticRegression

from skills.backtest import BacktestResult, VectorBacktester
from skills.compute.label_maker import TripleBarrierLabelMaker
from skills.store.data_manager import DataManager
from skills.strategy import MarketDataReader
from skills.strategy.time_series import signal_to_single_asset_weights
from strategies.time_series.features import make_price_volume_features

DEFAULT_TS_SYMBOL = "SHSE.510300"
DEFAULT_FREQUENCY = "1d"


def run_demo(
    *,
    data_reader: MarketDataReader | None = None,
    symbol: str = DEFAULT_TS_SYMBOL,
    frequency: str = DEFAULT_FREQUENCY,
) -> BacktestResult:
    """Build public ML weights and execute them with ``VectorBacktester``."""
    reader = data_reader or DataManager()
    panel = reader.read_symbols([symbol], frequency=frequency)
    bars = panel.xs(symbol, level="symbol").copy()
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

    model = LogisticRegression(max_iter=1000)
    model.fit(train.drop(columns=["label"]), train["label"])
    signal = pd.Series(
        model.predict(test.drop(columns=["label"])),
        index=test.index,
        dtype=float,
    )
    weights = signal_to_single_asset_weights(signal, symbol=symbol)

    return VectorBacktester(
        panel,
        trade_at="close",
        signal_lag=1,
        commission=0.0002,
        slippage_bp=2.0,
    ).run(weights)


def main() -> None:
    """Run the demo and print its metrics."""
    result = run_demo()
    print("Time-series demo metrics:")
    for key, value in result.metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
