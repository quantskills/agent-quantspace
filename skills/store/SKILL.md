---
name: store
description: Use when tasks need local market Parquet data, factor artifacts, backtest data, or model files through DataManager.
---

# Store

`skills/store` owns reusable file storage for market data and generic research
artifacts. The public project uses explicit strategy universes and does not
maintain a central universe registry.

## DataManager

```python
from skills.store.data_manager import DataManager, DataQualityReport, validate_ohlcv
from skills.store.workspace import resolve_workspace_paths
```

The data root comes from `QUANTSPACE_DATA_ROOT`, otherwise the repository
`data/` directory.

`resolve_workspace_paths()` centralizes `QUANTSPACE_WORKSPACE_ROOT`,
`QUANTSPACE_DATA_ROOT`, and `QUANTSPACE_REPORTS_ROOT` without creating any
directories. Runtime entrypoints use it instead of modifying `sys.path` or
independently guessing the repository root.

Supported layout:

```text
data/market/<frequency>/<symbol>.parquet
data/adj_factor/<symbol>.parquet
data/factors/<namespace>/
data/correlation/
data/backtest/
data/models/
data/export/
```

The subdirectory below `data/market/` is a storage directory/data-set key. Its
base part is the real bar frequency, while an optional `_adj` suffix records
the price-adjustment state:

| Directory key | Real `freq` | Meaning |
|---------------|-------------|---------|
| `1d` | `1d` | Daily unadjusted (raw) bars |
| `1d_adj` | `1d` | Adjusted daily bars |
| `5m` | `5m` | 5-minute unadjusted bars |
| `5m_adj` | `5m` | Adjusted 5-minute bars |

Therefore `data/market/1d_adj/` does **not** represent a frequency named
`1d_adj`; its `freq` is still `1d`, and `1d_adj` is only the directory name
indicating adjusted `1d` data. The same convention applies to other bar
intervals: `<freq>_adj` stores adjusted bars whose actual frequency is
`<freq>`.

`DataManager` names its directory-selector parameter `frequency`. Pass the full directory key to `read_symbol` / `read_symbols` /
`save_symbol` (for example, `frequency="1d_adj"`) so it resolves the intended
path. Do not reuse that suffixed value as the semantic `freq` or pass it to an
upstream market-data API; use `freq="1d"` there.

Main methods:

- `read_symbol`, `read_symbols`, `save_symbol`
- `import_symbol_csv`, `import_combined_csv`, `list_symbols`
- `save_factor`, `read_factor`, `factor_namespace_dir`, `factor_filename`
- `save_factor_correlation`, `read_factor_correlation`
- `save_backtest_run`, `read_backtest_summary`, `read_backtest_run`
- `list_models`, `read_model_metadata`

`read_symbols` returns a MultiIndex `(symbol, eob)` panel and reports every
missing symbol in one `FileNotFoundError`.

`DataManagerArtifactStore` (`skills.factor_mining.adapters.store`) persists
factor-mining research artifacts under
`data/factors/<namespace>/artifacts/<kind>/<artifact_id>.json` (path segments are
validated; resolved paths must stay under that namespace). It reuses
`save_factor` / `factor_filename` for explicit wide-pivot caches keyed by a
content-addressed `cache_key`. `DataManager.namespaced_artifact_dir(namespace,
*parts)` is the generic helper that returns (and creates)
`data/factors/<namespace>/<parts...>/`; there is no second catalog.

```python
from skills.store.data_manager import DataManager

panel = DataManager().read_symbols(
    ["SHSE.510300", "SHSE.510500"],
    frequency="1d_adj",
)
```

## Boundary Rules

- Keep market and generic research files here.
- Pass strategy universes as explicit symbol lists owned by the caller.
- Treat factor/backtest/model subdirectory names as artifact namespaces, not
  centrally managed instrument universes.
- Do not add strategy identity schemas or a second experiment catalog.

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

### `uv run qs store info`

Inspect the local data store inventory.

Priority: P0. Side effects: read-only.

| Option | Type / default | Description |
|---|---|---|
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |

Output data fields: `data_root`, `exists`, `frequencies`, `adj_factors`, `namespaces`.

