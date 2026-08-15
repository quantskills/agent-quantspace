# Scripts

[English README](README.md)

这个目录存放全局数据、报告和维护入口。

脚本必须保持小而清晰，优先组合公开 `skills/` 和 `strategies/` 模块，不要复制研究逻辑。
参数解析、日期分块、文件规范化这类脚本本地 helper 可以保留；可复用研究行为应放到
`skills/` 或 `strategies/`。
策略专用 demo 放在各策略域的 `workflows/` 包中。在当前边界下，执行和指标调用
`skills.backtest`，通用策略类型调用 `skills.strategy`，可复用 ML 能力调用 `skills.ml`。

## 公开脚本

- `generate_sample_data.py`：为 demo 的显式品种列表生成确定性的合成 OHLCV 数据。
- `run_strategy_reports.py`：基于已有日线 Parquet 编排三个横截面示例和两个时序示例，其中包括覆盖 18 个资产代理的 ETF/LOF Top 3 轮动，并写出 HTML 报告和 PNG 图表。
- `import_panda_data_demo.py`：将 PandaData bar 导入本地 `DataManager` 存储。

## 使用方式

```bash
uv run python -m scripts.generate_sample_data
uv run python -m strategies.cross_sectional.workflows.run_demo
uv run python -m strategies.time_series.workflows.run_demo
uv run python -m scripts.run_strategy_reports
# 也可以直接读取另一份本地数据根目录，避免复制或覆盖工作区行情：
uv run python -m scripts.run_strategy_reports --data-root /path/to/data
```

`generate_sample_data.py` 只是确定性的 fixture 辅助脚本。真实研究输出应先通过 PandaData
导入，或自行把真实日线 Parquet 放到 `data/market/1d/`，再运行策略脚本。

私有一次性研究脚本应放在私有仓库，不要进入本开源仓库。
