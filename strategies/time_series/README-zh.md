# Time-Series 策略域

[English README](README.md)

这个策略域展示公开的单品种 ML workflow。

```text
raw OHLCV bars -> features/rules/triple-barrier labels -> weights -> VectorBacktester
```

## 主要模块

- `features.py`：公开价格/成交量特征 helper。
- `rules.py`：规则类单品种权重 helper。
- `ml.py`：三重屏障 XGBoost 信号到权重 helper。
- `workflows/run_demo.py`：不注入路径、通过模块运行的公开 demo。
- `STRATEGY.md`：策略域说明和端到端示例。

通用 signal-to-weight 类型由 `skills.strategy.time_series` 提供。
执行和收益核算由 `skills.backtest.VectorBacktester` 提供。

## 标签

公开 workflow 使用 `skills.compute` 中的 `TripleBarrierLabelMaker`。
私有标签实验不属于开源边界。

## Demo

```bash
uv run python -m strategies.time_series.workflows.run_demo
```
