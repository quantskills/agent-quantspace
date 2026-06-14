# Scripts

[English README](README.md)

这个目录存放可直接运行的 demo 和数据导入入口。

脚本必须保持小而清晰，优先组合公开 `skills/` 和 `strategies/` 模块，不要复制研究逻辑。
参数解析、日期分块、文件规范化这类脚本本地 helper 可以保留；可复用研究行为应放到
`skills/` 或 `strategies/`。

## 公开脚本

- `generate_sample_data.py`：生成确定性的合成 OHLCV 数据和 sample pool。
- `run_cross_sectional_demo.py`：基于 `data/market/1d/` 下已有 Parquet 运行公开横截面轮动示例。
- `run_time_series_demo.py`：基于 `data/market/1d/` 下已有 Parquet 运行使用三重屏障标签的公开 time-series ML 示例。
- `run_strategy_reports.py`：基于已有日线 Parquet 编排两个横截面示例和两个时序示例，并写出 Markdown 报告和 PNG 图表。
- `import_panda_data_demo.py`：将 PandaData bar 导入本地 `DataManager` 存储。

## 使用方式

```bash
uv run python scripts/generate_sample_data.py
uv run python scripts/run_cross_sectional_demo.py
uv run python scripts/run_time_series_demo.py
uv run python scripts/run_strategy_reports.py
```

`generate_sample_data.py` 只是确定性的 fixture 辅助脚本。真实研究输出应先通过 PandaData
导入，或自行把真实日线 Parquet 放到 `data/market/1d/`，再运行策略脚本。

私有一次性研究脚本应放在私有仓库，不要进入本开源仓库。
