from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import scripts.run_strategy_reports as report_script
from scripts.run_strategy_reports import generate_reports


def test_report_backtests_use_next_close_execution_for_eod_signals(monkeypatch) -> None:
    captured_kwargs = {}

    class FakeVectorBacktester:
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

        def run(self, weights):
            return SimpleNamespace(executed_weights=weights, result_df=pd.DataFrame(), metrics={})

    monkeypatch.setattr(report_script, "VectorBacktester", FakeVectorBacktester)
    dates = pd.date_range("2024-01-01", periods=3, name="eob")
    close = pd.Series([100.0, 101.0, 102.0], index=dates)
    panel = (
        pd.DataFrame(
            {
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1000.0,
                "symbol": "AAA",
            }
        )
        .reset_index()
        .set_index(["symbol", "eob"])
    )
    weights = pd.DataFrame({"AAA": [0.0, 1.0, 0.0]}, index=dates)

    report_script._run_vector_backtest(panel, weights, start_date="2024-01-01")

    assert captured_kwargs["signal_lag"] == 0
    assert captured_kwargs["return_mode"] == "forward"


def test_strategy_report_set_includes_rule_and_ml_examples(tmp_path: Path) -> None:
    output_dir = tmp_path / "strategy_examples"
    report_paths = generate_reports(report_dir=output_dir)

    names = {path.name for path in report_paths}
    assert names == {
        "README.md",
        "csi300_if_ma10_atr_reversion.md",
        "csi300_if_xgboost_triple_barrier.md",
        "futures_cross_sectional_reversal.md",
        "futures_xgboost_rank.md",
    }
    combined = "\n".join(path.read_text(encoding="utf-8") for path in report_paths)
    assert "CFFEX.IF99" in combined
    assert "MA10" in combined
    assert "probability spread" in combined
    assert "trade_days" in combined
    assert "triple-barrier" in combined
    assert "rank label" in combined
    assert "MA80" not in combined
    assert "inverse-vol basket" not in combined.lower()

    chart_names = {path.name for path in output_dir.glob("*_performance.png")}
    assert chart_names == {
        "csi300_if_ma10_atr_reversion_performance.png",
        "csi300_if_xgboost_triple_barrier_performance.png",
        "futures_cross_sectional_reversal_performance.png",
        "futures_xgboost_rank_performance.png",
    }
    for path in report_paths:
        if path.name == "README.md":
            continue
        chart_name = f"{path.stem}_performance.png"
        report = path.read_text(encoding="utf-8")
        assert f"![Performance Chart]({chart_name})" in report
        assert report.index("## Summary") < report.index("## Performance Chart")
        assert report.index("## Performance Chart") < report.index("## Metrics")
        assert report.index("## Metrics") < report.index("## Notes")
