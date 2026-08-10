# Cross-Sectional 策略域

[English README](README.md)

这个策略域展示公开的横截面轮动 workflow。具体因子、规则和 ML 行为保留在
本目录，可复用策略类型统一位于 `skills.strategy.cross_sectional`。

```text
panel OHLCV -> factors/rules/ML ranks -> weights -> VectorBacktester -> metrics
```

## 主要模块

- `factors.py`：公开示例因子，例如动量、波动率、趋势和均值回归。
- `asset_class_rotation.py`：显式定义 18 个全球大类资产 ETF/LOF 代理，并提供
  20/60/120 日复合动量 Top 3 轮动规则。
- `rules.py`：规则类横截面权重 helper。
- `ml_rank.py`：rank label、generic 因子和 XGBoost rank 权重。
- `workflows/run_demo.py`：可直接运行的公开策略 workflow。
- `workflows/run_lesson06_multifactor.py`：可复现 Horizon/Lagged IC、相关性、
  调仓周期与五种多因子组合的研究 workflow。

因子帧构建、选取、风控和 `ModularBacktester` 位于
`skills.strategy.cross_sectional`；执行和收益核算由
`skills.backtest.VectorBacktester` 提供。

## Demo

```bash
uv run python -m strategies.cross_sectional.workflows.run_demo
uv run python -m strategies.cross_sectional.workflows.run_lesson06_multifactor --normalization rank
```

多因子工作流默认使用逐日横截面百分位排名；可改为 `--normalization zscore`。

输入 panel 必须使用 MultiIndex `(symbol, eob)` 和 OHLCV 列。

公开大类资产示例每 20 个交易日调仓一次，等权持有当期动量最强且满足历史窗口要求的
三个代理。显式品种集合由 `asset_class_rotation.ASSET_CLASS_ETF_UNIVERSE` 定义。
信号和回测收益计算前，会先处理原始价格中的三次 2022 年公开份额拆分事件。
