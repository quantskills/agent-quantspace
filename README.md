# QuantSpace

[中文说明](README-zh.md)

QuantSpace is a PandaData-first quantitative research workbench. It keeps
the core small, exposes reusable research skills, and provides two public
strategy domains that can be composed by a coding agent or used directly from
Python scripts.

The repository is intended as a clean open-source core for research workflows:
data ingestion, local Parquet storage, feature and label generation, factor
analysis, portfolio construction, reporting, and demo backtests.

## What Is Included

- PandaData/PandaAI data access through `skills.ingest`.
- Local file and artifact management through `skills.store.data_manager.DataManager`.
- Generic OHLCV indicators, math utilities, time-series features, and public
  label generators.
- Generic factor examples for cross-sectional and time-series research.
- Analysis, construction, research-screening, model, and report skills.
- Two public strategy domains:
  - `strategies.cross_sectional`: ETF-style cross-sectional rotation demo.
  - `strategies.time_series`: single-instrument ML demo using triple-barrier labels.
- A deterministic fixture-data generator for smoke tests and runnable demo scripts.

## What Is Not Included

- Private strategy research, proprietary alpha logic, private notebooks, or
  generated research reports.
- Private market data, credentials, or local absolute paths.
- Non-PandaData vendor adapters or remote execution tools.
- Production trading, brokerage integration, or live order management.
- Private label experiments.

## Project Layout

```text
quantspace/
  skills/                 reusable capabilities
    ingest/               PandaData client and symbol conversion
    store/                local Parquet storage and artifact management
    compute/              indicators, features, labels, factor examples
    analyze/              factor analysis, metrics, attribution, tearsheets
    construct/            weighting, filters, strategy combination
    model/                ML helpers and optional model engines
    research/             factor screening, parameter sweeps, comparisons
    report/               HTML/Markdown report rendering and charts
  strategies/
    cross_sectional/      generic cross-sectional rotation
    time_series/          single-instrument ML workflow
  scripts/                sample data, demos, PandaData import helper
  data/                   local data root; only sample pools are committed
  reports/                local generated report output
  docs/                   architecture, data layout, examples, scope notes
  tests/                  public pytest suite
```

## Quick Start

Requirements:

- Python `>=3.10`
- `uv`

Install the default environment. For a self-contained smoke test, generate the
small fixture dataset first, then run the demos:

```bash
uv sync
uv run python scripts/generate_sample_data.py
uv run python scripts/run_cross_sectional_demo.py
uv run python scripts/run_time_series_demo.py
uv run python -m pytest tests/
```

The fixture data is synthetic and deterministic. It is written under
`data/market/` and can be regenerated at any time. For real research runs,
replace it with real daily Parquet files or import data through PandaData.

Optional extras:

```bash
uv sync --extra panda_data  # PandaData SDK
uv sync --extra ml          # optional PyCaret-based ML helpers
uv sync --extra ts          # optional time-series feature dependencies
uv sync --extra query       # optional DuckDB querying
```

## PandaData Setup

Install the optional PandaData SDK dependency:

```bash
uv sync --extra panda_data
cp .env.example .env
```

Set credentials in `.env`:

```bash
PANDA_DATA_USERNAME=86xxxxxxxxxxx
PANDA_DATA_PASSWORD=your-password
```

Run the import demo:

```bash
uv run python scripts/import_panda_data_demo.py \
  --symbol SHSE.600000 \
  --start-date 20230101 \
  --end-date 20231231
```

QuantSpace symbol format is `EXCHANGE.CODE`, such as `SHSE.510300`.
PandaData-style symbols are converted through:

```python
from skills.ingest import to_panda_data_symbol, to_quantspace_symbol

to_panda_data_symbol("SHSE.510300")  # "510300.SH"
to_quantspace_symbol("510300.SH")    # "SHSE.510300"
```

## Data Model

Market data is stored as one Parquet file per symbol:

