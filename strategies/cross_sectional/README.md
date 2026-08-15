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
- `ml_rank.py`: rank labels plus expanding PCA model scores/weights on top of the
  `skills.compute.features` LogDiff panel.
- `workflows/run_demo.py`: the runnable public strategy workflow.
- `workflows/run_lesson06_multifactor.py`: reproducible Horizon/Lagged IC,
  correlation, rebalance, and five-method multi-factor experiment.
- `workflows/run_lesson07_etf18_logdiff_pca_ml.py`: 18-ETF LogDiff + expanding
  PCA + ols/lasso/rf/xgboost rank comparison with equal-weight Top-3 backtest.

Factor-frame construction, selection, risk controls, and `ModularBacktester`
live in `skills.strategy.cross_sectional`. Execution and return accounting live
in `skills.backtest.VectorBacktester`.

## Demo

```bash
uv run python -m strategies.cross_sectional.workflows.run_demo
uv run python -m strategies.cross_sectional.workflows.run_lesson06_multifactor --normalization rank
uv run python -m strategies.cross_sectional.workflows.run_lesson07_etf18_logdiff_pca_ml
```

The multifactor workflow defaults to daily cross-sectional percentile ranks;
use `--normalization zscore` for population z-scores.

The input panel must use MultiIndex `(symbol, eob)` and OHLCV columns.

The public asset-class example rebalances every 20 trading days and equally
weights the three strongest eligible proxies. Its explicit universe is defined
by `asset_class_rotation.ASSET_CLASS_ETF_UNIVERSE`. The workflow applies the three
publicly disclosed 2022 share splits in its raw-price history before both signal
and return calculation.
