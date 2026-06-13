---
name: cross-sectional-rotation
description: Public cross-sectional rotation example using generic factors and the modular backtester.
---

# Cross-Sectional Rotation

This domain demonstrates a long-only rotation workflow:

```
panel OHLCV -> factors/rules/ML ranks -> weights -> VectorBacktester -> metrics
```

## Data Contract

- Input data is a `pd.DataFrame` with MultiIndex `(symbol, eob)`.
- Required columns: `close`; `open` is required when `trade_at="open"`.
- Factor functions accept a single-symbol DataFrame and return a Series aligned
  to that symbol's index.

## Public Modules

- `strategies.cross_sectional.factors`: generic example factors.
- `strategies.cross_sectional.rules`: rule-based cross-sectional weights.
- `strategies.cross_sectional.ml_rank`: rank labels, generic features, and XGBoost rank weights.
- `strategies.cross_sectional.modular_backtester`: high-level orchestration.
- `strategies.cross_sectional.signals_top_pct`: top-percent signal generation.
- `skills.analyze.backtest`: shared vectorized execution, costs, and metrics.
- `strategies.cross_sectional.types`: config types.
- `strategies.cross_sectional.exits`: reusable exit filters.

## Example

```python
from strategies.cross_sectional.factors import momentum_score, volatility_score
from strategies.cross_sectional.modular_backtester import ModularBacktester

factor_configs = [
    {"func": momentum_score, "kwargs": {"lookback": 20}, "name": "momentum", "direction": 1},
    {"func": volatility_score, "kwargs": {"lookback": 20}, "name": "low_vol", "direction": 1},
]

bt = ModularBacktester(
    data=panel,
    factor_configs=factor_configs,
    top_pct=0.5,
    commission=0.0002,
    slippage_bp=2.0,
    rebalance_freq=5,
)
bt.run()
print(bt.metrics)
```