```text
data/market/{frequency}/{symbol}.parquet
```

Each OHLCV frame is indexed by `eob` and uses:

```text
open, high, low, close, volume
```

Pools are JSON files under `data/pools/`:

```json
{
  "pool_id": "sample_etf_rotation",
  "description": "ETF-style pool for public examples",
  "frequency": "1d",
  "symbols": ["SHSE.510300", "SHSE.510500"]
}
```

`DataManager.load_pool_data(pool_id)` returns a panel indexed by
`(symbol, eob)`.

Set `QUANTSPACE_DATA_ROOT` if you want data outside the repository.

## Strategy Demos

### Cross-Sectional Rotation

Pipeline:

```text
panel OHLCV -> generic factors -> top-percent selection -> execution -> metrics
```

Run:

```bash
uv run python scripts/run_cross_sectional_demo.py
```

The demo combines simple momentum and low-volatility factors through
`strategies.cross_sectional.ModularBacktester` using existing
`data/market/1d/` Parquet files for the configured sample pool.

### Time-Series ML

Pipeline:

```text
raw OHLCV bars -> feature engineering -> triple-barrier labels -> model -> backtest
```

Run:

```bash
uv run python scripts/run_time_series_demo.py
```

The demo uses `strategies.time_series.features.make_price_volume_features`,
`TripleBarrierLabelMaker`, a small scikit-learn classifier, a date x symbol
weight matrix, and `skills.analyze.backtest.VectorBacktester` on an existing
single-symbol daily Parquet file.

### Example Strategy Reports

```bash
uv run python scripts/run_strategy_reports.py
```

This thin orchestration script reads existing PandaData daily Parquet files from
`data/market/1d/` and writes four public strategy reports plus performance PNGs
to `reports/strategy_examples/`. For both cross-sectional and time-series
domains, one example is rule-based and the other uses XGBoost. Strategy logic
lives under `strategies/`; storage, backtest metrics, weighting, and report
helpers live under `skills/`.

## Public Skills

| Skill | Main import | Purpose |
|---|---|---|
| `ingest` | `from skills.ingest import PandaDataClient` | PandaData access and symbol conversion |
| `store` | `from skills.store.data_manager import DataManager` | Market data, pools, factors, backtests, metadata |
| `compute` | `from skills.compute.indicators import trend_score` | Indicators, features, labels, generic factor examples |
| `analyze` | `from skills.analyze.backtest import VectorBacktester` | Vectorized backtests, IC, grouped returns, metrics, tearsheets |
| `construct` | `from skills.construct.weighting import WEIGHT_METHODS` | Weighting methods and portfolio filters |
| `model` | `from skills.model.ml_engine import MLEngine` | Optional ML helpers |
| `research` | `from skills.research import screen_all_indicators` | Factor screening and parameter sweeps |
| `report` | `from skills.report import ReportRenderer` | HTML/Markdown report rendering and chart helpers |

Each skill directory contains a `SKILL.md` guide.

## Documentation

- [Architecture](docs/architecture.md)
- [Data layout](docs/data_layout.md)
- [Examples](docs/examples.md)
- [PandaData ingest](docs/panda_data_ingest.md)
- [Open-source scope](docs/open_source_scope.md)
- [Private extension pattern](docs/private_extension_pattern.md)

## Development

Run the public tests:

```bash
uv run python -m pytest tests/
```

Before publishing, run the test suite and your release safety scan for private
paths, credentials, private strategy names, and removed research-only modules.

Generated data and reports should stay local. The committed repository should
only include code, docs, tests, sample pool definitions, and small templates.

## Private Extension Pattern

Keep private research in a separate repository:

```text
workspace/
  quantspace/
  quantspace-private/
```

Promote generic improvements back to this repository. Keep proprietary strategy
domains, private data adapters, alpha research, notebooks, and generated reports
out of the open-source repo.

## License

Add the project license before publishing to a public package index or Git host.
