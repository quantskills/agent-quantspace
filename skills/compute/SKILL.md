---
name: compute
description: Use when tasks need strategy-agnostic OHLCV indicators, math utilities, regime slicing, resampling, or label makers.
---

## Description

Compute derived values from OHLCV data. This skill is organized in reusable, strategy-agnostic layers:

| Layer | Module | Contents |
|-------|--------|----------|
| **Utils** | `skills.compute.utils` | Math primitives: `safe_divide`, `rolling_zscore`, `calculate_atr`, `clip_outliers`, etc. |
| **Indicators** | `skills.compute.indicators` | 19 public technical indicators: `rsi`, `trend_score`, `er`, `supertrend`, etc. |
| **Features** | `skills.compute.features` | Strategy-agnostic OHLCV feature builders such as `make_logdiff_features` |

Also: label makers (`label_maker.py`), forward adjustment from stored adjustment factors (`adjust.py`), and the `Factor` wrapper.

Shared market-structure helpers used by strategy domains:

- `skills.compute.resample.resample_to_5m(df_1m)` — A-share 1m eob OHLCV to 5m eob bars without crossing lunch break; keeps `09:31-11:30` and `13:01-15:00`, removes zero-volume rows, and preserves OHLCV aggregation.
- `skills.compute.regime.split_by_regime(df, regimes=None)` — lithium-cycle date slicing for DatetimeIndex or MultiIndex inputs.

**Strategy-specific factors and feature engineering** live in `strategies/`, not here — except generic single-instrument OHLCV transforms such as log-difference grids, which belong in `skills.compute.features`.
The factor-mining workflow may generate new Python factor functions directly in
`strategies/<domain>/mined_factors/`; they only need to satisfy the `Factor`
callable contract below. They do not need to be added to
`skills.compute.indicators` or to any allowlist.

## Prerequisites

- **Python**: `pandas`, `numpy`.
- **Imports**:
  - `from skills.compute.indicators import trend_score, rsi, er`
  - `from skills.compute.utils import safe_divide, calculate_atr`
  - `from skills.compute.wrappers import Factor`
  - `from skills.compute.resample import resample_to_5m`
  - `from skills.compute.regime import split_by_regime`
  - `from skills.compute.features import make_logdiff_features, default_logdiff_shifts`

## API Reference

### Math Utilities (`skills.compute.utils`)

```python
from skills.compute.utils import safe_divide, rolling_zscore, calculate_atr, clip_outliers, round_away_from_zero
```

6 public functions: `safe_divide`, `rolling_zscore`, `rolling_regression_vectorized`, `calculate_atr`, `clip_outliers`, `round_away_from_zero`, plus private helpers `_weighted_polyfit_coefficients`, `_rolling_linear_regression`, `_scalar_kalman_smoother`.

### Universal Indicators (`skills.compute.indicators`)

```python
from skills.compute.indicators import trend_score, rsi, er, supertrend
```

19 public functions organized by category:

- **Price/Momentum**: `roc`, `ma`, `daily_return`, `ma_cross`, `price_above_ma`, `bias_momentum`, `mom_skip`
- **Trend**: `trend_score`, `trend_score_v2`, `trend_score_v2_skip`, `supertrend`, `donchian_channel`
- **Volume**: `orb_relvol`
- **Efficiency**: `er`
- **Oscillators**: `cci`, `slowkdj`, `williams_r`, `rsi`, `rsi_divergence`

### `Factor` wrapper (`skills.compute.wrappers`)

```python
from skills.compute.wrappers import Factor
from skills.compute.indicators import trend_score_v2
```

- `__init__(func: Callable, **params)` — binds callable and defaults; `name` from `func.__name__` and params.
- `calculate(data: pd.DataFrame, *, dropna: bool = True) -> pd.Series` — per-symbol apply with index contract checks. Pass `dropna=False` to keep warm-up NaNs and the full index (factor_mining always does).
- `cal_df(data, *, dropna: bool = True) -> pd.DataFrame` — wide pivot with `eob` index and one column per symbol; respects the same `dropna` flag. Not an authoritative research result.

