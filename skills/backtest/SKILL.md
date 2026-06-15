---
name: backtest
description: Use when tasks need vectorized strategy execution, portfolio weighting, portfolio-level filters, transaction cost helpers, exit A/B analysis, overlay metrics, or multi-strategy return blending.
---

# Backtest

Backtest is the shared portfolio execution and construction boundary. Strategy
domains should produce date x symbol weights; this skill turns those weights
into executed weights, returns, costs, diagnostics, and report-ready metrics.

## Public API

```python
from skills.backtest import VectorBacktester, annual_return_metrics
from skills.backtest.weighting import WEIGHT_METHODS, risk_parity
from skills.backtest.filters import apply_portfolio_filters
from skills.backtest.cost_model import cost_bp_for_trigger_time
from skills.backtest.exit_analysis import evaluate_exit_factor
from skills.backtest.overlay_metrics import overlay_alpha
```

## Components

| Module | Purpose |
|--------|---------|
| `skills.backtest.vector` | `VectorBacktester`, `BacktestResult`, annual/activity/benchmark metrics |
| `skills.backtest.weighting` | Equal weight, risk parity, inverse variance, EPO, `WEIGHT_METHODS` |
| `skills.backtest.filters` | Market breadth, index trend, and volatility targeting overlays |
| `skills.backtest.combiner` | Blend multiple strategy return streams |
| `skills.backtest.cost_model` | A-share trigger-time cost layers and single-trade PnL helpers |
| `skills.backtest.exit_analysis` | Baseline vs filtered exit A/B evaluation |
| `skills.backtest.overlay_metrics` | Overlay alpha, win rate, drawdown, Sharpe, and regime metrics |

`VectorBacktester` requires explicit `commission` and `slippage_bp`; there is no
symbol-level fallback cost table. By default, each date's executed weight earns
the next bar's return (`return_mode="forward"`), which is the safer convention
for close-derived signals. Use `return_mode="backward"` only when weights are
already known before the return interval being measured.

## Recipes

**Run weights through the shared vectorized backtester**

```python
from skills.backtest import VectorBacktester

result = VectorBacktester(
    data=panel,
    trade_at="close",
    signal_lag=1,
    commission=0.0002,
    slippage_bp=2.0,
).run(weights_df)
```

**Convert votes to risk-aware weights**

```python
from skills.backtest.weighting import risk_parity

weights = risk_parity(votes_df, returns_df=returns_df, lookback=60, min_periods=20)
```

**Evaluate an exit filter**

```python
from skills.backtest.exit_analysis import evaluate_exit_factor

result = evaluate_exit_factor(
    data,
    factor_configs,
    exit_filter,
    commission=0.0002,
    slippage_bp=2.0,
)
```
