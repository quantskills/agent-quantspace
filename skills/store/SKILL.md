---
name: store
description: Use when tasks need local Parquet market data storage, pool management, research artifacts, backtest records, or model metadata.
---

# Store

Use this skill when a task needs local file management for research data and
artifacts. The public project uses `DataManager` as the storage boundary.

## DataManager

```python
from skills.store.data_manager import DataManager, DataQualityReport, validate_ohlcv
```

`DataManager` resolves its root from `QUANTSPACE_DATA_ROOT`, falling back to
the repository `data/` directory.

## Supported Layout

- `data/market/{frequency}/{symbol}.parquet`
- `data/adj_factor/{symbol}.parquet`
- `data/pools/{pool_id}.json`
- `data/factors/{pool_id}/`
- `data/factor_test/{pool_id}/`
- `data/correlation/`
- `data/backtest/`
- `data/models/`
- `data/export/`

## Main Methods

**Market data**

- `read_symbol(symbol, frequency="1d")`
- `read_symbols(symbols, frequency="1d")`
- `save_symbol(symbol, df, frequency="1d", source="unknown")`
- `import_symbol_csv(csv_path, symbol, frequency="1d")`
- `import_combined_csv(csv_path, frequency="1d")`
- `list_symbols(frequency="1d")`

**Pools**

- `create_pool(pool_id, symbols, description="", frequency="1d")`
- `get_pool_symbols(pool_id)`
- `get_pool_frequency(pool_id)`
- `load_pool_data(pool_id)`
- `check_pool_coverage(pool_id)`
- `list_pools()`

**Research artifacts**

- `save_factor`, `read_factor`
- `save_factor_test`, `read_factor_test_summary`
- `save_factor_correlation`, `read_factor_correlation`
- `save_backtest_run`, `read_backtest_summary`, `read_backtest_run`
- `list_models`, `read_model_metadata`

## Recipes

**Save PandaData bars**

```python
import pandas as pd

from skills.ingest import PandaDataClient
from skills.store.data_manager import DataManager

raw = PandaDataClient().fetch_market_data("SHSE.600000", "20230101", "20231231")
bars = raw.copy()
bars["eob"] = pd.to_datetime(bars["date"])
bars = bars.set_index("eob")[["open", "high", "low", "close", "volume"]].sort_index()

DataManager().save_symbol("SHSE.600000", bars, frequency="1d", source="panda_data")
```

**Load a panel**

```python
from skills.store.data_manager import DataManager

dm = DataManager()
panel = dm.load_pool_data("sample_etf_rotation")
```

**Load explicit symbols**

```python
from skills.store.data_manager import DataManager

dm = DataManager()
panel = dm.read_symbols(["CFFEX.IF99", "SHFE.CU99"], frequency="1d")
```

`read_symbols` returns a MultiIndex `(symbol, eob)` panel and reports all
missing symbols in one `FileNotFoundError`.
