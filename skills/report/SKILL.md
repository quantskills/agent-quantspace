---
name: report
description: Use when tasks need HTML reports, Markdown strategy reports, PNG chart helpers, or report files under the research reports directory.
---

# Report Skill

Render research outputs into self-contained HTML (optionally PDF) using
Jinja2 templates + matplotlib charts.

## What it provides

| Component | Purpose |
|-----------|---------|
| `ReportRenderer` | Load Jinja2 templates from `skills/report/templates/`, render with context, save to `reports/` |
| `charts` module | Return matplotlib figures as PNG `bytes` for inline embedding |
| `strategy_markdown` | Write public Markdown strategy reports plus PNG performance charts |
| Templates | `factor_report.html`, `backtest_report.html`, `signal_digest.html` |

Charts are inlined as base64 data URIs via the `png_data_uri` Jinja filter, so
every report is a single portable HTML file.

## Python API

```python
from skills.report import ReportRenderer, charts

renderer = ReportRenderer()
ranking_png = charts.plot_factor_ranking(ranking_df, value_col="IC_IR")

html = renderer.render(
    "factor_report",
    {
        "title": "Macro pool — weekly factor screen",
        "pool": "macro_pool",
        "n": 5,
        "as_of": "2026-05-08",
        "ranking_chart": ranking_png,           # bytes
        "ranking_html": ranking_df.to_html(),   # pre-rendered pandas table
    },
)
path = renderer.save(html, "macro_pool_2026-05-08.html")
```

Strategy Markdown reports:

```python
import pandas as pd

from skills.report.strategy_markdown import StrategyReport, write_strategy_report

result_df = pd.DataFrame(
    {
        "return": [0.01, -0.02],
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
    metrics={"sharpe_ratio": 1.5, "total_return": -0.0102},
    result_df=result_df,
    notes=["Uses date x symbol vector weights."],
)
path = write_strategy_report(report, "reports/strategy_examples")
```

Pass a template name with or without `.html`; both work. Relative output
paths resolve against `reports/` at the repo root; absolute paths are
respected as-is.

## Available charts

| Function | Returns |
|----------|---------|
| `plot_equity_curve(returns, title)` | Cumulative `(1+r).cumprod()` equity curve |
| `plot_backtest_performance(result_df, title)` | Backtest equity curve plus drawdown |
| `plot_ic_heatmap(ic_df, title)` | RdBu_r symmetric heatmap (rows=factors, cols=pools/periods) |
| `plot_factor_ranking(ranking_df, value_col, label_col, title, top_n)` | Horizontal bar chart of top factors, colored by sign |
| `plot_regime_states(prices, states, title)` | Price line with colored bands per regime |

All helpers return `bytes` (PNG). The headless `Agg` backend is pinned at
import time so reports render inside cron jobs and SSH sessions without a
display.

## Template conventions

- Inline CSS only — reports must render standalone without external assets.
- Header band uses `#4f81bd`; table header background `#f4f4f4`.
- Optional chart blocks are wrapped in `{% if chart %} … {% endif %}`; the
  `png_data_uri` filter returns an empty string when the chart is `None`, but
  guarding with `{% if %}` avoids rendering an empty `<img>` tag.
- Safe-render pre-built tables via `{{ df.to_html() | safe }}`.

## PDF output (optional)

```python
renderer.to_pdf(html, "macro_pool_2026-05-08.pdf")
```

Requires `weasyprint` (install via `uv pip install weasyprint`). Keep this as
an optional dependency — core reports should work without it.
