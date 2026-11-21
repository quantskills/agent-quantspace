---
name: ingest
description: Download stock, index, futures, listed-fund and ETF, HK and US bars, adjustment factors, reference data, ETF creation and redemption data, and futures ticks from PandaData with `uv run qs ingest ...`, and store bars locally.
---

# Ingest

Use the `uv run qs ingest` commands below; data tasks do not require reading
`skills/ingest/` source. Each command prints one JSON envelope on stdout (`ok`,
`data`, `artifacts`, `warnings`, or `error` with a `hint`). Exact options:
`uv run qs ingest <command> --help` or `uv run qs schema ingest.<command>`.

## Prerequisites

- Install the SDK with `uv sync --extra panda_data`.
- Set `PANDA_DATA_USERNAME` and `PANDA_DATA_PASSWORD` in the environment or
  `.env`. Credentials are never passed as command flags.

## When to use

- Download daily or minute bars and store them under `data/market/`.
- Download adjustment-factor events for stocks.
- Look up stock, fund, index, industry, or concept reference data.
- Fetch ETF creation and redemption limits, flows, baskets, or lists.
- Call a PandaData SDK function that has no dedicated command.
- Download futures tick data.

## Workflow

```bash
uv run qs ingest bars --asset fund --symbols 510300.SH,518880.SH \
  --start 2019-01-01 --adjust post --save-frequency 1d_adj --write
uv run qs ingest bars --asset stock --symbols 600000.SH --start 2023-01-01 \
  --end 2023-12-31 --save-frequency 1d --write
uv run qs ingest adj-factor --symbols 600000.SH --write
uv run qs compute adjust --symbols 600000.SH --frequency 1d --write
uv run qs store validate --symbols 600000.SH
uv run qs ingest ref fund-detail --output out/fund_detail.parquet
uv run qs ingest etf list --start 2025-06-10 --end 2025-06-13 --output out/etf_cr.parquet
uv run qs ingest raw --list
uv run qs ingest raw --method get_trade_cal --params '{"start_date": "20250101", "end_date": "20250131"}' \
  --output out/trade_cal.parquet
uv run qs ingest future-ticks --underlying SA --start 2025-01-01 --end 2025-01-31
```

## Files

- `bars --save-frequency <directory> --write` stores one
  `data/market/<directory>/<symbol>.parquet` per symbol with a timezone-naive `eob` index and OHLCV columns. `--output` writes
  one table outside the store instead. Without `--write` the command only
  reports the planned paths.
- `adj-factor --write` stores `data/adj_factor/<symbol>.parquet`.
- Reference and ETF commands write the returned table to `--output`.
- `future-ticks` writes under `data/export/panda_future_ticks/<underlying>/`.

## Rules

- Listed ETFs and LOFs are funds: use `--asset fund`, never `--asset stock`.
  The `ingest etf` commands return creation and redemption data, not price bars.
- `--freq` is the real bar interval sent to PandaData (`1d`, `1m`, `5m`, ...).
  `1d_adj` is only the store directory for adjusted daily bars and is never
  sent to the provider.
- Symbols are PandaData codes in both directions and are never converted:
  `510300.SH`, `600000.SH`, `RB2701.SHF`, `CF509.CZC` (Zhengzhou contracts use a
  three-digit year-month), dominant continuous `RB_DOMINANT.SHF`. Stored files
  and returned `symbol` columns use the same codes.
- Each asset class uses its dedicated PandaData endpoint, as listed at
  https://www.pandaaiquant.com/docs/api: `get_stock_daily*`, `get_index_daily`,
  `get_future_daily`, `get_fund_daily*` for daily bars and `get_stock_min*`,
  `get_index_min`, `get_future_min`, `get_fund_min` for minute bars. Never call
  the old `get_market_data` or `get_market_min_data`: futures requests through
  them fail with error 200103 even when the account holds the futures permission.
- Stocks, funds (listed ETFs), indexes (1m only) and futures have minute bars;
  HK and US are daily only. `--adjust pre|post` applies to stock bars and daily
  fund bars. The provider caps the rows of one minute request: split long
  ranges across runs.
- PandaData publishes daily and minute bars once a day after the close (each
  endpoint page lists its update window, for example stock minute bars
  15:57-16:17 and futures minute bars 16:41-17:01); they are not an intraday feed.
