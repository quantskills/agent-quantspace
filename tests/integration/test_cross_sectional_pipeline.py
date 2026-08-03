from __future__ import annotations

from scripts.generate_sample_data import ETF_SYMBOLS, generate_sample_data
from skills.store.data_manager import DataManager
from skills.strategy.cross_sectional import ModularBacktester
from strategies.cross_sectional.factors import momentum_score, volatility_score


def test_cross_sectional_public_demo_pipeline_runs(tmp_path) -> None:
    generate_sample_data(tmp_path)
    panel = DataManager(data_root=str(tmp_path)).read_symbols(ETF_SYMBOLS, frequency="1d")
    bt = ModularBacktester(
        data=panel,
        factor_configs=[
            {
                "func": momentum_score,
                "kwargs": {"lookback": 20},
                "name": "momentum",
                "direction": 1,
            },
            {
                "func": volatility_score,
                "kwargs": {"lookback": 20},
                "name": "low_vol",
                "direction": 1,
            },
        ],
        top_pct=0.5,
        rebalance_freq=5,
        slippage_bp=2.0,
    )

    result = bt.run()

    assert not result.empty
    assert "total_return" in bt.metrics
    assert bt.executed_weights is not None
