from __future__ import annotations

import pandas as pd
import pytest

from skills.backtest import VectorBacktester
from skills.strategy.time_series import TimeSeriesBacktester, signal_to_single_asset_weights


def test_signal_to_single_asset_weights_maps_signal_to_symbol_column() -> None:
    signal = pd.Series(
        [1.0, 0.0, -1.0],
        index=pd.DatetimeIndex(["2026-01-02", "2026-01-03", "2026-01-04"], name="eob"),
    )

    weights = signal_to_single_asset_weights(signal, symbol="SHSE.510300")

    expected = pd.DataFrame({"SHSE.510300": [1.0, 0.0, -1.0]}, index=signal.index)
    pd.testing.assert_frame_equal(weights, expected)


def test_signal_to_single_asset_weights_fills_clips_and_scales() -> None:
    signal = pd.Series(
        [float("nan"), 1.5, -2.0, -0.5],
        index=pd.date_range("2026-01-02", periods=4, name="eob"),
    )

    weights = signal_to_single_asset_weights(
        signal,
        symbol="SHSE.510300",
        exposure=0.4,
    )

    expected = pd.DataFrame(
        {"SHSE.510300": [0.0, 0.4, -0.4, -0.2]},
        index=signal.index,
    )
    pd.testing.assert_frame_equal(weights, expected)


def test_time_series_backtester_delegates_execution_to_vector_backtester() -> None:
    index = pd.date_range("2024-01-01", periods=5, freq="D", name="eob")
    frame = pd.DataFrame(
        {
            "open": [10.0, 11.0, 12.0, 11.0, 13.0],
            "high": [11.0, 12.0, 13.0, 12.0, 14.0],
            "low": [9.0, 10.0, 11.0, 10.0, 12.0],
            "close": [10.0, 12.0, 11.0, 13.0, 14.0],
            "prediction_label": [0, 1, 1, -1, -1],
            "prediction_score": [0.0, 1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )

    backtester = TimeSeriesBacktester(
        frame,
        symbol="AAA",
        commission=0.0,
        slippage=0.0,
        delay=0,
    )
    backtester.run_backtest()

    panel = frame[["open", "high", "low", "close"]].copy()
    panel["symbol"] = "AAA"
    panel = panel.reset_index().set_index(["symbol", "eob"]).sort_index()
    target_weights = pd.DataFrame({"AAA": backtester.df["position"]}, index=index)
    expected = VectorBacktester(
        panel,
        trade_at="close",
        signal_lag=0,
        commission=0.0,
        slippage_bp=0.0,
        return_mode="forward",
    ).run(target_weights)

    pd.testing.assert_frame_equal(backtester.result_df, expected.result_df)
    assert backtester.metrics == expected.metrics


def test_time_series_backtester_requires_prediction_columns() -> None:
    with pytest.raises(ValueError, match="prediction columns"):
        TimeSeriesBacktester(pd.DataFrame({"prediction_label": [1]}), symbol="AAA")
