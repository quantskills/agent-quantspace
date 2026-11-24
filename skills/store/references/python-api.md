# Store Python API

Read this when changing the `store` Skill or writing strategy code. For research tasks use the `uv run qs store` commands in [../SKILL.md](../SKILL.md).

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

- `read_symbol`, `read_symbols`, `save_symbol`, `upsert_symbol`
- `save_dominant(symbol, contracts)`, `read_dominant(symbols)`, `dominant_path`:
  the actual contract per trading day of continuous futures symbols, stored
  under `market/dominant/<symbol>.parquet`; `save_dominant` merges by date,
  `read_dominant` returns the trading day by symbol table that
  `VectorBacktester(unit="lots", contracts=...)` takes
- `import_symbol_csv`, `import_combined_csv`, `list_symbols`
- `save_factor`, `read_factor`, `factor_namespace_dir`, `factor_filename`
- `save_factor_correlation`, `read_factor_correlation`
- `save_backtest_run`, `read_backtest_summary`, `read_backtest_run`
- `list_models`, `read_model_metadata`

`read_symbols` returns a MultiIndex `(symbol, eob)` panel and reports every
missing symbol in one `FileNotFoundError`.

`upsert_symbol(symbol, bars, frequency="1d", *, keep_last=None, compare=OHLCV,
tolerance=0.0)` merges bars into the stored file by `eob` instead of replacing
it: incoming bars replace stored bars at the same `eob`, other stored bars stay,
and `keep_last` keeps only the newest bars afterwards. The returned
`UpsertReport` has `added`, `replaced`, `dropped`, `rows`, and `changed` (one
row per overlapping bar and `compare` column whose value moved by more than
`tolerance`), so a caller can tell a provider rewriting history from an append.
Extra columns such as `source` are kept, timezone-aware or duplicate `eob`
values are refused, and the file is replaced atomically. Live minute
strategies use it on their own store:

```python
from skills.store.data_manager import DataManager

live = DataManager("data/live/rb_ma_cross_5m", create_layout=False)
report = live.upsert_symbol("RB_DOMINANT.SHF", bars, "5m", keep_last=345)
```

`DataManager(data_root, create_layout=False)` points at another root that uses
the `market/<frequency>/` layout without creating the research directories.

`save_symbol`, `upsert_symbol` and `save_dominant` write through
`skills.store.files.write_parquet_atomic`: a temporary file next to the target,
then `replace_file`, so a reader sees the old file or the new one, never half of
one. `replace_file` is `os.replace` retried for about two seconds while Windows
reports the target in use (another process reading it, an antivirus scan); the
live_trade state files use it too.

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
    ["510300.SH", "510500.SH"],
    frequency="1d_adj",
)
```

## Legacy symbol migration

```python
from datetime import date

from skills.store.legacy_symbols import (
    apply_symbol_migration,
    legacy_to_panda_data,
    plan_symbol_migration,
)

assert legacy_to_panda_data("SHSE.510300") == "510300.SH"
assert legacy_to_panda_data("SHFE.RB99") == "RB_DOMINANT.SHF"
assert legacy_to_panda_data("510300.SH") is None  # already a PandaData code
# Zhengzhou: PandaData uses a four-digit year-month; as_of picks the decade.
assert legacy_to_panda_data("CZCE.CF509", as_of=date(2025, 9, 12)) == "CF2509.CZC"
assert legacy_to_panda_data("CZCE.CF009", as_of=date(2020, 9, 14)) == "CF2009.CZC"

plan = plan_symbol_migration(dm.root)    # list[Rename(source, target, conflict)]
renamed = apply_symbol_migration(plan)   # renames entries without a conflict
```

This module is the only code that knows the legacy `<EXCHANGE>.<CODE>` format.
A three-digit Zhengzhou code gets the year ending in its digit within five years
before and four years after `as_of` (default: today in Asia/Shanghai).
`plan_symbol_migration` passes each such file's last bar date, so old contracts
keep their decade. It marks an entry as a conflict when its target exists or an
earlier entry already renames another legacy file to it.
`DataManager.read_symbol`, `read_symbols`, and `read_adj_factor` append a
migration hint to `FileNotFoundError` when the directory still holds legacy
names.

## Boundary Rules

- Keep market and generic research files here.
- Pass strategy universes as explicit symbol lists owned by the caller.
- Treat factor/backtest/model subdirectory names as artifact namespaces, not
  centrally managed instrument universes.
- Do not add strategy identity schemas or a second experiment catalog.
