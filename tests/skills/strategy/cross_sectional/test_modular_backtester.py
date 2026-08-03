from __future__ import annotations

import pandas as pd
import pytest

from skills.backtest import VectorBacktester
from skills.strategy.cross_sectional.modular_backtester import ModularBacktester
from strategies.cross_sectional.factors import momentum_score
from tests.fixtures.market_data import make_panel


def test_modular_backtester_runs_through_vector_backtester() -> None:
    panel = make_panel(symbols=("AAA", "BBB", "CCC"), periods=35)
    bt = ModularBacktester(
        data=panel,
        factor_configs=[
            {"func": momentum_score, "kwargs": {"lookback": 3}, "name": "mom", "direction": 1}
        ],
        top_pct=1 / 3,
        commission=0.0001,
        slippage_bp=1.0,
    )

    result = bt.run()

    assert not result.empty
    assert bt.signal_weights is not None
    assert bt.executed_weights is not None
    assert "sharpe_ratio" in bt.metrics

    direct = VectorBacktester(
        data=panel,
        signal_lag=1,
        commission=0.0001,
        slippage_bp=1.0,
        return_mode="forward",
    ).run(bt.signal_weights)
    pd.testing.assert_frame_equal(bt.executed_weights, direct.executed_weights)
    pd.testing.assert_frame_equal(bt.result_df, direct.result_df)
    assert bt.metrics == direct.metrics


def test_modular_backtester_requires_explicit_slippage() -> None:
    panel = make_panel(symbols=("AAA", "BBB"), periods=8)

    with pytest.raises(TypeError):
        ModularBacktester(
            data=panel,
            factor_configs=[{"func": momentum_score, "kwargs": {"lookback": 2}}],
        )


def test_modular_backtester_validates_return_mode() -> None:
    panel = make_panel(symbols=("AAA", "BBB"), periods=8)

    with pytest.raises(ValueError, match="return_mode"):
        ModularBacktester(
            data=panel,
            factor_configs=[{"func": momentum_score, "kwargs": {"lookback": 2}}],
            slippage_bp=0.0,
            return_mode="same_bar",
        )
