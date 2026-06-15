# Cross-Sectional Strategy Domain

[中文说明](README-zh.md)

This domain demonstrates a public ETF-style cross-sectional rotation workflow.

```text
panel OHLCV -> factors/rules/ML ranks -> weights -> VectorBacktester -> metrics
```

## Main Modules

- `factors.py`: public generic factors such as momentum, volatility, trend, and
  mean reversion.
- `rules.py`: rule-based cross-sectional weight helpers.
- `ml_rank.py`: rank labels, generic factors, and XGBoost rank weights.
- `factor_frame.py`: factor calculation and panel assembly helpers.
- `signals_top_pct.py`: top-percent selection logic.
- `modular_backtester.py`: high-level orchestration.
- `exits.py`: reusable exit and risk filters.
- `types.py`: configuration types.

Execution and return accounting live in `skills.backtest.VectorBacktester`.

## Demo

```bash
uv run python scripts/run_cross_sectional_demo.py
```

The input panel must use MultiIndex `(symbol, eob)` and OHLCV columns.
