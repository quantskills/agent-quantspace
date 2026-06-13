from __future__ import annotations

import pandas as pd

from skills.research.strategy_comparison import compare_strategies
from tests.fixtures.market_data import make_panel


def test_compare_strategies_passes_explicit_slippage_and_collects_metrics(monkeypatch) -> None:
    panel = make_panel(symbols=("AAA", "BBB", "CCC"), periods=8)
    seen_kwargs: list[dict] = []

    class FakeDataManager:
        def load_pool_data(self, pool):
            return panel

    class FakeBacktester:
        def __init__(self, **kwargs):
            seen_kwargs.append(kwargs)
            self.metrics = {
                "total_return": 0.1,
                "ann_return": 0.2,
                "max_drawdown": 0.03,
                "sharpe_ratio": 1.4,
                "calmar_ratio": 4.0,
            }

        def run(self):
            return pd.DataFrame()

    monkeypatch.setattr("skills.store.data_manager.DataManager", FakeDataManager)
    monkeypatch.setattr("strategies.cross_sectional.modular_backtester.ModularBacktester", FakeBacktester)

    result = compare_strategies(
        "demo",
        [{"name": "one", "factor_configs": [{"func": lambda group: group["close"]}]}],
        top_pct=0.5,
        commission=0.0002,
        slippage_bp=2.0,
    )

    assert result.loc[0, "strategy_name"] == "one"
    assert result.loc[0, "sharpe_ratio"] == 1.4
    assert seen_kwargs[0]["slippage_bp"] == 2.0
