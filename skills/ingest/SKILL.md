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

When saving adjusted bars, pass the storage directory key, for example
`frequency="1d_adj"`, to `DataManager`; the fetch frequency stays `1d`.

The same store boundary applies to listed funds: normalize the returned
`date` column to the timezone-naive `eob` index, keep OHLCV columns, and call
`DataManager.save_symbol`. `PandaDataClient` never writes local files.

**Symbol conversion**

```python
from skills.ingest import to_panda_data_symbol, to_quantspace_symbol

assert to_panda_data_symbol("SHSE.510300") == "510300.SH"
assert to_quantspace_symbol("RB_DOMINANT.SHF") == "SHFE.RB99"
```

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Transport: `--input-json FILE|-`, `--preview N`, and `--log-level LEVEL`; flags override JSON. Use `--print-template [FIELD]` for fillable templates.

### Shared parameter groups

#### `OutputOptions`

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path?` / `null` | Explicit output path outside managed store namespaces. |
| `--overwrite` | `boolean` / `false` | Allow replacing an existing output artifact. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |

### `uv run qs ingest bars`

Fetch stock, index, future, fund, HK or US bars; optionally store them.

Priority: P0. Side effects: network, writes-output, writes-store.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--asset` | `stock\|index\|future\|fund\|hk\|us` / `required` | Asset class. Listed ETF and LOF are fund, not stock. |
| `--symbols` | `list[string]` / `factory` | QuantSpace (SHSE.510300) or native (510300.SH) symbols; repeat flag or comma-separate. |
| `--symbols-file` | `path?` / `null` | Text lines or JSON list of symbols, instead of symbols. |
| `--start` | `string` / `required` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string?` / `null` | Inclusive end date: YYYY-MM-DD or YYYYMMDD; defaults to today. |
| `--freq` | `1d\|1m\|5m\|15m\|60m` / `1d` | Real bar interval sent to PandaData (never 1d_adj). Only stock, index (1m only) and future have minute bars; the provider caps rows per minute request, so split long minute ranges across runs. |
| `--adjust` | `none\|pre\|post` / `none` | Fund price adjustment: none, pre (forward) or post (backward). Fund only. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |
| `--indicator` | `string?` / `null` | Stock pool code for daily stock bars only; empty means all stocks. |
| `--st` | `boolean` / `true` | Include ST stocks; --no-st excludes them. Daily stock bars only. |
| `--save-frequency` | `string?` / `null` | Market store directory under data/market, for example 1d or 1d_adj (adjusted 1d bars). Without --write this is a dry run that only reports planned paths. |
| `--write` | `boolean` / `false` | Write bars into data/market/<save-frequency>/<symbol>.parquet; requires --save-frequency. |

Output data fields: `asset`, `freq`, `adjust`, `start`, `end`, `requested_symbols`, `dry_run`, `saved`, `rows`, `columns`, `symbols`, `no_data`, `output`, `target_frequency`, `planned_paths`, `written_paths`, `preview`.

Inspect schemas: `uv run qs schema ingest.bars` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest adj-factor`

Fetch stock adjustment-factor events; optionally store them per symbol.

Priority: P1. Side effects: network, writes-output, writes-store.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--symbols` | `list[string]` / `factory` | Stock symbols (QuantSpace or native); empty queries the whole market. |
| `--symbols-file` | `path?` / `null` | Text lines or JSON list of symbols, instead of symbols. |
| `--start` | `string?` / `null` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string?` / `null` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |
| `--write` | `boolean` / `false` | Write one data/adj_factor/<symbol>.parquet per symbol (ex_date index). A bounded --start/--end stores only the events in that range. With neither --output nor --write the command is a dry run: nothing is fetched. |

Output data fields: `scope`, `requested_symbols`, `start`, `end`, `dry_run`, `saved`, `rows`, `columns`, `symbols`, `no_data`, `output`, `planned_paths`, `path_template`, `written_paths`, `preview`.

Inspect schemas: `uv run qs schema ingest.adj-factor` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest ref stock-detail`

Fetch stock basic information (get_stock_detail).

Priority: P1. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--symbols` | `list[string]` / `factory` | Stock symbols; empty returns all. Symbols (QuantSpace or native); repeat flag or comma-separate. |
| `--market` | `string` / `cn` | Market code passed to get_stock_detail. |
| `--status` | `integer?` / `null` | Listing status filter. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.ref.stock-detail` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest ref fund-detail`

Fetch fund and ETF metadata (get_fund_detail).