`Factor` never persists files. Artifact writes belong to factor_mining store adapters.

**Contract for `func`**: first argument is a single-symbol `DataFrame` with a one-level `eob` DatetimeIndex and required OHLCV columns; return a real numeric `Series` whose index equals the input index item-for-item.

### Exit / risk filters (cross-sectional package)

```python
from skills.strategy.cross_sectional.exits import (
    gap_down_filter,
    vol_spike_filter,
    drawdown_from_high_filter,
)
```

Panel-level filters return a MultiIndex `Series`; use with `ExitFilterConfig` and `condition` in the cross-sectional backtester (see `strategies/cross_sectional/STRATEGY.md`).

## Recipes

**1. Panel factor**

```python
import pandas as pd
from skills.compute.wrappers import Factor
from skills.compute.indicators import roc, trend_score_v2

f = Factor(trend_score_v2, period=24)
scores = f.calculate(data)  # data: MultiIndex (symbol, eob)

f2 = Factor(roc, period=60)
roc_df = f2.cal_df(data)
```

**2. Direct single-symbol call**  
Slice one symbol, index by `eob` → `roc(sym_df, period=20)`.

**3. Apply a single-symbol indicator to a panel**

```python
from skills.compute.indicators import trend_score
from skills.compute.wrappers import Factor

factor = Factor(trend_score, period=25)
scores = factor.calculate(panel)
```

**4. Exit filter in a backtest**  
Pass `{'func': drawdown_from_high_filter, 'kwargs': {...}, 'condition': lambda x: x < 0.1}` in `exit_filters` on `ModularBacktester` (see strategy domain doc).

### OHLCV Features (`skills.compute.features`)

```python
from skills.compute.features import (
    default_logdiff_shifts,
    make_logdiff_features,
    make_logdiff_panel_features,
)
```

- `make_logdiff_features(bars, *, factors=..., lags=..., shifts=None, lookback=5)` — single-symbol OHLC log-difference grid. Default: 4×4 factor pairs × 9 lags × 10 shifts = **1440** columns when `lookback=5`. Non-positive prices become NaN instead of `-inf`.
- `make_logdiff_panel_features(panel, ...)` — same grid applied per symbol on a `(symbol, eob)` panel, non-finite rows dropped, so the result is model-ready. Build once and reuse across horizons/models.
- `default_logdiff_shifts(lookback)` — tuple `0..lookback-1` followed by `5, 10, ..., lookback*5` (not deduplicated).
- No duplicate log-difference implementation under `strategies/`.

### Label Generation (`skills.compute.label_maker`)

```python
from skills.compute.label_maker import ForwardReturnLabelMaker, TripleBarrierLabelMaker
```

Public supervised-learning labels:

- `ForwardReturnLabelMaker`: forward-return threshold labels.
- `TripleBarrierLabelMaker`: AFML-style volatility-scaled triple-barrier labels.

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

#### `OutputOptions`

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path?` / `null` | Explicit output path outside managed store namespaces. |
| `--overwrite` | `boolean` / `false` | Allow replacing an existing output artifact. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |

### `uv run qs compute indicators list`

List public indicators with signatures.

Priority: P0. Side effects: read-only.

| Option | Type / default | Description |
|---|---|---|

Output data fields: `indicators`.

Inspect schemas: `uv run qs schema compute.indicators.list` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs compute indicators show`

Show one indicator's signature, defaults, and docstring.

Priority: P0. Side effects: read-only.

Positional: `name`.

| Option | Type / default | Description |
|---|---|---|
| `--name` | `string` / `required` | Public indicator name. |

Output data fields: `name`, `signature`, `defaults`, `docstring`.

