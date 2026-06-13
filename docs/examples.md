# Examples

## Generate Sample Data

```bash
uv run python scripts/generate_sample_data.py
```

This writes deterministic synthetic OHLCV data into `data/market/1d/` and a
sample pool into `data/pools/sample_etf_rotation.json`. It is intended for
smoke tests and local development fixtures.

## Cross-Sectional Demo

```bash
uv run python scripts/run_cross_sectional_demo.py
```

The demo runs generic momentum and low-volatility factors through
`ModularBacktester` using the configured sample pool and existing
`data/market/1d/` Parquet files.

## Time-Series Demo

```bash
uv run python scripts/run_time_series_demo.py
```

The demo creates public triple-barrier labels, trains a small scikit-learn
classifier, maps predictions to a date x symbol weight matrix, and runs
`skills.analyze.backtest.VectorBacktester` on an existing single-symbol daily
Parquet file.

## Example Strategy Reports

```bash
uv run python scripts/run_strategy_reports.py
```

This generates four public strategy reports and performance PNGs under
`reports/strategy_examples/`: two cross-sectional examples and two time-series
examples. In each domain, one strategy is rule-based and the other uses
XGBoost. The script is only an orchestration layer; reusable logic lives in
`skills/` and `strategies/`.

The report script reads existing daily Parquet files from `data/market/1d/`.
Import real PandaData bars or place your own sanitized Parquet files there
before running it for real research output.

## PandaData Import Demo

```bash
uv sync --extra panda_data
uv run python scripts/import_panda_data_demo.py --symbol SHSE.600000 --start-date 20230101 --end-date 20231231
```
