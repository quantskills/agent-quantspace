from __future__ import annotations

import pandas as pd
import pytest

from skills.backtest.overlay_metrics import (
    max_drawdown,
    overlay_alpha,
    overlay_maxdd,
    overlay_sharpe,
    overlay_winrate,
    regime_alpha_table,
    summarize_overlay_metrics,
    trades_per_year,
)


def test_overlay_metrics_summarize_trade_stream() -> None:
    index = pd.date_range("2024-01-01", periods=5)
    trades = pd.DataFrame(
        {
            "trigger_date": [index[0], index[-1]],
            "net_bp": [20.0, -10.0],
        }
    )
    overlay = pd.Series([0.001, -0.002, 0.003, 0.0, 0.001], index=index)
    buy_hold = pd.Series([0.0005, 0.0005, -0.0005, 0.0002, 0.0003], index=index)

    summary = summarize_overlay_metrics(trades, overlay, buy_hold)

    assert summary["winrate_net"] == 0.5
    assert summary["trades_per_year"] == pytest.approx(trades_per_year(trades))
    assert summary["max_dd_overlay"] == pytest.approx(overlay_maxdd(overlay)[0])
    assert overlay_alpha(overlay, buy_hold) != 0.0
    assert overlay_sharpe(overlay) != 0.0
    assert max_drawdown((1 + overlay).cumprod()) >= 0.0


def test_regime_alpha_table_uses_requested_slices() -> None:
    index = pd.date_range("2024-01-01", periods=6)
    overlay = pd.Series([0.001, 0.002, -0.001, 0.0, 0.001, 0.002], index=index)
    benchmark = pd.Series([0.0, 0.001, 0.0, -0.001, 0.0, 0.001], index=index)

    table = regime_alpha_table(
        overlay,
        benchmark,
        {"first": (index[0], index[2]), "second": (index[3], index[-1])},
    )

    assert list(table.index) == ["first", "second"]
    assert table.loc["first", "n_days"] == 3


def test_overlay_winrate_empty_trades_is_zero() -> None:
    assert overlay_winrate(pd.DataFrame(columns=["net_bp"])) == 0.0
