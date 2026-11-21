# Ingest Python API

Read this when changing the `ingest` Skill or writing strategy code. For research tasks use the `uv run qs ingest` commands in [../SKILL.md](../SKILL.md).

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
```

`PandaDataClient` takes and returns PandaData codes such as `510300.SH`,
`RB2701.SHF`, and `RB_DOMINANT.SHF`; symbols pass through unchanged.

## Wrapped Endpoints

**Bars**

- `fetch_market_data(symbol, start_date, end_date, type="stock", adjust="none")`: routes
  `stock` to `get_stock_daily` (`adjust="pre"`/`"post"` to `get_stock_daily_pre`/`_post`),
  `index` to `get_index_daily`, `future` to `get_future_daily` (includes `settlement`).
  `indicator` and `st` apply to stocks only.
- `fetch_market_min_data(symbol, start_date, end_date, symbol_type="stock", frequency="1m", adjust="none")`:
  routes `stock` to `get_stock_min` (`_pre`/`_post` with `adjust`), `index` to `get_index_min`
  (1m only), `future` to `get_future_min`, `fund` to `get_fund_min`.
- `get_future_daily_post(start_date, end_date, underlying_symbol="RB", method="close_pcs")`:
  backward-adjusted dominant-continuous daily bars (`RB_DOMINANT.SHF`, actual contract in `dominant_id`).
- `get_future_detail(symbol, fields=..., exchange=..., date=...)`: contract multiplier,
  `trading_hours`, `market_tplus`, margin rate.
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
| `pandaai-01-overview-setup.md` | coverage, install, auth, endpoint map | `init_token` |
| `pandaai-02-trading-tools.md` | calendars and trade lists | `get_trade_cal`, `get_trade_list` |
| `pandaai-03-a-share-market.md` | A-share and index bars | `get_stock_daily*`, `get_stock_min*`, `get_index_daily`, `get_index_min` |
| `pandaai-04-a-share-reference.md` | stock/index metadata, industries, concepts | `get_stock_detail`, `get_index_weights` |
| `pandaai-05-a-share-trading-ipo-bonds.md` | flows, IPOs, convertible bonds | `get_lhb_list`, `get_margin` |
| `pandaai-06-a-share-corporate.md` | corporate actions and holders | `get_top_holders`, `get_stock_dividend` |
| `pandaai-07-a-share-financials.md` | financial reports | `get_fina_reports` |
| `pandaai-08-futures.md` | futures bars, contracts, dominant contracts | `get_future_daily`, `get_future_min`, `get_future_detail`, `get_future_dominant` |
| `pandaai-09-futures-deepview.md` | futures positioning and fundamentals | `get_future_basis`, `get_future_inventory` |
| `pandaai-10-options.md` | options | `get_option_daily` |
| `pandaai-11-factors-adjustment.md` | factors and adjustment events | `get_factor`, `get_adj_factor` |
| `pandaai-12-hk-us.md` | HK/US data | `get_hk_daily`, `get_us_daily` |
| `pandaai-13-funds-etf.md` | fund metadata, bars, ETF creation/redemption | `get_fund_detail`, `get_fund_daily*`, `get_fund_min`, `get_fund_etf_*` |
| `pandaai-14-macro.md` | macro data | `get_macro_*` |
| `pandaai-15-preferred-stock.md` | preferred stock | `get_stock_preferred_*` |

## Recipes

**Daily A-share bars**

```python
from skills.ingest import PandaDataClient

client = PandaDataClient()
df = client.fetch_market_data("600000.SH", "20230101", "20231231", type="stock")
```

**Daily ETF bars**

```python
from skills.ingest import PandaDataClient

client = PandaDataClient()
df = client.get_fund_daily(
    "20250610",
    "20250613",
    symbol="510300.SH",
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
raw = client.fetch_market_data("600000.SH", "20230101", "20231231", type="stock")

bars = raw.copy()
bars["eob"] = pd.to_datetime(bars["date"])
bars = bars.set_index("eob")[["open", "high", "low", "close", "volume"]].sort_index()

DataManager().save_symbol("600000.SH", bars, frequency="1d", source="panda_data")
```

When saving adjusted bars, pass the storage directory key, for example
`frequency="1d_adj"`, to `DataManager`; the fetch frequency stays `1d`.

The same store boundary applies to listed funds: normalize the returned
`date` column to the timezone-naive `eob` index, keep OHLCV columns, and call
`DataManager.save_symbol`. `PandaDataClient` never writes local files.

