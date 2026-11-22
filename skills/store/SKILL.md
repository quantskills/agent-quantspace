---
name: store
description: Inspect, read, import, validate, and query the local Parquet market store (daily and intraday bars, adjusted bars, adjustment factors) with `uv run qs store ...`.
---

# Store

Use the `uv run qs store` commands below; research tasks do not require reading
`skills/store/` source. Each command prints one JSON envelope on stdout (`ok`,
`data`, `artifacts`, `warnings`, or `error` with a `hint`). Exact options:
`uv run qs store <command> --help` or `uv run qs schema store.<command>`.

## When to use

- See which frequencies and symbols exist locally.
- Read symbols into one panel file for other commands.
- Import CSV or Parquet bars into the store.
- Check OHLCV quality, or check adjusted bars against raw bars.
- Run a read-only SQL query over the store.
- Rename a store written by older versions (`SHSE.510300.parquet`) to PandaData codes.

## Workflow

```bash
uv run qs store info
uv run qs store list --frequency 1d_adj --limit 200
uv run qs store read --symbols 510300.SH,518880.SH --frequency 1d_adj \
  --start 2019-01-01 --output out/panel.parquet
uv run qs store validate --symbols 510300.SH,518880.SH
uv run qs store check-adjusted --symbols 510300.SH --frequency 1d_adj \
  --output out/adjusted_issues.parquet
uv run qs store import --file bars.csv --layout single --symbol 510301.SH            # dry run
uv run qs store import --file bars.csv --layout single --symbol 510301.SH --write
uv run qs store query \
  --sql "SELECT count(*) AS n FROM read_parquet('{data}/market/1d/510300.SH.parquet') WHERE volume > \$1" \
  --params '[0]' --output out/query.parquet
uv run qs store migrate-symbols            # dry run: legacy name -> PandaData code
uv run qs store migrate-symbols --write
```

## Files

The data root is `QUANTSPACE_DATA_ROOT`, otherwise the repository `data/`
directory:

```text
data/market/<frequency>/<symbol>.parquet
data/adj_factor/<symbol>.parquet
data/factors/<namespace>/
data/backtest/
data/models/
data/export/
```

`<frequency>` is a directory key: the real bar interval plus an optional `_adj`
suffix for adjusted prices. Live strategies keep their own bars under
`data/live/<strategy-id>/market/<frequency>/` in the same layout; that store
belongs to the `live-trade` Skill and these commands never read or write it.

| Directory key | Real interval | Meaning |
|---------------|---------------|---------|
| `1d` | `1d` | Daily unadjusted bars |
| `1d_adj` | `1d` | Adjusted daily bars |
| `5m` | `5m` | 5-minute unadjusted bars |
| `5m_adj` | `5m` | Adjusted 5-minute bars |

`read` writes a `(symbol, eob)` panel; `eob` is the timezone-naive end of bar.

File names are the symbol. PandaData data uses PandaData codes: `510300.SH`,
`600000.SH`, `000300.SH`, `RB2601.SHF`, dominant continuous `RB_DOMINANT.SHF`.
Data from other sources keeps whatever symbol the caller imports it under.

## Rules

- Pass the full directory key to `--frequency` (for example `1d_adj`). Never
  send a suffixed key to a data provider: the ingest frequency stays `1d`.
- `read` reports every missing symbol at once instead of returning a partial
  panel.
- `query` runs DuckDB SQL; `{data}` in the SQL is replaced by the data root and
  `--params` are bound as `$1`, `$2`, and so on.
- `import` is a dry run unless `--write` is given. `--output` paths never point
  into the managed store.
- Strategy universes are explicit symbol lists owned by the caller; the store
  keeps no universe registry and no experiment catalog.
- Stores written before the switch to PandaData codes name files
  `SHSE.510300`, `SHFE.RB99`, and so on. Reads that miss a file say so and point
  to `migrate-symbols`. It renames files under `market/*/` and `adj_factor/`
  (contents are unchanged), skips names that are already PandaData codes, never
  overwrites, and reports a conflict when both names exist. Running it again
  changes nothing. Symbols written inside your own scripts or exported CSV files
  are not touched: the dry run lists each `old -> new` pair to replace them.
- PandaData writes every futures contract with a four-digit year-month,
  Zhengzhou included (`CF2509.CZC`), and refuses `CF509.CZC`. A legacy
  three-digit Zhengzhou name such as `CZCE.CF509` becomes `CF2509.CZC`: the
  year is the one ending in that digit within five years before and four years
  after the file's last bar (today's date for a file without bars). Check those
  pairs in the dry run. When `CZCE.CF2509` and `CZCE.CF509` both exist, the
  second is reported as a conflict and kept.

## References

- [references/python-api.md](references/python-api.md): `DataManager` methods,
  workspace path resolution, and factor-mining artifact storage. Read it when
  changing this Skill or writing strategy code.

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs store info` | Inspect the local data store inventory. | read-only |
| `uv run qs store list` | List stored market symbols, adjustment factors, or models. | read-only |
| `uv run qs store read` | Read stored symbols into a (symbol, eob) panel. | writes-output |
| `uv run qs store import` | Import market bars from CSV into data/market. | writes-store |
| `uv run qs store validate` | Validate OHLCV quality; exit 1 when a check fails. | read-only |
| `uv run qs store check-adjusted` | Scan adjusted bars for zero-volume price jumps; exit 1 when found. | writes-output |
| `uv run qs store query` | Run DuckDB SQL over stored Parquet files (needs --extra query). | writes-output |
| `uv run qs store migrate-symbols` | Rename legacy 510300.SH-style store files to PandaData codes such as 510300.SH. | writes-store |

<!-- END GENERATED: qs commands -->