- Commands that reach the network are marked `network` in the command list
  below; they fail with a hint when credentials are missing.

## References

Open only the file needed for the task.

| Reference | Open when you need |
|-----------|--------------------|
| [references/python-api.md](references/python-api.md) | `PandaDataClient` methods and Python recipes, when changing this Skill or writing code |
| `references/pandaai-01-overview-setup.md` | Coverage, SDK install and upgrade, authentication, which endpoint serves which bars |
| `references/pandaai-02-trading-tools.md` | Trading calendar, previous trading dates, ST and suspension lists, listed stocks |
| `references/pandaai-03-a-share-market.md` | A-share daily, weekly, monthly and minute bars (with adjustment), tick stream; index daily and minute bars |
| `references/pandaai-04-a-share-reference.md` | Stock and index details, industries, concepts, index weights and valuation |
| `references/pandaai-05-a-share-trading-ipo-bonds.md` | Dragon-tiger lists, margin, Stock Connect, money flow, IPOs, convertible bonds |
| `references/pandaai-06-a-share-corporate.md` | Corporate actions, dividends, splits, holders, pledges |
| `references/pandaai-07-a-share-financials.md` | Earnings forecasts, flash reports, financial statements, audit opinions |
| `references/pandaai-08-futures.md` | Futures daily, minute and post-adjusted bars, tick stream, contract details, dominant contracts |
| `references/pandaai-09-futures-deepview.md` | Futures broker positions, basis, warehouse receipts, inventory, term structure |
| `references/pandaai-10-options.md` | Option details, daily bars, volatility, trading statistics |
| `references/pandaai-11-factors-adjustment.md` | Backtest factors, adjustment factors, Barra style factors, risk-free rate |
| `references/pandaai-12-hk-us.md` | HK and US bars, details, events, holders, financials, ETFs, indexes, warrants |
| `references/pandaai-13-funds-etf.md` | Fund details, daily and minute bars, ETF creation and redemption, holdings, performance |
| `references/pandaai-14-macro.md` | China and global macro indicators, industry macro data, economic calendar |
| `references/pandaai-15-preferred-stock.md` | Preferred stock |

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs ingest bars` | Fetch stock, index, future, fund, HK or US bars; optionally store them. | network, writes-output, writes-store |
| `uv run qs ingest adj-factor` | Fetch stock adjustment-factor events; optionally store them per symbol. | network, writes-output, writes-store |
| `uv run qs ingest ref stock-detail` | Fetch stock basic information (get_stock_detail). | network, writes-output |
| `uv run qs ingest ref fund-detail` | Fetch fund and ETF metadata (get_fund_detail). | network, writes-output |
| `uv run qs ingest ref index-detail` | Fetch index basic information (get_index_detail). | network, writes-output |
| `uv run qs ingest ref index-indicator` | Fetch index valuation indicators (get_index_indicator). | network, writes-output |
| `uv run qs ingest ref index-weights` | Fetch index constituent weights (get_index_weights). | network, writes-output |
| `uv run qs ingest ref industry-detail` | Fetch the industry taxonomy (get_industry_detail). | network, writes-output |
| `uv run qs ingest ref industry-constituents` | Fetch industry constituents (get_industry_constituents). | network, writes-output |
| `uv run qs ingest ref stock-industry` | Fetch one stock's industry classification (get_stock_industry). | network, writes-output |
| `uv run qs ingest ref concept-list` | Fetch the concept list (get_concept_list). | network, writes-output |
| `uv run qs ingest ref concept-constituents` | Fetch concept constituents (get_concept_constituents). | network, writes-output |
| `uv run qs ingest etf limits` | Fetch ETF creation/redemption limits (get_fund_etf_cr_limits). | network, writes-output |
| `uv run qs ingest etf net` | Fetch ETF net creation/redemption and fund flows (get_fund_etf_cr_net). | network, writes-output |
| `uv run qs ingest etf constituents` | Fetch ETF creation/redemption baskets (get_fund_etf_constituents). | network, writes-output |
| `uv run qs ingest etf list` | Fetch ETF creation/redemption lists (get_fund_etf_cr). | network, writes-output |
| `uv run qs ingest raw` | Call any public panda_data SDK function, or list them. | network, writes-output |
| `uv run qs ingest future-ticks` | Run the long-running futures tick downloader; exit 1 when tasks fail. | network, writes-output |

<!-- END GENERATED: qs commands -->
