---
name: cross-sectional-rotation
description: Public cross-sectional rotation behavior built on reusable strategy types.
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
- `strategies.cross_sectional.asset_class_rotation`: explicit 18-proxy global-asset ETF/LOF universe and Top-3 composite-momentum weights.
- `strategies.cross_sectional.rules`: rule-based cross-sectional weights.
- `strategies.cross_sectional.ml_rank`: rank labels and expanding PCA model scores/weights (`ols` / `lasso` / `rf` / `xgboost`; default Top-N equal weight) built on the `skills.compute.features` LogDiff panel.
- `strategies.cross_sectional.workflows`: runnable public workflows.
- `skills.strategy.cross_sectional`: factor frames, selection, exits, risk controls, and research orchestration.
- `skills.backtest`: shared vectorized execution, costs, and metrics.

## Example

```python
from strategies.cross_sectional.factors import momentum_score, volatility_score
from skills.strategy.cross_sectional import ModularBacktester

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

The public large-asset rotation uses the new reusable weight interface directly:

```python
from strategies.cross_sectional.asset_class_rotation import (
    ASSET_CLASS_ETF_SYMBOLS,
    asset_class_top3_weights,
)

weights = asset_class_top3_weights(close[ASSET_CLASS_ETF_SYMBOLS])
```

Its default rule averages 20-, 60-, and 120-trading-day returns, rebalances
every 20 trading days, and equally weights the strongest three eligible proxies.
