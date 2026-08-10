---
name: strategy
description: Use when tasks need reusable strategy contracts, cross-sectional selection types, or time-series signal-to-weight helpers.
---

# Strategy

`skills/strategy` owns reusable strategy types that convert features, scores,
labels, or signals into date × symbol target weights. Concrete public strategy
behavior remains under `strategies/`.

## Public API

```python
from skills.strategy import StrategyContext, StrategyResult, WeightGenerator
from skills.strategy.cross_sectional import (
    DynamicFactorWeightConfig,
    ModularBacktester,
    apply_rebalance_schedule,
    combine_factor_scores,
    estimate_factor_weights,
    normalize_factor_frames,
    rank_factor_frames,
    top_n_weights,
)
from skills.strategy.time_series import signal_to_single_asset_weights
```

## Boundaries

- `contracts.py` defines the strategy-neutral target-weight result and generator protocol.
- `ports.py` defines only the market-data reader needed by current workflows; it
  does not predeclare persistence or Tracking APIs.
- `cross_sectional/` owns reusable ranking, selection, exit, risk-control, and
  modular research types, including equal-rank, equal-vote, rolling IC,
  rolling ICIR, and correlation-aware maximum-ICIR factor combinations.
- `time_series.py` owns signal-to-weight conversion and a research-only
  `TimeSeriesBacktester` adapter that delegates execution to `VectorBacktester`.
- Concrete factors, features, rules, model pipelines, and workflows belong in
  `strategies/`.
- Formal public execution always passes target weights to
  `skills.backtest.VectorBacktester`.

`TimeSeriesBacktester` keeps exploratory prediction-frame analysis available,
but does not implement a second return or metric engine. Published public
strategy results should still use explicit target weights plus `VectorBacktester`.

## Multi-factor combination recipe

```python
from skills.strategy.cross_sectional import (
    DynamicFactorWeightConfig,
    combine_factor_scores,
)

config = DynamicFactorWeightConfig(
    availability_delay=signal_lag + horizon,
    lookback=252,
    min_periods=126,
    max_weight=0.5,
    correlation_shrinkage=0.5,
)
result = combine_factor_scores(
    raw_factors,
    method="max_icir",
    directions=factor_directions,
    normalization="rank",
    top_n=3,
    ic_history=ic_history,
    correlation_history=rolling_rank_correlations,
    dynamic_config=config,
)
```

Supported methods are equal rank, equal vote, rolling IC, rolling ICIR, and
correlation-aware maximum ICIR. `result.factor_weights` is the factor-level
voice in the composite score; `result.target_weights` is the separate asset
allocation produced after Top-N selection. Maximum ICIR requires tidy
correlation history with columns `eob`, `factor_a`, `factor_b`, and
`correlation`. The public combination entry point always applies factor
direction and daily cross-sectional normalization. Use `normalization="rank"`
for robust percentile ranks or `normalization="zscore"` to retain relative
score distance; do not pre-normalize inputs.

## Time-series recipe

```python
from skills.backtest import VectorBacktester
from skills.strategy.time_series import signal_to_single_asset_weights

weights = signal_to_single_asset_weights(signal, symbol="SHSE.510300")
result = VectorBacktester(
    panel,
    signal_lag=1,
    commission=0.0002,
    slippage_bp=2.0,
).run(weights)
```
