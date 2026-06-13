---
name: analyze
description: Factor diagnostics (IC, layered returns, winsorization, full_stat) and exit/risk filter A/B evaluation with event studies and plots.
---

## Description

This skill merges **vectorized backtesting** (`VectorBacktester` on date × symbol
weights), **single-factor research** (`IC_stat`, `group_stat`, `full_stat` on
MultiIndex panels with `close` and `fac_val`) and **exit design**
(`evaluate_exit_factor`, summaries and plots for baseline vs filtered rotation).

It also contains overlay metrics for base-position T strategies:

- `overlay_alpha(overlay_returns_or_trade_bp, bh_daily_returns)` — annualized alpha of buy-and-hold plus overlay versus pure buy-and-hold.
- `overlay_winrate(trades)` — net win rate from a trade table.
- `overlay_maxdd(overlay_returns)` — overlay drawdown and duration.
- `overlay_sharpe(overlay_returns)` — annualized Sharpe of overlay returns.
- `regime_alpha_table(overlay_returns, bh_returns, regimes)` — per-regime overlay alpha table.

## Prerequisites

- **Factor analysis**: `pandas`, `numpy`, `scipy.stats`, `matplotlib.pyplot`; input MultiIndex must include **`eob`** and **`symbol`**, columns **`close`**, **`fac_val`** for `IC_stat` / `group_stat` / `full_stat`.
- **Exit analysis**: `pandas`, `numpy`, `matplotlib`; OHLCV panel MultiIndex `(symbol, eob)` with `close` (and columns required by factor/exit callables).
- **Exit engine**: `evaluate_exit_factor` uses the public cross-sectional modular backtester for A/B runs; configs align with `FactorConfig`-style dicts and exit filter specs used alongside `strategies.cross_sectional`.
- **Legacy Ricequant helpers** inside `factor_analysis.py` (`Factor_Return_N_IC`, `group_5`, `neutralization`) need external wiring (`get_price`, `rqdatac`, etc.).

## API Reference

### Vectorized backtests (`skills.analyze.backtest`)

```python
from skills.analyze.backtest import (
    VectorBacktester,
    activity_metrics,
    annual_return_metrics,
    benchmark_return_corr,
)
```

- `VectorBacktester(data, trade_at="close", signal_lag=1, commission=..., slippage_bp=...).run(weights_df)` — shared vectorized execution from date × symbol target weights.
- `annual_return_metrics(result_df)` — calendar-year compounded returns.
- `activity_metrics(result_df)` — trade day count and active day ratio.
- `benchmark_return_corr(result_df, benchmark_close)` — daily return correlation.

`commission` and `slippage_bp` must be explicit; there is no symbol-level fallback
cost table.

### Factor statistics (`skills.analyze.factor_analysis`)

```python
from skills.analyze.factor_analysis import IC_stat, group_stat, full_stat
from skills.analyze.factor_analysis import (
    filter_extreme_MAD,
    winsorize_std,
    winsorize_percentile,
    maxdrawdown,
    get_Performance_analysis,
)
from skills.analyze.overlay_metrics import overlay_alpha, overlay_sharpe, regime_alpha_table
```

- `IC_stat(df, rank_IC=True, n=1) -> tuple[dict, pd.Series]` — summary dict + daily IC.
- `group_stat(df, n, g, verbose=False) -> tuple[group_return, turnover_ratio]` — columns `G1`…`Gg`.
- `full_stat(df, n=1, g=5, rank_IC=True, verbose=False)` — IC + groups + plots; returns `(ic_stat_dict, ic_series, group_return, turnover)`.
- Filters: `filter_extreme_MAD`, `winsorize_std`, `winsorize_percentile`.
- Performance: `maxdrawdown`, `get_Performance_analysis`.

### Exit evaluation (`skills.analyze.exit_analysis`)

```python
from skills.analyze.exit_analysis import (
    evaluate_exit_factor,
    plot_exit_evaluation,
    print_ab_comparison,
    print_event_analysis,
    summarize_exit_factors,
)
```

- `evaluate_exit_factor(data, factor_configs, exit_filter, top_pct=0.2, commission=0.0002, slippage_bp=None, signal_lag=1, start_date=None, end_date=None, baseline_exits=None, forward_windows=None, exposure_policy="keep_cash") -> dict`  
  Keys include `ab_comparison`, `trigger_stats`, `event_analysis`, `baseline_result_df`, `variant_result_df`, `trigger_mask`.
- `plot_exit_evaluation(eval_result, figsize=(16, 10))`
- `print_ab_comparison`, `print_event_analysis`
- `summarize_exit_factors(results: list) -> pd.DataFrame`

**Factor configs**: `{'func', 'kwargs', 'name'}`. **Exit filter**: `{'func', 'kwargs', 'name', 'condition'}`.

## Recipes

**1. Standard factor evaluation**

```python
import pandas as pd
from skills.analyze.factor_analysis import IC_stat, group_stat

ic_stat_dict, ic_series = IC_stat(df, rank_IC=True, n=5)
group_return, turnover = group_stat(df, n=5, g=5, verbose=True)
```

**2. One-shot report**  
`full_stat(df, n=5, g=5, rank_IC=True)` for figures and printed tables.

**3. Exit A/B with compute factors**

```python
from skills.analyze.exit_analysis import (
    evaluate_exit_factor,
    plot_exit_evaluation,
    print_ab_comparison,
)
from skills.compute import indicators as I

factor_configs = [{"func": I.cci, "kwargs": {"period": 48}, "name": "cci"}]
exit_filter = {
    "func": I.rsi,
    "kwargs": {"period": 14},
    "name": "rsi_lt_75",
    "condition": lambda x: x < 75,
}

result = evaluate_exit_factor(
    data,
    factor_configs,
    exit_filter,
    top_pct=0.2,
    commission=0.0002,
    start_date="2020-01-01",
    forward_windows=[1, 3, 5, 10],
    exposure_policy="keep_cash",
)
print_ab_comparison(result)
plot_exit_evaluation(result)
```

**4. Cross-sectional winsorization**  
`df.groupby(level="eob", group_keys=False)["fac_val"].transform(lambda s: winsorize_std(s, n=3))` before `IC_stat`.

**5. Many exit candidates**  
Loop `evaluate_exit_factor`, then `summarize_exit_factors(results)`.

### Time-Series Analysis (`skills.analyze.ts_analysis`)

```python
from skills.analyze.ts_analysis import ts_analysis, TimeSeriesAnalyzer, analyze_time_series
```

- `ts_analysis(price, plot_title, plot_path, show, save_csv)` — KDE distribution analysis on log-return series.
- `kde_analysis(price, ...)` / `qq_analysis(price, ...)` — individual distribution plots.
- `TimeSeriesAnalyzer(series)` — Hurst exponent, ADF test, KPSS test, trend scoring.
- `analyze_time_series(series, windows)` — convenience wrapper for windowed analysis.

**6. Time-series stationarity check**

```python
from skills.analyze.ts_analysis import TimeSeriesAnalyzer

analyzer = TimeSeriesAnalyzer(price_series)
analyzer.analyze_windows([60, 120, 240])
results_df = analyzer.get_results_dataframe()
```
