from __future__ import annotations

import pandas as pd


def test_strategy_html_writes_report_and_index(tmp_path) -> None:
    from skills.report.strategy_markdown import (
        StrategyReport,
        write_strategy_index,
        write_strategy_report,
    )

    result_df = pd.DataFrame(
        {
            "return": [0.01, -0.02],
            "raw_return": [0.01, -0.02],
            "cum_return": [0.01, -0.0102],
            "drawdown": [0.0, -0.02],
            "turnover": [1.0, 0.0],
        },
        index=pd.date_range("2024-01-01", periods=2, name="eob"),
    )
    report = StrategyReport(
        slug="demo",
        title="Demo Strategy",
        domain="time_series",
        strategy_type="Rule-based",
        label="none",
        description="Demo description.",
        metrics={"sharpe_ratio": 1.5, "total_return": -0.0102, "max_drawdown": 0.02},
        result_df=result_df,
        notes=["Uses vector weights."],
    )

    report_path = write_strategy_report(report, tmp_path)
    index_path = write_strategy_index([report], tmp_path)

    content = report_path.read_text(encoding="utf-8")
    assert report_path.name == "demo.html"
    assert "data:image/png;base64," in content
    assert "<h2>Performance Chart</h2>" in content
    assert "<h2>Metrics</h2>" in content
    assert 'href="../catalog.html"' in content
    assert "返回目录" in content
    assert (tmp_path / "demo_performance.png").is_file()
    assert not (tmp_path / "demo.md").exists()

    index_content = index_path.read_text(encoding="utf-8")
    assert index_path.name == "index.html"
    assert 'href="demo.html"' in index_content
    assert "Demo Strategy" in index_content
    assert "listed-fund and futures bars" in index_content
    assert "uv run python -m scripts.run_strategy_reports" in index_content
    assert "python scripts/" not in index_content
    assert not (tmp_path / "README.md").exists()
