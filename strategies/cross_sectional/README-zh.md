# Cross-Sectional 策略域

[English README](README.md)

这个策略域展示公开的 ETF 风格横截面轮动 workflow。

```text
panel OHLCV -> factors/rules/ML ranks -> weights -> VectorBacktester -> metrics
```

## 主要模块

- `factors.py`：公开 generic 因子，例如动量、波动率、趋势和均值回归。
- `rules.py`：规则类横截面权重 helper。
- `ml_rank.py`：rank label、generic 因子和 XGBoost rank 权重。
- `factor_frame.py`：因子计算和 panel 组装 helper。
- `signals_top_pct.py`：top-percent 选取逻辑。
- `modular_backtester.py`：高层编排入口。
- `exits.py`：可复用退出和风险过滤器。
- `types.py`：配置类型。

执行和收益核算由 `skills.backtest.VectorBacktester` 提供。

## Demo

```bash
uv run python scripts/run_cross_sectional_demo.py
```

输入 panel 必须使用 MultiIndex `(symbol, eob)` 和 OHLCV 列。
