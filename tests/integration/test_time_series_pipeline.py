from __future__ import annotations

from pathlib import Path

import pandas as pd

from skills.backtest import VectorBacktester
from skills.compute.label_maker import TripleBarrierLabelMaker


def test_time_series_public_workflow_runs_with_triple_barrier_labels() -> None:
    index = pd.date_range("2024-01-01", periods=50, freq="D", name="eob")
    close = pd.Series(range(100, 150), index=index, dtype=float)
    bars = pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000,
        },
        index=index,
    )
    labels = TripleBarrierLabelMaker(data=bars, L=3, pt_sl=0.5, t_limit=5).generate_labels()
    weights = labels["state"].map({1: 1.0, 0: 0.0, -1: -1.0}).to_frame("SHSE.510300")
    panel = bars.copy()
    panel["symbol"] = "SHSE.510300"
    panel = panel.reset_index().set_index(["symbol", "eob"])

    result = VectorBacktester(
        panel,
        trade_at="close",
        signal_lag=1,
        commission=0.0002,
        slippage_bp=2.0,
    ).run(weights)

    assert not result.result_df.empty
    assert "total_return" in result.metrics


def test_time_series_workflow_documents_triple_barrier_only() -> None:
    root = Path(__file__).resolve().parents[2]
    strategy_doc = (root / "strategies/time_series/STRATEGY.md").read_text()
    demo_script = (root / "scripts/run_time_series_demo.py").read_text()
    combined = strategy_doc + "\n" + demo_script

    assert "TripleBarrierLabelMaker" in combined
    assert "VectorBacktester" in combined
    assert "ForwardReturnLabelMaker" not in combined
    assert "forward-return" not in combined.lower()
    assert "g" + "mm" not in combined.lower()
