# Cross-Sectional Strategy Domain

[中文说明](README-zh.md)

This domain demonstrates a public cross-sectional rotation workflow. Concrete
factors, rules, and ML behavior live here; reusable strategy types live in
`skills.strategy.cross_sectional`.

```text
panel OHLCV -> factors/rules/ML ranks -> weights -> VectorBacktester -> metrics
```

## Main Modules

- `factors.py`: public example factors such as momentum, volatility, trend, and
  mean reversion.
- `asset_class_rotation.py`: explicit 18-proxy global-asset ETF/LOF universe and
  a 20/60/120-day composite-momentum Top-3 rotation rule.
- `rules.py`: rule-based cross-sectional weight helpers.
- `ml_rank.py`: rank labels, generic factors, and XGBoost rank weights.
- `workflows/run_demo.py`: the runnable public strategy workflow.

Factor-frame construction, selection, risk controls, and `ModularBacktester`
live in `skills.strategy.cross_sectional`. Execution and return accounting live
in `skills.backtest.VectorBacktester`.

## Demo

```bash
uv run python -m strategies.cross_sectional.workflows.run_demo
```

The input panel must use MultiIndex `(symbol, eob)` and OHLCV columns.

The public asset-class example rebalances every 20 trading days and equally
weights the three strongest eligible proxies. Its explicit universe is defined
by `asset_class_rotation.ASSET_CLASS_ETF_UNIVERSE`. The workflow applies the three
publicly disclosed 2022 share splits in its raw-price history before both signal
and return calculation.
