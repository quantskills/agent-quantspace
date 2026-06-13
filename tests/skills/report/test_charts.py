from __future__ import annotations

import pandas as pd

from skills.report.charts import plot_backtest_performance, plot_equity_curve, plot_factor_ranking


def _is_png(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n")


def test_plot_backtest_performance_returns_png_bytes() -> None:
    result_df = pd.DataFrame(
        {"return": [0.01, -0.01], "equity": [1.01, 0.9999], "drawdown": [0.0, -0.01]},
        index=pd.date_range("2024-01-01", periods=2),
    )

    assert _is_png(plot_backtest_performance(result_df))


def test_plot_equity_curve_returns_png_bytes() -> None:
    assert _is_png(plot_equity_curve(pd.Series([0.01, 0.02], index=pd.date_range("2024-01-01", periods=2))))


def test_plot_factor_ranking_returns_png_bytes() -> None:
    ranking = pd.DataFrame({"indicator": ["a", "b"], "IC_IR": [1.0, -0.5]})

    assert _is_png(plot_factor_ranking(ranking))
