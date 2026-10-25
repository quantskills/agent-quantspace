---
name: research
description: >
  Use when tasks need reusable research pipeline templates, factor screening,
  or parameter sensitivity sweeps.
---

# Research Templates

## Components

| Function | Module | Description |
|----------|--------|-------------|
| `screen_all_indicators` | `factor_screening.py` | Batch-compute indicators on an explicit panel and return IC/IR ranking |
| `param_sweep` | `param_sensitivity.py` | Grid-sweep one factor parameter on an explicit panel |

## Usage

```python
from skills.research.factor_screening import screen_all_indicators
from skills.research.param_sensitivity import param_sweep
```

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Transport: `--input-json FILE|-`, `--preview N`, and `--log-level LEVEL`; flags override JSON. Use `--print-template [FIELD]` for fillable templates.

### Shared parameter groups

#### `PanelSource`

| Option | Type / default | Description |
|---|---|---|
| `--panel` | `path?` / `null` | Parquet/CSV panel, mutually exclusive with symbols or symbols-file. |
| `--symbols` | `list[string]` / `factory` | QuantSpace symbols such as SHSE.510300; repeat flag or comma-separate. |
| `--symbols-file` | `path?` / `null` | Text lines or JSON list of QuantSpace symbols. |
| `--frequency` | `string` / `1d` | Market store directory under data/market, for example 1d or 1d_adj. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |
| `--start` | `string?` / `null` | Inclusive start date: YYYY-MM-DD or YYYYMMDD. |
| `--end` | `string?` / `null` | Inclusive end date: YYYY-MM-DD or YYYYMMDD. |
| `--fields` | `list[string]` / `factory` | Optional panel field subset. |

### `uv run qs research screen`

Screen indicators on a panel and rank them by |IC_IR|.

Priority: P1. Side effects: writes-store.

Shared parameters: `PanelSource`.

| Option | Type / default | Description |
|---|---|---|
| `--namespace` | `string` / `required` | Artifact namespace under data/factor_test. |
| `--horizon` | `integer` / `5` | Holding period n for the IC. |
| `--groups` | `integer` / `5` | Number of groups g for group_stat. |
| `--top-k` | `integer` / `0` | Keep the top_k by \|IC_IR\|; 0 keeps all. |
| `--indicators` | `list[string]` / `factory` | Indicator subset; empty screens every indicator. |
| `--write` | `boolean` / `false` | Persist each indicator's IC, group returns and turnover under data/factor_test/<namespace>/ (persist=True); otherwise the store is not touched. |
| `--output` | `path?` / `null` | Optional full ranking table. |
| `--overwrite` | `boolean` / `false` | Replace an existing ranking file. |

Output data fields: `rows`, `persisted`, `ranking`.

Inspect schemas: `uv run qs schema research.screen` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs research batch-screen`

Screen indicators across namespace panels and holding periods.

Priority: P2. Side effects: writes-store.

| Option | Type / default | Description |
|---|---|---|
| `--panels` | `object` / `required` | Panel files by artifact namespace, e.g. etf=etf_panel.parquet. |
| `--n-list` | `list[integer]` / `factory` | Holding periods screened per namespace. |
| `--groups` | `integer` / `5` | Number of groups g for group_stat. |
| `--indicators` | `list[string]` / `factory` | Indicator subset; empty screens every indicator. |
| `--write` | `boolean` / `false` | Persist each indicator's IC, group returns and turnover under data/factor_test/<namespace>/ (persist=True); otherwise the store is not touched. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |
| `--output` | `path?` / `null` | Optional combined ranking table. |
| `--overwrite` | `boolean` / `false` | Replace an existing ranking file. |

Output data fields: `rows`, `persisted`, `ranking`.

Inspect schemas: `uv run qs schema research.batch-screen` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs research param-sweep`

Sweep one factor parameter and report IC statistics per value.

Priority: P1. Side effects: read-only.

Shared parameters: `PanelSource`.

| Option | Type / default | Description |
|---|---|---|
| `--indicator` | `string?` / `null` | Public skills.compute indicator name. |
| `--function` | `string?` / `null` | Importable module:name factor callable. |
| `--call` | `per-symbol\|panel` / `per-symbol` | per-symbol: Factor(func, **kwargs).calculate(panel, dropna=False); panel: func(panel, **kwargs) as param_sweep calls it. |
| `--param-name` | `string` / `required` | Parameter to sweep. |
| `--param-range` | `list[any]` / `required` | Values swept, in order; flag values are JSON-decoded, so 20 is an integer. |
| `--params` | `object` / `factory` | Other keyword arguments held fixed (base_kwargs). |
| `--horizon` | `integer` / `5` | Holding period n for the IC. |

Output data fields: `rows`, `failed`.

Inspect schemas: `uv run qs schema research.param-sweep` (add `--part input|output` or `--file-field FIELD`).

<!-- END GENERATED: qs commands -->
