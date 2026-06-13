from __future__ import annotations

from strategies.cross_sectional.factors import momentum_score
from strategies.cross_sectional.modular_backtester import ModularBacktester
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