Inspect schemas: `uv run qs schema compute.indicators.show` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs compute factor`

Calculate an indicator or module:name factor on a panel.

Priority: P0. Side effects: writes-output.

Shared parameters: `PanelSource`, `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination factor table; values never go to stdout. |
| `--indicator` | `string?` / `null` | Public indicator name. |
| `--function` | `string?` / `null` | Importable module:name callable, e.g. a generated mined factor. |
| `--params` | `object` / `factory` | Factor keyword parameters. |
| `--call` | `per-symbol\|panel` / `per-symbol` | per-symbol: Factor(func, **params).calculate on each symbol; panel: func(panel, **params) must return a Series aligned to the panel. |
| `--keep-na` | `boolean` / `false` | Keep warm-up NaN rows (Factor dropna=False). |
| `--layout` | `long\|wide` / `long` | long: symbol, eob, value columns; wide: eob x symbol like Factor.cal_df. |

Output data fields: `name`, `rows`, `symbols`, `start`, `end`, `nan_ratio`, `output`.

Inspect schemas: `uv run qs schema compute.factor` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs compute features`

Build model-ready OHLC log-difference features for a panel.

Priority: P1. Side effects: writes-output.

Shared parameters: `PanelSource`, `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination (symbol, eob) feature table. |
| `--factors` | `list[string]` / `factory` | OHLC columns paired in log differences. |
| `--lags` | `list[integer]` / `factory` | Lags of the right-hand price. |
| `--shifts` | `list[integer]?` / `null` | Feature shifts; defaults to default_logdiff_shifts(lookback). |
| `--lookback` | `integer` / `5` | Lookback used for default shifts. |

Output data fields: `rows`, `features`, `symbols`, `start`, `end`, `output`.

Inspect schemas: `uv run qs schema compute.features` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs compute labels forward-return`

Create forward-return threshold labels for one symbol.

Priority: P1. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination label table. |
| `--bars` | `path` / `required` | Single-symbol OHLCV file with a close column. |
| `--horizon` | `integer` / `1` | Forward bar horizon. |
| `--up-threshold` | `number` / `0.0` | Label 1 above this forward return. |
| `--down-threshold` | `number` / `0.0` | Label -1 below minus this magnitude. |

Output data fields: `rows`, `columns`, `output`.

Inspect schemas: `uv run qs schema compute.labels.forward-return` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs compute labels triple-barrier`

Create triple-barrier labels for one symbol.

Priority: P1. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination label table. |
| `--bars` | `path` / `required` | Single-symbol OHLCV file with a close column. |
| `--lookback` | `integer` / `5` | Volatility scaling horizon (L). |
| `--pt-sl` | `number` / `1.0` | Profit and stop volatility multiplier. |
| `--t-limit` | `integer` / `10` | Maximum holding bars. |

Output data fields: `rows`, `columns`, `output`.

Inspect schemas: `uv run qs schema compute.labels.triple-barrier` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs compute resample`

Resample A-share one-minute bars to five-minute bars.

Priority: P1. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination 5-minute table. |
| `--input` | `path` / `required` | A-share one-minute OHLCV file with an eob index or column. |

Output data fields: `rows`, `columns`, `output`.

Inspect schemas: `uv run qs schema compute.resample` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs compute adjust`

Forward-adjust stored raw bars with adj_factor events.

Priority: P1. Side effects: writes-output, writes-store.

| Option | Type / default | Description |
|---|---|---|
| `--symbols` | `list[string]` / `required` | QuantSpace symbols with raw bars and adj_factor files. |
| `--frequency` | `string` / `1d` | Raw market store directory, e.g. 1d or 1m. |
| `--output` | `path?` / `null` | Output file for exactly one symbol, outside managed storage. |
| `--write` | `boolean` / `false` | Write <frequency>_adj files into managed market storage; otherwise a dry run. |
| `--overwrite` | `boolean` / `false` | Allow replacing existing output. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |

Output data fields: `symbols`, `rows`, `saved`, `dry_run`, `target_frequency`, `planned_paths`, `unadjusted`.

Inspect schemas: `uv run qs schema compute.adjust` (add `--part input|output` or `--file-field FIELD`).

<!-- END GENERATED: qs commands -->