Inspect schemas: `uv run qs schema store.info` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs store list`

List stored market symbols, adjustment factors, or models.

Priority: P0. Side effects: read-only.

| Option | Type / default | Description |
|---|---|---|
| `--kind` | `market\|adj-factor\|models` / `market` | Stored item kind. |
| `--frequency` | `string` / `1d` | Directory under data/market: real bar frequency plus optional _adj suffix, for example 1d, 1d_adj, 5m. |
| `--namespace` | `string?` / `null` | Model artifact namespace; required for models. |
| `--prefix` | `string?` / `null` | Optional name prefix. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |
| `--limit` | `integer` / `100` | Maximum items per page. |
| `--offset` | `integer` / `0` | Number of matching items to skip. |

Output data fields: `kind`, `items`, `count`, `truncated`, `next_offset`.

Inspect schemas: `uv run qs schema store.list` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs store read`

Read stored symbols into a (symbol, eob) panel.

Priority: P0. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--symbols` | `list[string]` / `factory` | QuantSpace symbols such as SHSE.510300; repeat flag or comma-separate. |
| `--symbols-file` | `path?` / `null` | Text lines or JSON list of QuantSpace symbols. |
| `--frequency` | `string` / `1d` | Directory under data/market: real bar frequency plus optional _adj suffix, for example 1d, 1d_adj, 5m. |
| `--start` | `string?` / `null` | Inclusive start date. |
| `--end` | `string?` / `null` | Inclusive end date. |
| `--fields` | `list[string]` / `factory` | Columns to retain. |

Output data fields: `symbols`, `frequency`, `rows`, `start`, `end`, `columns`, `missing`, `preview`.

Inspect schemas: `uv run qs schema store.read` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs store import`

Import market bars from CSV into data/market.

Priority: P1. Side effects: writes-store.

| Option | Type / default | Description |
|---|---|---|
| `--file` | `path` / `required` | Input CSV file, as accepted by DataManager.import_*_csv. |
| `--layout` | `single\|combined` / `single` | single: one symbol per file (import_symbol_csv); combined: a symbol column splits the file (import_combined_csv). |
| `--symbol` | `string?` / `null` | QuantSpace symbol for single layout. |
| `--frequency` | `string` / `1d` | Directory under data/market: real bar frequency plus optional _adj suffix, for example 1d, 1d_adj, 5m. |
| `--symbol-col` | `string` / `symbol` | Symbol column for combined layout. |
| `--time-col` | `string` / `eob` | Timestamp column. Values are parsed as UTC (offset-aware values keep their offset) and stored as naive Asia/Shanghai time, exactly like DataManager.import_*_csv. |
| `--write` | `boolean` / `false` | Write into managed market storage; otherwise a dry run. |
| `--overwrite` | `boolean` / `false` | Allow replacing existing symbol files. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |

Output data fields: `symbols`, `rows`, `saved`, `dry_run`, `frequency`, `planned_paths`, `existing`.

Inspect schemas: `uv run qs schema store.import` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs store validate`

Validate OHLCV quality; exit 1 when a check fails.

Priority: P1. Side effects: read-only.

| Option | Type / default | Description |
|---|---|---|
| `--file` | `path?` / `null` | OHLCV Parquet/CSV file to validate. |
| `--symbols` | `list[string]` / `factory` | Stored symbols to validate. |
| `--frequency` | `string` / `1d` | Directory under data/market: real bar frequency plus optional _adj suffix, for example 1d, 1d_adj, 5m. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |

Output data fields: `passed`, `n_rows`, `nan_count`, `inf_count`, `negative_price_count`, `negative_volume_count`, `high_lt_low_count`, `non_monotonic_index`, `details`.

Inspect schemas: `uv run qs schema store.validate` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs store check-adjusted`

Scan adjusted bars for zero-volume price jumps; exit 1 when found.

Priority: P1. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--symbols` | `list[string]` / `factory` | QuantSpace symbols such as SHSE.510300; repeat flag or comma-separate. |
| `--symbols-file` | `path?` / `null` | Text lines or JSON list of QuantSpace symbols. |
| `--frequency` | `string` / `1d_adj` | Adjusted market store directory. |
| `--threshold` | `number` / `0.2` | Relative price jump threshold. |

Output data fields: `symbols`, `missing`, `issues`, `preview`.

Inspect schemas: `uv run qs schema store.check-adjusted` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs store query`

Run DuckDB SQL over stored Parquet files (needs --extra query).

Priority: P2. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--sql` | `string` / `required` | DuckDB SQL; {data} is replaced by the data root, as in DataManager.query. |
| `--params` | `list[any]` / `factory` | Positional parameters bound as $1, $2, ... |

Output data fields: `rows`, `columns`, `preview`.

Inspect schemas: `uv run qs schema store.query` (add `--part input|output` or `--file-field FIELD`).

<!-- END GENERATED: qs commands -->