Priority: P1. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--symbols` | `list[string]` / `factory` | Fund symbols, listed or *.OF. Symbols (QuantSpace or native); repeat flag or comma-separate. |
| `--exchange` | `list[string]` / `factory` | Exchange filter, SH or SZ. |
| `--type` | `list[string]` / `factory` | Fund type filter. |
| `--operation-mode` | `list[string]` / `factory` | Operation mode filter. |
| `--etf-lof-type` | `list[string]` / `factory` | ETF or LOF subtype; ETF discovers listed ETFs. |
| `--is-class-fund` | `list[integer]` / `factory` | Class-fund flag filter, 0 or 1. |
| `--index-fund-type` | `list[string]` / `factory` | Index fund type filter. |
| `--status` | `list[string]` / `factory` | Listing status filter, e.g. L. |
| `--fund-status` | `list[string]` / `factory` | Fund status filter. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.ref.fund-detail` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest ref index-detail`

Fetch index basic information (get_index_detail).

Priority: P1. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--symbols` | `list[string]` / `factory` | Index symbols; empty returns all. Symbols (QuantSpace or native); repeat flag or comma-separate. |
| `--status` | `integer?` / `null` | Index status filter. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.ref.index-detail` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest ref index-indicator`

Fetch index valuation indicators (get_index_indicator).

Priority: P1. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--symbols` | `list[string]` / `factory` | Index symbols; empty returns all. Symbols (QuantSpace or native); repeat flag or comma-separate. |
| `--start` | `string?` / `null` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string?` / `null` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.ref.index-indicator` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest ref index-weights`

Fetch index constituent weights (get_index_weights).

Priority: P1. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--start` | `string` / `required` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string` / `required` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--index-symbol` | `list[string]` / `factory` | Index symbols, such as SHSE.000300 (QuantSpace or native). |
| `--stock-symbol` | `list[string]` / `factory` | Constituent stock symbols to filter by. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.ref.index-weights` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest ref industry-detail`

Fetch the industry taxonomy (get_industry_detail).

Priority: P1. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--level` | `list[string]` / `factory` | Industry level filter. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.ref.industry-detail` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest ref industry-constituents`

Fetch industry constituents (get_industry_constituents).

Priority: P1. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--industry-code` | `list[string]` / `factory` | Industry code filter. |
| `--stock-symbol` | `list[string]` / `factory` | Stock symbols whose industries to list. |
| `--level` | `string?` / `null` | Industry level. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.ref.industry-constituents` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest ref stock-industry`

Fetch one stock's industry classification (get_stock_industry).

Priority: P1. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--stock-symbol` | `string` / `required` | One stock symbol, QuantSpace or native. |
| `--level` | `string?` / `null` | Industry level. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.ref.stock-industry` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest ref concept-list`

Fetch the concept list (get_concept_list).

Priority: P1. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--concept` | `list[string]` / `factory` | Concept name or code filter. |
| `--start` | `string?` / `null` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string?` / `null` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.ref.concept-list` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest ref concept-constituents`

Fetch concept constituents (get_concept_constituents).

Priority: P1. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--concept` | `list[string]` / `factory` | Concept name or code filter. |
| `--concept-stock` | `list[string]` / `factory` | Stock symbols whose concepts to list. |
| `--start` | `string?` / `null` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string?` / `null` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.ref.concept-constituents` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest etf limits`

Fetch ETF creation/redemption limits (get_fund_etf_cr_limits).

Priority: P2. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--start` | `string` / `required` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string` / `required` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--symbols` | `list[string]` / `factory` | ETF symbols; empty returns all. Symbols (QuantSpace or native); repeat flag or comma-separate. |
| `--exchange` | `list[string]` / `factory` | Exchange filter, SH or SZ. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.etf.limits` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest etf net`

Fetch ETF net creation/redemption and fund flows (get_fund_etf_cr_net).

Priority: P2. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--start` | `string` / `required` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string` / `required` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--symbols` | `list[string]` / `factory` | ETF symbols; empty returns all. Symbols (QuantSpace or native); repeat flag or comma-separate. |
| `--exchange` | `list[string]` / `factory` | Exchange filter, SH or SZ. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.etf.net` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest etf constituents`

Fetch ETF creation/redemption baskets (get_fund_etf_constituents).

Priority: P2. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--start` | `string` / `required` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string` / `required` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--symbols` | `list[string]` / `factory` | ETF symbols; empty returns all. Symbols (QuantSpace or native); repeat flag or comma-separate. |
| `--exchange` | `list[string]` / `factory` | Exchange filter, SH or SZ. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.etf.constituents` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest etf list`

Fetch ETF creation/redemption lists (get_fund_etf_cr).

Priority: P2. Side effects: network, writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--start` | `string` / `required` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string` / `required` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--symbols` | `list[string]` / `factory` | ETF symbols; empty returns all. Symbols (QuantSpace or native); repeat flag or comma-separate. |
| `--exchange` | `list[string]` / `factory` | Exchange filter, SH or SZ. |
| `--fields` | `list[string]` / `factory` | SDK fields subset; empty returns all columns. |

