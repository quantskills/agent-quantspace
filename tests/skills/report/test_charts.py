from __future__ import annotations

import pandas as pd

from skills.report.charts import (
    plot_backtest_performance,
    plot_equity_comparison,
    plot_equity_curve,
    plot_factor_diagnostics,
    plot_factor_ranking,
    plot_factor_weight_history,
    plot_horizon_ic,
    plot_ic_heatmap,
    plot_lagged_ic,
    plot_rebalance_comparison,
)


def _is_png(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n")


def test_plot_backtest_performance_returns_png_bytes() -> None:
    result_df = pd.DataFrame(
        {"return": [0.01, -0.01], "equity": [1.01, 0.9999], "drawdown": [0.0, -0.01]},
        index=pd.date_range("2024-01-01", periods=2),
    )

    assert _is_png(plot_backtest_performance(result_df))


def test_plot_equity_curve_returns_png_bytes() -> None:
    assert _is_png(
        plot_equity_curve(pd.Series([0.01, 0.02], index=pd.date_range("2024-01-01", periods=2)))
    )


def test_plot_factor_diagnostics_returns_png_bytes() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    ic = pd.Series([0.10, -0.05, 0.08, 0.02], index=index)
    group_returns = pd.DataFrame(
        {"G1": [-0.01, 0.00, 0.01, -0.01], "G2": [0.01, 0.02, -0.01, 0.01]},
        index=index,
    )
    turnover = pd.DataFrame({"G1": [0.0, 0.5, 0.0, 0.5], "G2": [0.0, 1.0, 0.0, 0.0]}, index=index)

    png = plot_factor_diagnostics(
        ic,
        {"IC_mean": 0.0375, "IC_IR": 0.5, "IC_>0": 0.75, "p_value": 0.2},
        group_returns,
        turnover,
        rolling_ir_window=2,
    )

    assert _is_png(png)


def test_plot_factor_ranking_returns_png_bytes() -> None:
    ranking = pd.DataFrame({"indicator": ["a", "b"], "IC_IR": [1.0, -0.5]})

    assert _is_png(plot_factor_ranking(ranking))


def test_multifactor_chart_helpers_return_png_bytes() -> None:
    dates = pd.bdate_range("2024-01-01", periods=4)
    summary_rows = []
    for factor in ["a", "b"]:
        for horizon in [1, 5, 10, 20]:
            for lag in [0, 1, 5]:
                summary_rows.append(
                    {
                        "factor": factor,
                        "segment": "calibration",
                        "horizon": horizon,
                        "lag": lag,
                        "ic_mean": 0.01 * horizon / (lag + 1),
                    }
                )
    summary = pd.DataFrame(summary_rows)
    correlation = pd.DataFrame([[1.0, 0.4], [0.4, 1.0]], index=["a", "b"], columns=["a", "b"])
    rebalance = pd.DataFrame(
        {
            "segment": ["calibration", "calibration"],
            "rebalance_days": [1, 5],
            "sharpe_ratio": [1.0, 1.2],
            "annual_turnover": [100.0, 30.0],
        }
    )
    factor_weights = pd.DataFrame(
        [
            {"method": "max_icir", "eob": date, "factor": factor, "weight": 0.5}
            for date in dates
            for factor in ["a", "b"]
        ]
    )
    equities = pd.DataFrame(
        [
            {"method": method, "eob": date, "equity": 1.0 + 0.01 * i}
            for method in ["equal_rank", "max_icir"]
            for i, date in enumerate(dates)
        ]
    )
    charts = [
        plot_horizon_ic(summary, factors=["a", "b"], segment="calibration"),
        plot_lagged_ic(summary, factors=["a", "b"], segment="calibration"),
        plot_ic_heatmap(correlation, annotate=True),
        plot_rebalance_comparison(rebalance, selected_days=5),
        plot_factor_weight_history(factor_weights),
        plot_equity_comparison(equities, start="2024-01-01", title="Comparison"),
    ]
    assert all(_is_png(chart) for chart in charts)
