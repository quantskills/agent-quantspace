from __future__ import annotations

import importlib

import pandas as pd
import pytest


def _panel() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=4, name="eob")
    frames = []
    for symbol, prices in {
        "AAA": [100.0, 110.0, 121.0, 133.1],
        "BBB": [100.0, 100.0, 100.0, 100.0],
    }.items():
        close = pd.Series(prices, index=dates)
        bars = pd.DataFrame(
            {
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1000,
                "symbol": symbol,
            }
        )
        frames.append(bars.reset_index().set_index(["symbol", "eob"]))
    return pd.concat(frames).sort_index()


def test_vector_backtester_runs_from_weight_matrix() -> None:
    from skills.backtest import VectorBacktester, activity_metrics, annual_return_metrics

    weights = pd.DataFrame(
        {
            "AAA": [0.0, 1.0, 1.0, 0.0],
            "BBB": [0.0, 0.0, 0.0, 0.0],
        },
        index=pd.date_range("2024-01-01", periods=4, name="eob"),
    )

    result = VectorBacktester(
        data=_panel(),
        trade_at="close",
        signal_lag=0,
        commission=0.0,
        slippage_bp=0.0,
    ).run(weights)

    assert result.executed_weights.equals(weights)
    assert result.result_df["return"].tolist() == pytest.approx([0.1, 0.1])
    assert result.metrics["total_return"] == pytest.approx(0.21)
    assert activity_metrics(result.result_df)["trade_days"] == 1.0
    assert "2024_return" in annual_return_metrics(result.result_df)


def test_vector_backtester_backward_mode_requires_explicit_opt_in() -> None:
    from skills.backtest import VectorBacktester

    weights = pd.DataFrame(
        {
            "AAA": [0.0, 1.0, 1.0, 0.0],
            "BBB": [0.0, 0.0, 0.0, 0.0],
        },
        index=pd.date_range("2024-01-01", periods=4, name="eob"),
    )

    result = VectorBacktester(
        data=_panel(),
        trade_at="close",
        signal_lag=0,
        commission=0.0,
        slippage_bp=0.0,
        return_mode="backward",
    ).run(weights)

    assert result.result_df["return"].tolist() == pytest.approx([0.1, 0.1, 0.0])


def test_vector_backtester_requires_explicit_costs() -> None:
    from skills.backtest import VectorBacktester

    with pytest.raises(ValueError, match="commission and slippage_bp"):
        VectorBacktester(data=_panel(), commission=None, slippage_bp=0.0)
    with pytest.raises(ValueError, match="commission and slippage_bp"):
        VectorBacktester(data=_panel(), commission=0.0, slippage_bp=None)


def test_removed_legacy_backtest_modules_are_not_importable() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("strategies.cross_sectional.execution")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("strategies.time_series.backtester")
