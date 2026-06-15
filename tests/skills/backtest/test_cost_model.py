from __future__ import annotations

import pandas as pd
import pytest

from skills.backtest.cost_model import (
    cost_bp_for_trigger_time,
    cost_layer_for_trigger_time,
    single_T_pnl_bp,
)


def test_cost_layer_for_trigger_time_maps_cn_session_windows() -> None:
    assert cost_layer_for_trigger_time(pd.Timestamp("2024-01-01 09:35")) == "worst"
    assert cost_layer_for_trigger_time(pd.Timestamp("2024-01-01 14:50")) == "tight"
    assert cost_bp_for_trigger_time(pd.Timestamp("2024-01-01 14:50")) == 16


def test_cost_layer_rejects_outside_session_time() -> None:
    with pytest.raises(ValueError, match="outside CN session"):
        cost_layer_for_trigger_time(pd.Timestamp("2024-01-01 12:00"))


def test_single_t_pnl_bp_subtracts_cost() -> None:
    gross, net = single_T_pnl_bp(sell_price=10.0, buyback_price=9.9, cost_bp=5.0)

    assert gross == pytest.approx(100.0)
    assert net == pytest.approx(95.0)
