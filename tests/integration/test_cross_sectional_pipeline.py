from __future__ import annotations

from scripts.generate_sample_data import generate_sample_data
from skills.store.data_manager import DataManager
from strategies.cross_sectional.factors import momentum_score, volatility_score
from strategies.cross_sectional.modular_backtester import ModularBacktester


def test_cross_sectional_public_demo_pipeline_runs(tmp_path) -> None:
    generate_sample_data(tmp_path)
    panel = DataManager(data_root=str(tmp_path)).load_pool_data("sample_etf_rotation")
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
