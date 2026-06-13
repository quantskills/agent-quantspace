from __future__ import annotations

from pathlib import Path

from scripts.run_strategy_reports import generate_reports


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
