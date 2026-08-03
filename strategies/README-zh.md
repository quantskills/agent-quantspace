# Strategies

[English README](README.md)

这个目录存放公开策略域。策略域是一个聚焦的示例 workflow，用来把可复用 skills 组合成完整研究路径。

## 公开策略域

- `cross_sectional/`：横截面轮动，使用 generic 因子、规则权重、XGBoost rank 权重和共享向量化回测器。
- `time_series/`：单品种 workflow，使用原始 OHLCV、公开特征、三重屏障标签、规则/ML 权重和共享向量化回测器。

## 边界

策略域应包含策略特定规则、特征集合、因子/模型选择和 workflow。可复用策略契约、横截面/
时序类型和 signal-to-weight 原语应放在 `skills.strategy`；存储、分析、回测、ML 和报告等
通用能力放在其他 `skills/` 包中。

私有策略域应放在单独的私有仓库。
