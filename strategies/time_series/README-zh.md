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
- `signal_engine.py`：从原始 OHLCV bar 和训练好的分类器生成流式信号。
- `types.py`：默认成本、延迟和仓位映射。
- `STRATEGY.md`：策略域说明和端到端示例。

执行和收益核算由 `skills.backtest.VectorBacktester` 提供。

## 标签

公开 workflow 使用 `skills.compute` 中的 `TripleBarrierLabelMaker`。
私有标签实验不属于开源边界。

## Demo

```bash
uv run python scripts/run_time_series_demo.py
```
