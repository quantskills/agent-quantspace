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

## Workflow

```bash
uv run qs store info
uv run qs store list --frequency 1d_adj --limit 200
uv run qs store read --symbols SHSE.510300,SHSE.518880 --frequency 1d_adj \
  --start 2019-01-01 --output out/panel.parquet
uv run qs store validate --symbols SHSE.510300,SHSE.518880
uv run qs store check-adjusted --symbols SHSE.510300 --frequency 1d_adj \
  --output out/adjusted_issues.parquet
uv run qs store import --file bars.csv --layout single --symbol SHSE.510301            # dry run
uv run qs store import --file bars.csv --layout single --symbol SHSE.510301 --write
uv run qs store query \
  --sql "SELECT count(*) AS n FROM read_parquet('{data}/market/1d/SHSE.510300.parquet') WHERE volume > \$1" \
  --params '[0]' --output out/query.parquet
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
suffix for adjusted prices.

| Directory key | Real interval | Meaning |
|---------------|---------------|---------|
| `1d` | `1d` | Daily unadjusted bars |
| `1d_adj` | `1d` | Adjusted daily bars |
| `5m` | `5m` | 5-minute unadjusted bars |
| `5m_adj` | `5m` | Adjusted 5-minute bars |

`read` writes a `(symbol, eob)` panel; `eob` is the timezone-naive end of bar.

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

<!-- END GENERATED: qs commands -->
