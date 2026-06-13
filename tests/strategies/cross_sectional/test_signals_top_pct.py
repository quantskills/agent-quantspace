from __future__ import annotations

import pandas as pd
import pytest

from strategies.cross_sectional.signals_base import StrategyContext
from strategies.cross_sectional.signals_top_pct import TopPctStrategy
from tests.fixtures.market_data import make_panel


def test_top_pct_strategy_selects_and_equal_weights_top_names() -> None:
    panel = make_panel(symbols=("AAA", "BBB", "CCC"), periods=3)
    dates = panel.index.get_level_values("eob").unique()
    factor_df = panel.copy()
    factor_pivots = {
        "score": pd.DataFrame(
            {
                "AAA": [1.0, 1.0, 1.0],
                "BBB": [3.0, 3.0, 3.0],
                "CCC": [2.0, 2.0, 2.0],
            },
            index=dates,
        )
    }
    context = StrategyContext(
        data=panel,
        factor_configs=[{"func": lambda group: group["close"], "name": "score", "direction": 1}],
        exit_filters=[],
        top_pct=1 / 3,
        weight_method="equal",
        rebalance_freq=1,
        vol_target=None,
        exposure_policy="keep_cash",
        defensive_symbols=[],
        execution_returns=panel["close"].unstack("symbol").pct_change(fill_method=None),
        signal_lag=1,
    )

    result = TopPctStrategy().generate(factor_df, factor_pivots, context)

    assert result.signal_weights["BBB"].eq(1.0).all()
    assert result.signal_weights[["AAA", "CCC"]].sum().sum() == 0.0
    assert result.signal_df["strategy__target_weight"].max() == pytest.approx(1.0)
