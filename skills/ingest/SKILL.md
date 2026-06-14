---
name: ingest
description: Use when tasks need PandaData/PandaAI market data, reference data, adjustment factors, futures tick downloads, or symbol conversion.
---

# PandaData Ingest

Use this skill when a task needs market bars, reference data, adjustment
factors, or futures tick data from the PandaData SDK.

## Prerequisites

- Install optional SDK dependencies with `uv sync --extra panda_data`.
- Set `PANDA_DATA_USERNAME` and `PANDA_DATA_PASSWORD` in the environment.
- `PandaDataClient` fetches data only. Persist normalized OHLCV with
  `skills.store.data_manager.DataManager`.

## Public API

```python
from skills.ingest import PandaDataClient
from skills.ingest import to_panda_data_symbol, to_quantspace_symbol
```

`PandaDataClient` accepts QuantSpace symbols such as `SHSE.510300` and
panda_data native symbols such as `510300.SH`. Returned `symbol` columns are
converted back to QuantSpace format by default.

## Wrapped Endpoints

**Bars**

- `fetch_market_data(symbol, start_date, end_date, type="stock")`
- `fetch_market_min_data(symbol, start_date, end_date, symbol_type="stock", frequency="1m")`
- `fetch_hk_daily(symbol, start_date, end_date)`
- `fetch_us_daily(symbol, start_date, end_date)`

**Reference**

- `get_stock_detail`
- `get_index_detail`
- `get_index_indicator`
- `get_index_weights`
- `get_industry_detail`
- `get_industry_constituents`
- `get_stock_industry`
- `get_concept_list`
- `get_concept_constituents`
- `get_adj_factor`

**Futures Tick Utility**

`skills.ingest.panda_future_tick` contains offline-testable helpers and CLI
building blocks for PandaData futures tick downloads.

## Progressive References

Detailed PandaAI docs are split by task under `references/`. Open only the
specific file needed for the endpoint you are using.

| Reference | Open when you need | Main methods |
|-----------|--------------------|--------------|
| `pandaai-01-overview-setup.md` | setup and auth | `init_token` |
| `pandaai-02-market-daily.md` | A-share/index/futures daily bars | `get_market_data` |
| `pandaai-03-market-minute.md` | A-share/index/futures intraday bars | `get_market_min_data` |
| `pandaai-04-market-hk-us.md` | HK/US daily bars | `get_hk_daily`, `get_us_daily` |
| `pandaai-05-reference-securities.md` | stock/index metadata | `get_stock_detail`, `get_index_detail` |
| `pandaai-06-reference-classification-index.md` | classifications and index weights | `get_index_weights` |
| `pandaai-07-equity-market-events.md` | market events | `get_lhb_list`, `get_margin` |
| `pandaai-08-equity-corporate-info.md` | holders and corporate info | `get_top_holders` |
| `pandaai-09-financial-reports.md` | financial reports | `get_fina_reports` |
| `pandaai-10-factors-adjustment.md` | factors and adjustment events | `get_factor`, `get_adj_factor` |
| `pandaai-11-trading-tools.md` | calendars and trade lists | `get_trade_cal`, `get_trade_list` |
| `pandaai-12-futures.md` | futures metadata and dominant contracts | `get_future_detail` |

## Recipes

**Daily A-share bars**

```python
from skills.ingest import PandaDataClient

client = PandaDataClient()
df = client.fetch_market_data("SHSE.600000", "20230101", "20231231", type="stock")
```

**Normalize and save bars**

```python
import pandas as pd

from skills.ingest import PandaDataClient
from skills.store.data_manager import DataManager

client = PandaDataClient()
raw = client.fetch_market_data("SHSE.600000", "20230101", "20231231", type="stock")

bars = raw.copy()
bars["eob"] = pd.to_datetime(bars["date"])
bars = bars.set_index("eob")[["open", "high", "low", "close", "volume"]].sort_index()

DataManager().save_symbol("SHSE.600000", bars, frequency="1d", source="panda_data")
```

**Symbol conversion**

```python
from skills.ingest import to_panda_data_symbol, to_quantspace_symbol

assert to_panda_data_symbol("SHSE.510300") == "510300.SH"
assert to_quantspace_symbol("RB_DOMINANT.SHF") == "SHFE.RB99"
```