Output data fields: `endpoint`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.etf.list` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest raw`

Call any public panda_data SDK function, or list them.

Priority: P1. Side effects: network, writes-output.

Positional: `method`.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--method` | `string?` / `null` | Public panda_data SDK function name, such as get_trade_cal. |
| `--params` | `object` / `factory` | JSON object of keyword arguments passed unchanged to the SDK function. Symbols are NOT converted: use the SDK's native format (510300.SH). Returned symbol columns are converted to QuantSpace format. |
| `--list` | `boolean` / `false` | List the callable public SDK functions instead of calling one. |

Output data fields: `method`, `methods`, `rows`, `columns`, `output`, `preview`.

Inspect schemas: `uv run qs schema ingest.raw` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs ingest future-ticks`

Run the long-running futures tick downloader; exit 1 when tasks fail.

Priority: P2. Side effects: network, writes-output.

| Option | Type / default | Description |
|---|---|---|
| `--underlying` | `string` / `SA` | Futures underlying code, such as SA; ignored with --all-underlyings. |
| `--all-underlyings` | `boolean` / `false` | Download every underlying serially into --output-root. |
| `--start` | `string?` / `null` | Inclusive start date; defaults to about five years before today. |
| `--end` | `string?` / `null` | Inclusive end date; defaults to today. |
| `--output-dir` | `path?` / `null` | Single-underlying output directory, relative to the workspace root. Defaults to data/export/panda_future_ticks/<underlying>. |
| `--output-root` | `path?` / `null` | Root holding one subdirectory per underlying (all mode: the root itself); all-underlyings mode defaults to data/export/panda_future_ticks. |
| `--workers` | `integer?` / `null` | Worker processes; the downloader default is min(4, CPU count). |
| `--symbol-batch-size` | `integer` / `8` | Contract symbols per request batch. |
| `--progress-every` | `integer` / `1` | Progress report interval, in tasks. |
| `--max-retries` | `integer` / `3` | Retries per task. |
| `--retry-sleep` | `number` / `2.0` | Seconds between retries. |
| `--retry-failed-rounds` | `integer` / `2` | Extra rounds for failed tasks. |
| `--http-timeout` | `integer` / `60` | HTTP timeout in seconds. |
| `--stall-timeout` | `integer` / `300` | Seconds without completed futures before the pool is terminated. |
| `--provider-timeout-threshold` | `integer` / `3` | Timeouts of one symbol-day before it counts as a provider gap. |
| `--allow-provider-timeout-gaps` | `boolean` / `false` | Treat repeatedly timed-out symbol-days as acceptable gaps. |
| `--fallback-on-batch-timeout` | `boolean` / `true` | Retry a timed-out batch symbol by symbol; --no-fallback-on-batch-timeout disables it. |
| `--compression` | `string` / `zstd` | Parquet compression codec. |
| `--compression-level` | `integer` / `9` | Parquet compression level. |
| `--overwrite` | `boolean` / `false` | Discard existing tick outputs and download again; otherwise resume. |
| `--include-dominant` | `boolean` / `false` | Include dominant continuous contracts. |
| `--refresh-discovery` | `boolean` / `false` | Refresh contract discovery. |
| `--combine` | `boolean` / `true` | Write combined per-contract files; --no-combine skips them. |
| `--monthly-output` | `boolean` / `false` | Write monthly output files. |
| `--month-by-month` | `boolean` / `true` | Run month by month; --no-month-by-month disables it. |
| `--min-free-disk-gb` | `number` / `100.0` | All-underlyings mode pauses below this free disk space, in GB. |
| `--limit-tasks` | `integer` / `0` | Debug limit on tasks; 0 means no limit. |
| `--limit-underlyings` | `integer` / `0` | Debug limit on underlyings; 0 means no limit. |
| `--priority-underlyings` | `string` / `` | Comma-separated underlyings processed before the rest. |
| `--data-root` | `path?` / `null` | Managed data root, used only to keep tick output out of its store namespaces; otherwise QUANTSPACE_DATA_ROOT or repository data/. |

Output data fields: `underlying`, `all_underlyings`, `output_dir`, `status`, `exit_code`, `argv`.

Inspect schemas: `uv run qs schema ingest.future-ticks` (add `--part input|output` or `--file-field FIELD`).

<!-- END GENERATED: qs commands -->
