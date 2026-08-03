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
from skills.strategy.cross_sectional import ModularBacktester, top_n_weights
from skills.strategy.time_series import signal_to_single_asset_weights
```

## Boundaries

- `contracts.py` defines the strategy-neutral target-weight result and generator protocol.
- `ports.py` defines only the market-data reader needed by current workflows; it
  does not predeclare persistence or Tracking APIs.
- `cross_sectional/` owns reusable ranking, selection, exit, risk-control, and
  modular research types.
- `time_series.py` owns signal-to-weight conversion and a research-only
  `TimeSeriesBacktester` adapter that delegates execution to `VectorBacktester`.
- Concrete factors, features, rules, model pipelines, and workflows belong in
  `strategies/`.
- Formal public execution always passes target weights to
  `skills.backtest.VectorBacktester`.

`TimeSeriesBacktester` keeps exploratory prediction-frame analysis available,
but does not implement a second return or metric engine. Published public
strategy results should still use explicit target weights plus `VectorBacktester`.

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
