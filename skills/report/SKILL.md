---
name: report
description: Use when tasks need complete HTML research reports, HTML dashboards, Markdown strategy example cards, PNG chart helpers, or files under the research reports directory.
---

# Report Skill

Render research outputs into self-contained HTML using Jinja2 templates and
matplotlib charts. Install with `uv sync --extra report`. Default output uses
`QUANTSPACE_REPORTS_ROOT` when set, otherwise the workspace `reports/` path.

Complete research archives are **HTML only**. Do not write them as Markdown or
PDF. Do not use a database. Other skills must not write HTML; they return
objects, and the caller fills `ResearchReport` then calls
`write_research_bundle`.

## Three output paths

| Path | Entry | Output | Use for |
|------|-------|--------|---------|
| Complete research archive | `ResearchReport` + `write_research_bundle` | `reports/<namespace>/<slug>/index.html` | Takeaway research document |
| Public example card | `StrategyReport` + `write_strategy_report` | `reports/strategy_examples/*.md` | Compact public demos |
| Dashboard preview | `ReportRenderer` + `factor_report` / `backtest_report` / `signal_digest` | one HTML file | Quick look, not an archive |

Charts are inlined as base64 data URIs via the `png_data_uri` Jinja filter.

## Complete research archive

```python
from skills.report import (
    ReportFigure,
    ReportTable,
    ResearchReport,
    charts,
    write_research_bundle,
    write_research_catalog,
)

equity_png = charts.plot_backtest_performance(result_df, title="Performance")
report = ResearchReport(
    namespace="lesson_09",
    slug="if_ma10_atr",
    title="IF MA10 + ATR",
    question="Does this rule beat buy-and-hold under the stated costs?",
    universe=["CFFEX.IF99"],
    frequency="1d",
    sample_start="2024-01-01",
    sample_end="2026-07-01",
    in_sample_end=None,
    out_of_sample_start=None,
    hypothesis="Close below MA10 enters; ATR stop only ratchets up.",
    method_notes=["Rule from strategies.time_series.rules."],
    execution={
        "trade_at": "close",
        "signal_lag": 1,
        "commission": 0.0002,
        "slippage_bp": 2.0,
        "return_mode": "forward",
    },
    metrics=execution.metrics,  # from VectorBacktester, do not invent numbers
    metrics_source="BacktestResult.metrics",
    figures=[ReportFigure(name="equity", caption="Equity and drawdown", png=equity_png)],
    tables=[],
    caveats=["Historical result only; not a live trading recommendation."],
    next_steps=["Add cost sensitivity."],
    reproduce_command="uv run python -m strategies.time_series.workflows.run_demo",
    visibility="private",
    domain="time_series",
)
study_dir = write_research_bundle(report)
write_research_catalog()
```

Directory contract:

```text
reports/<namespace>/<slug>/index.html
reports/<namespace>/<slug>/params.json
reports/catalog.html
reports/catalog.json
```

`index.html` is the human-readable nine-section report. `params.json` is the
catalog sidecar. `list_research_studies` only accepts folders that have both
files. CSV-only experiment folders are ignored. `write_research_bundle` does
not write the catalog; call `write_research_catalog` after a batch.

Required HTML sections: 研究问题, 数据与样本, 假设与方法, 执行约定,
证据与指标, 图表, 对照与稳健性, 限制与下一步, 复现与产物.
If there is no comparison or robustness evidence, section 7 still renders
`本报告未做`.

Hard rules:

- Fill `metrics` from `BacktestResult`, CSV, JSON, or `result_df`. Never invent Sharpe.
- `metrics_source` is required.
- `namespace` and `slug` are safe path segments only.
- Default `visibility="private"`. Do not git-add private studies.
- `visibility="public_example"` still writes `reports/<namespace>/<slug>/`, not `strategy_examples/`.
- Do not import `strategies/` from this skill.
- Do not export PDF.

## Dashboard preview

```python
from skills.report import ReportRenderer, charts

renderer = ReportRenderer()
ranking_png = charts.plot_factor_ranking(ranking_df, value_col="IC_IR")
html = renderer.render(
    "factor_report",
    {
        "title": "Macro universe — weekly factor screen",
        "namespace": "macro_weekly",
        "n": 5,
        "as_of": "2026-05-08",
        "ranking_chart": ranking_png,
        "ranking_html": ranking_df.to_html(),
    },
)
path = renderer.save(html, "macro_weekly_2026-05-08.html")
```

Pass a template name with or without `.html`. Relative output paths resolve
against `reports/`; absolute paths are respected as-is.

## Public Markdown cards

```python
from skills.report.strategy_markdown import StrategyReport, write_strategy_report

report = StrategyReport(
    slug="demo",
    title="Demo Strategy",
    domain="time_series",
    strategy_type="Rule-based",
    label="none",
    description="Demo description.",
    metrics={"sharpe_ratio": 1.5, "total_return": -0.0102},
    result_df=result_df,
    notes=["Uses date x symbol vector weights."],
)
path = write_strategy_report(report, "reports/strategy_examples")
```

Keep this path for `scripts/run_strategy_reports`. Do not upgrade those cards
into nine-section HTML unless explicitly requested.

## Available charts

| Function | Returns |
|----------|---------|
| `plot_equity_curve(returns, title)` | Cumulative `(1+r).cumprod()` equity curve |
| `plot_backtest_performance(result_df, title)` | Backtest equity curve plus drawdown |
| `plot_factor_diagnostics(ic_series, ic_stats, group_returns, turnover, title, rolling_ir_window)` | IC, rolling IR, layered NAV, and turnover dashboard |
| `plot_ic_heatmap(ic_df, title)` | RdBu_r symmetric heatmap (rows=factors, cols=namespaces/periods) |
| `plot_rolling_pair_correlation(history, title)` | Small-multiple histories from Analyze's tidy rolling factor correlations |
| `plot_horizon_ic(summary, factors, segment)` | Multi-factor Horizon IC term structure |
| `plot_lagged_ic(summary, factors, horizons, segment)` | Four-panel signal-delay decay curves |
| `plot_rebalance_comparison(comparison, segment, selected_days)` | Net Sharpe and turnover by rebalance interval |
| `plot_factor_weight_history(factor_weights, method, start)` | Stacked dynamic factor weights |
| `plot_equity_comparison(equities, start, title)` | Rebased equity curves for multiple combination methods |
| `plot_factor_ranking(ranking_df, value_col, label_col, title, top_n)` | Horizontal bar chart of top factors, colored by sign |
| `plot_regime_states(prices, states, title)` | Price line with colored bands per regime |

All helpers return `bytes` (PNG). The headless `Agg` backend is pinned at
import time so reports render without a display.

## Template conventions

- Inline CSS only — reports must render standalone without external assets.
- Header band uses `#4f81bd`; table header background `#f4f4f4`.
- Optional chart blocks are wrapped in `{% if chart %} … {% endif %}`.
- Safe-render pre-built tables via `{{ table.html | safe }}`.
