from __future__ import annotations

import pandas as pd
import pytest

from skills.analyze.backtest import VectorBacktester
from tests.fixtures.market_data import make_ohlcv


def test_vector_backtest_known_no_cost_path() -> None:
    bars = make_ohlcv([100.0, 110.0, 121.0], symbol="AAA")
    weights = pd.DataFrame({"AAA": [1.0, 1.0, 1.0]}, index=pd.date_range("2024-01-01", periods=3, name="eob"))

    result = VectorBacktester(
        bars,
        signal_lag=0,
        commission=0.0,
        slippage_bp=0.0,
    ).run(weights)

    assert result.result_df["return"].tolist() == pytest.approx([0.1, 0.1])
    assert result.result_df["equity"].iloc[-1] == pytest.approx(1.21)
    assert result.metrics["total_return"] == pytest.approx(0.21)


def test_vector_backtest_known_cost_path() -> None:
    bars = make_ohlcv([100.0, 110.0, 121.0], symbol="AAA")
    weights = pd.DataFrame({"AAA": [1.0, 0.0, 1.0]}, index=pd.date_range("2024-01-01", periods=3, name="eob"))

    result = VectorBacktester(
        bars,
        signal_lag=0,
        commission=0.001,
        slippage_bp=10.0,
    ).run(weights)

    assert result.result_df["turnover"].tolist() == pytest.approx([1.0, 1.0])
    assert result.result_df["transaction_cost"].tolist() == pytest.approx([0.002, 0.002])
