from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import scripts.run_strategy_reports as report_script
from scripts.run_strategy_reports import generate_reports

_SLUGS = {
    "csi300_if_ma10_atr_reversion",
    "csi300_if_xgboost_triple_barrier",
    "futures_cross_sectional_reversal",
    "futures_xgboost_rank",
}


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
    assert "return_mode" not in captured_kwargs


def test_strategy_report_set_includes_rule_and_ml_examples(
    tmp_path: Path,
    strategy_report_data_root: Path,
) -> None:
    output_dir = tmp_path / "strategy_examples"
    unrelated = output_dir / "research_notes.md"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep", encoding="utf-8")
    report_paths = generate_reports(
        data_root=strategy_report_data_root,
        report_dir=output_dir,
    )

    slugs = {path.parent.name for path in report_paths}
    assert slugs == _SLUGS
    assert all(path.name == "index.html" for path in report_paths)
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
    assert chart_names == {f"{slug}_performance.png" for slug in _SLUGS}
    for path in report_paths:
        slug = path.parent.name
        report = path.read_text(encoding="utf-8")
        assert "data:image/png;base64," in report
        assert (output_dir / f"{slug}_performance.png").is_file()
        assert (path.parent / "params.json").is_file()
        assert report.index("<h2>研究问题</h2>") < report.index("<h2>证据与指标</h2>")
        assert report.index("<h2>证据与指标</h2>") < report.index("<h2>图表</h2>")
        assert 'href="../../catalog.html"' in report
    assert unrelated.read_text(encoding="utf-8") == "keep"
    catalog = (tmp_path / "catalog.html").read_text(encoding="utf-8")
    assert "public_example" in catalog
    assert "strategy_examples/futures_cross_sectional_reversal/index.html" in catalog
