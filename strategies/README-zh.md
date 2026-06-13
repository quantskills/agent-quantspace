# Strategies

[English README](README.md)

这个目录存放公开策略域。策略域是一个聚焦的示例 workflow，用来把可复用 skills 组合成完整研究路径。

## 公开策略域

- `cross_sectional/`：横截面轮动，使用 generic 因子、规则权重、XGBoost rank 权重和共享向量化回测器。
- `time_series/`：单品种 workflow，使用原始 OHLCV、公开特征、三重屏障标签、规则/ML 权重和共享向量化回测器。

## 边界

策略域应包含策略特定规则、特征集合、信号到权重映射和数据契约。可复用的存储、分析、构建、建模和报告能力应放在 `skills/`。

私有策略域应放在单独的私有仓库。
