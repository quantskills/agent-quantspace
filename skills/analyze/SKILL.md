---
name: analyze
description: Use when tasks need factor diagnostics, IC/grouped return analysis, attribution, robustness checks, or time-series distribution and stationarity checks.
---

# Analyze

Analyze is the research diagnostics boundary. Use it to understand factors,
returns, attribution, robustness, and time-series behavior after data and
signals have been produced. Strategy execution and portfolio construction live
in `skills.backtest`.

## Public API

```python
from skills.analyze.factor_analysis import IC_stat, group_stat, full_stat
from skills.analyze.ts_analysis import TimeSeriesAnalyzer, analyze_time_series
from skills.analyze.attribution_counterfactual import performance_metrics
```

## Components

| Module family | Purpose |
|---------------|---------|
| `factor_analysis` | IC statistics, grouped returns, winsorization, drawdown helpers |
| `ts_analysis` | KDE/QQ plots, Hurst, ADF, KPSS, trend scoring |
| `attribution_*` | Symbol/category PnL, Brinson, decision edges, ranking buckets, Shapley, robustness, stat tests |
| `tearsheet` | Pool summary report helpers |

## Recipes

**Factor evaluation**

```python
from skills.analyze.factor_analysis import IC_stat, group_stat

ic_stat_dict, ic_series = IC_stat(df, rank_IC=True, n=5)
group_return, turnover = group_stat(df, n=5, g=5, verbose=True)
```

**Time-series stationarity check**

```python
from skills.analyze.ts_analysis import TimeSeriesAnalyzer

analyzer = TimeSeriesAnalyzer(price_series)
analyzer.analyze_windows([60, 120, 240])
results_df = analyzer.get_results_dataframe()
```
