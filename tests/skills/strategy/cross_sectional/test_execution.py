from __future__ import annotations

import pandas as pd
import pytest

from skills.backtest import VectorBacktester
from skills.strategy.cross_sectional.execution import SignalBacktestExecutor
from tests.fixtures.market_data import make_panel


def _signal_frame(weights: pd.DataFrame) -> pd.DataFrame:
    target = weights.stack().rename("strategy__target_weight")
    target.index.names = ["eob", "symbol"]
    return target.reorder_levels(["symbol", "eob"]).sort_index().to_frame()


def test_signal_executor_delegates_target_weights_to_vector_backtester() -> None:
    panel = make_panel(symbols=("AAA", "BBB"), periods=12)
    dates = panel.index.get_level_values("eob").unique()
    weights = pd.DataFrame({"AAA": 0.75, "BBB": 0.25}, index=dates)

    executor = SignalBacktestExecutor(
        data=panel,
        signal_lag=1,
        commission=0.0002,
        slippage_bp=2.0,
        return_mode="forward",
    )
    result = executor.run(_signal_frame(weights))
    direct = VectorBacktester(
        data=panel,
        signal_lag=1,
        commission=0.0002,
        slippage_bp=2.0,
        return_mode="forward",
    ).run(weights)

    pd.testing.assert_frame_equal(result.executed_weights, direct.executed_weights)
    pd.testing.assert_frame_equal(result.result_df, direct.result_df)
    assert executor.metrics == direct.metrics


def test_signal_executor_rejects_non_contract_frames() -> None:
    panel = make_panel(symbols=("AAA",), periods=4)
    executor = SignalBacktestExecutor(
        data=panel,
        commission=0.0,
        slippage_bp=0.0,
    )

    with pytest.raises(ValueError, match="strategy__target_weight"):
        executor.run(pd.DataFrame(index=panel.index))

    bad_index = panel.rename_axis(index=["asset", "date"])
    bad_frame = bad_index.assign(strategy__target_weight=1.0)
    with pytest.raises(ValueError, match="index names"):
        executor.run(bad_frame)
