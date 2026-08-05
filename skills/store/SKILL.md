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
data/factor_test/<namespace>/
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

The current `DataManager` API names its directory-selector parameter
`frequency`. Pass the full directory key to `read_symbol` / `read_symbols` /
`save_symbol` (for example, `frequency="1d_adj"`) so it resolves the intended
path. Do not reuse that suffixed value as the semantic `freq` or pass it to an
upstream market-data API; use `freq="1d"` there.

Main methods:

- `read_symbol`, `read_symbols`, `save_symbol`
- `import_symbol_csv`, `import_combined_csv`, `list_symbols`
- `save_factor`, `read_factor`, `factor_namespace_dir`, `factor_filename`
- `save_factor_test`, `read_factor_test_summary`
- `save_factor_correlation`, `read_factor_correlation`
- `save_backtest_run`, `read_backtest_summary`, `read_backtest_run`
- `list_models`, `read_model_metadata`

`read_symbols` returns a MultiIndex `(symbol, eob)` panel and reports every
missing symbol in one `FileNotFoundError`.

Factor-mining Phase 02 persists research artifacts under
`data/factors/<namespace>/artifacts/` through `DataManagerArtifactStore` (path
segments are validated; resolved paths must stay under that namespace) and may
reuse `save_factor` / `factor_filename` for explicit wide-pivot caches keyed by
content-addressed params such as `cache_key`. Phase 04 additionally uses
`DataManager.namespaced_artifact_dir` / `get_by_identity` for controller
snapshots and append-only event payloads under the same factors namespace root
(no second catalog).

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
