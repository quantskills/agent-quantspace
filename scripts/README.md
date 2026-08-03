# Scripts

[中文说明](README-zh.md)

This directory contains global data, report, and maintenance entrypoints.

Scripts must stay small and compose public `skills/` and `strategies/` modules
instead of duplicating research logic.
Small script-local helpers for argument parsing, date chunking, or file
normalization are acceptable; reusable research behavior belongs in `skills/`
or `strategies/`.
Strategy-specific demos live under each domain's `workflows/` package. In the
current boundary, scripts call `skills.backtest` for execution and metrics,
`skills.strategy` for reusable strategy types, and `skills.ml` for reusable ML
helpers.

## Public Scripts

- `generate_sample_data.py`: writes deterministic synthetic OHLCV data for the
  demo's explicit symbol list.
- `run_strategy_reports.py`: orchestrates three cross-sectional examples and two
  time-series examples from existing daily Parquet files, including an 18-proxy
  global-asset ETF/LOF Top-3 rotation, then writes Markdown reports and PNG
  charts through `skills.report.strategy_markdown`.
- `import_panda_data_demo.py`: imports PandaData bars into local
  `DataManager` storage.

## Usage

```bash
uv run python -m scripts.generate_sample_data
uv run python -m strategies.cross_sectional.workflows.run_demo
uv run python -m strategies.time_series.workflows.run_demo
uv run python -m scripts.run_strategy_reports
# Or read a separate local data root without copying/overwriting workspace data:
uv run python -m scripts.run_strategy_reports --data-root /path/to/data
```

`generate_sample_data.py` is only a deterministic fixture helper. For real
research outputs, import or place real daily Parquet data under
`data/market/1d/` before running the strategy scripts.

Keep private one-off research scripts outside this repository.
