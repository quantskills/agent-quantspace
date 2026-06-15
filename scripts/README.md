# Scripts

[中文说明](README-zh.md)

This directory contains runnable entrypoints for demos and data import helpers.

Scripts must stay small and compose public `skills/` and `strategies/` modules
instead of duplicating research logic.
Small script-local helpers for argument parsing, date chunking, or file
normalization are acceptable; reusable research behavior belongs in `skills/`
or `strategies/`.
In the current skill boundary, scripts should call `skills.backtest` for
portfolio construction, execution, costs, and metrics, and `skills.ml` for
reusable ML helpers.

## Public Scripts

- `generate_sample_data.py`: writes deterministic synthetic OHLCV data and a
  sample pool.
- `run_cross_sectional_demo.py`: runs the public cross-sectional rotation demo
  on existing `data/market/1d/` Parquet files.
- `run_time_series_demo.py`: runs the public time-series ML demo with
  triple-barrier labels on existing `data/market/1d/` Parquet files.
- `run_strategy_reports.py`: orchestrates two cross-sectional examples and two
  time-series examples from existing daily Parquet files, then writes Markdown
  reports and PNG charts through `skills.report.strategy_markdown`.
- `import_panda_data_demo.py`: imports PandaData bars into local
  `DataManager` storage.

## Usage

```bash
uv run python scripts/generate_sample_data.py
uv run python scripts/run_cross_sectional_demo.py
uv run python scripts/run_time_series_demo.py
uv run python scripts/run_strategy_reports.py
```

`generate_sample_data.py` is only a deterministic fixture helper. For real
research outputs, import or place real daily Parquet data under
`data/market/1d/` before running the strategy scripts.

Keep private one-off research scripts outside this repository.
