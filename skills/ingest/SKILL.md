---
name: ingest
description: Use when tasks need PandaData/PandaAI stock, fund, ETF, index, or futures data, reference data, adjustment factors, futures tick downloads, or symbol conversion.
---

# PandaData Ingest

Use this skill when a task needs stock, listed-fund/ETF, index, or futures
market data; reference data; adjustment factors; or futures tick data from the
PandaData SDK.

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
- `get_fund_daily(start_date, end_date, symbol=...)`
- `get_fund_daily_pre(start_date, end_date, symbol=...)`
- `get_fund_daily_post(start_date, end_date, symbol=...)`

**Reference**

- `get_stock_detail`
- `get_fund_detail`
- `get_index_detail`
- `get_index_indicator`
- `get_index_weights`
- `get_industry_detail`
- `get_industry_constituents`
- `get_stock_industry`
- `get_concept_list`
- `get_concept_constituents`
- `get_adj_factor`

**ETF Creation/Redemption**

- `get_fund_etf_cr_limits`
- `get_fund_etf_cr_net`
- `get_fund_etf_constituents`
- `get_fund_etf_cr`

Listed ETFs and LOFs are funds, not A-share stocks. Fetch their bars with
`get_fund_daily*`; do not send them to `get_stock_daily`, `get_factor`, or
`fetch_market_data(..., type="stock")`. The `get_fund_etf_*` methods provide
creation/redemption data and are not price-bar replacements.

The three `get_fund_daily*` methods accept an inclusive `YYYYMMDD` range of
any length. `PandaDataClient` automatically sends contiguous requests of at
most 365 calendar days and concatenates the returned frames in request order.
This handling applies only to listed-fund daily bars, not `get_fund_etf_*`
creation/redemption endpoints.

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
| `pandaai-13-funds-etf.md` | fund metadata, listed-fund bars, ETF creation/redemption | `get_fund_detail`, `get_fund_daily*`, `get_fund_etf_*` |

## Recipes

**Daily A-share bars**

```python
from skills.ingest import PandaDataClient

client = PandaDataClient()
df = client.fetch_market_data("SHSE.600000", "20230101", "20231231", type="stock")
```

**Daily ETF bars**

```python
from skills.ingest import PandaDataClient

client = PandaDataClient()
df = client.get_fund_daily(
    "20250610",
    "20250613",
    symbol="SHSE.510300",
    fields=["open", "high", "low", "close", "volume", "amount"],
)
```

Use `get_fund_daily_pre` or `get_fund_daily_post` when the research explicitly
requires forward- or backward-adjusted fund prices.

The market-data API frequency remains the real bar interval. For example,
adjusted daily bars still use `freq="1d"` (or the endpoint's daily API); do not
send `"1d_adj"` to an ingest endpoint as a frequency. `1d_adj` is only the
QuantSpace storage directory/data-set name for adjusted `1d` bars. The same
rule applies to other intervals: a directory such as `5m_adj` contains adjusted
`5m` bars, while the ingest frequency is still `5m`.

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

When saving adjusted bars, pass the storage directory key to `DataManager`,
for example `frequency="1d_adj"`, even though the frequency used to fetch or
describe those bars is `1d`. Here the DataManager parameter is a directory
selector retained by its current API, not the semantic market-data frequency.

The same store boundary applies to listed funds: normalize the returned
`date` column to the timezone-naive `eob` index, keep OHLCV columns, and call
`DataManager.save_symbol`. `PandaDataClient` never writes local files.

**Symbol conversion**

```python
from skills.ingest import to_panda_data_symbol, to_quantspace_symbol

assert to_panda_data_symbol("SHSE.510300") == "510300.SH"
assert to_quantspace_symbol("RB_DOMINANT.SHF") == "SHFE.RB99"
```
