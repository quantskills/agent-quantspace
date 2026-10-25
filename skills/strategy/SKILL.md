---
name: strategy
description: Use when tasks need reusable strategy contracts, cross-sectional selection types, or time-series signal-to-weight helpers.
---

# Strategy

`skills/strategy` owns reusable strategy types that convert features, scores,
labels, or signals into date × symbol target weights. Concrete public strategy
behavior remains under `strategies/`.

## Public API

```python
from skills.strategy import StrategyContext, StrategyResult, WeightGenerator
from skills.strategy.cross_sectional import (
    DynamicFactorWeightConfig,
    ModularBacktester,
    apply_rebalance_schedule,
    combine_factor_scores,
    estimate_factor_weights,
    hold_weights_on_calendar,
    normalize_factor_frames,
    rank_factor_frames,
    top_n_weights,
)
from skills.strategy.time_series import signal_to_single_asset_weights
```

## Boundaries

- `contracts.py` defines the strategy-neutral target-weight result and generator protocol.
- `ports.py` defines only the market-data reader needed by current workflows; it
  does not predeclare persistence or Tracking APIs.
- `cross_sectional/` owns reusable ranking, selection, exit, risk-control, and
  modular research types, including equal-rank, equal-vote, rolling IC,
  rolling ICIR, and correlation-aware maximum-IC / maximum-ICIR factor
  combinations.
- `hold_weights_on_calendar` maps signal-day target weights onto the full trading
  calendar (forward hold, flat before the first signal) before backtesting.
- `time_series.py` owns signal-to-weight conversion and a research-only
  `TimeSeriesBacktester` adapter that delegates execution to `VectorBacktester`.
- Concrete factors, features, rules, model pipelines, and workflows belong in
  `strategies/`.
- Formal public execution always passes target weights to
  `skills.backtest.VectorBacktester`.

`TimeSeriesBacktester` keeps exploratory prediction-frame analysis available,
but does not implement a second return or metric engine. Published public
strategy results should still use explicit target weights plus `VectorBacktester`.

## Multi-factor combination recipe

```python
from skills.strategy.cross_sectional import (
    DynamicFactorWeightConfig,
    combine_factor_scores,
)

config = DynamicFactorWeightConfig(
    availability_delay=signal_lag + horizon,
    lookback=252,
    min_periods=126,
    max_weight=0.5,
    correlation_shrinkage=0.5,
)
result = combine_factor_scores(
    raw_factors,
    method="max_icir",
    directions=factor_directions,
    normalization="rank",
    top_n=3,
    ic_history=ic_history,
    correlation_history=rolling_rank_correlations,
    dynamic_config=config,
)
```

Supported methods are equal rank, equal vote, rolling IC, rolling ICIR,
correlation-aware maximum IC, and correlation-aware maximum ICIR.
`max_ic` applies the inverse rolling factor-correlation matrix to rolling mean
IC; `max_icir` applies it to rolling ICIR. Both require tidy correlation
history with columns `eob`, `factor_a`, `factor_b`, and `correlation`.
`result.factor_weights` is the factor-level voice in the composite score;
`result.target_weights` is the separate asset allocation produced after Top-N
selection. The public combination entry point always applies factor direction
and daily cross-sectional normalization. Use `normalization="rank"` for robust
percentile ranks or `normalization="zscore"` to retain relative score distance;
do not pre-normalize inputs.

## Time-series recipe

```python
from skills.backtest import VectorBacktester
from skills.strategy.time_series import signal_to_single_asset_weights

weights = signal_to_single_asset_weights(signal, symbol="SHSE.510300")
result = VectorBacktester(
    panel,
    signal_lag=1,
    commission=0.0002,
    slippage_bp=2.0,
).run(weights)
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

#### `OutputOptions`

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path?` / `null` | Explicit output path outside managed store namespaces. |
| `--overwrite` | `boolean` / `false` | Allow replacing an existing output artifact. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |

### `uv run qs strategy top-n`

Equal-weight the top N scores on each date.

Priority: P1. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination target-weight table. |
| `--scores` | `path` / `required` | Date by symbol score table; higher is better. |
| `--top-n` | `integer` / `required` | Names held per date. |
| `--gross-exposure` | `number` / `1.0` | Total weight per date. |

Output data fields: `rows`, `columns`, `start`, `end`, `preview`.

Inspect schemas: `uv run qs schema strategy.top-n` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs strategy signal-weights`

Turn a single-asset signal into target weights.

Priority: P1. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination one-column target-weight table. |
| `--signal` | `path` / `required` | Signal table with an eob index or column. |
| `--column` | `string` / `signal` | Signal column; values are clipped to [-1, 1]. |
| `--symbol` | `string` / `required` | QuantSpace symbol that receives the weights. |
| `--exposure` | `number` / `1.0` | Weight multiplier. |

Output data fields: `rows`, `columns`, `start`, `end`, `preview`.

Inspect schemas: `uv run qs schema strategy.signal-weights` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs strategy hold-calendar`

Forward-hold signal-day weights across a panel's trading calendar.

Priority: P1. Side effects: writes-output.

Shared parameters: `PanelSource`, `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination daily target-weight table. |
| `--weights` | `path` / `required` | Signal-day target weights (date by symbol). |

Output data fields: `rows`, `columns`, `start`, `end`, `preview`.

Inspect schemas: `uv run qs schema strategy.hold-calendar` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs strategy combine`

Combine raw factors into composite scores and Top-N weights.

Priority: P1. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--factors` | `object` / `required` | Raw factor tables by name, each date by symbol, e.g. mom=mom.parquet. |
| `--directions` | `object` / `required` | Direction for every factor: 1 if larger is better, -1 otherwise. |
| `--method` | `equal_rank\|equal_vote\|rolling_ic\|rolling_icir\|max_ic\|max_icir` / `required` | Combination method. |
| `--normalization` | `rank\|zscore` / `rank` | Daily cross-sectional normalization. |
| `--top-n` | `integer` / `3` | Assets selected from the composite score. |
| `--ic-history` | `path?` / `null` | Date by factor IC table; required by rolling and max methods. |
| `--correlation-history` | `path?` / `null` | Tidy table with eob, factor_a, factor_b, correlation; required by max methods. |
| `--availability-delay` | `integer?` / `null` | Bars before an IC becomes known (signal_lag + horizon); required by rolling and max methods. |
| `--lookback` | `integer` / `252` | Rolling IC window. |
| `--min-periods` | `integer` / `126` | Minimum IC observations. |
| `--max-weight` | `number` / `0.5` | Cap on one factor's weight. |
| `--correlation-shrinkage` | `number` / `0.5` | Shrink factor correlations toward identity. |
| `--out-dir` | `path` / `required` | Directory for factor_weights, composite_scores and target_weights Parquet files. |

Output data fields: `method`, `factors`, `rows`, `start`, `end`, `latest_factor_weights`.

Inspect schemas: `uv run qs schema strategy.combine` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs strategy cs-run`

Run a factor-voting Top-pct cross-sectional strategy with ModularBacktester.

Priority: P1. Side effects: writes-output.

Shared parameters: `PanelSource`.

| Option | Type / default | Description |
|---|---|---|
| `--start` | `string?` / `null` | First result date (start_date); earlier bars still load. Pass a trimmed --panel from `qs store read` to limit history. |
| `--end` | `string?` / `null` | Last result date (end_date); later bars still load. Pass a trimmed --panel from `qs store read` to limit history. |
| `--factors` | `list[FactorItem]` / `required` | Entry factors voted into the Top-pct selection. |
| `--exit-filters` | `list[ExitFilterItem]` / `factory` | Exit filters applied to selected weights. |
| `--top-pct` | `number` / `0.2` | Fraction of names selected. |
| `--trade-at` | `open\|close` / `close` | Execution price field. |
| `--signal-lag` | `integer` / `1` | Bars between signal and execution. |
| `--commission` | `number` / `0.0002` | One-way commission rate. |
| `--slippage-bp` | `number` / `required` | One-way slippage in basis points. |
| `--rebalance-freq` | `string` / `1` | D, W, M, or a positive number of bars between rebalances. |
| `--weight-method` | `equal\|risk_parity\|inverse_variance\|epo` / `equal` | WEIGHT_METHODS key for selected names. |
| `--vol-target` | `number?` / `null` | Optional volatility target. |
| `--exposure-policy` | `keep_cash\|renormalize\|allocate_defensive` / `keep_cash` | What happens to weight removed by exit filters. |
| `--defensive-symbols` | `list[string]` / `factory` | Symbols for the allocate_defensive policy. |
| `--out-dir` | `path?` / `null` | Optional directory for signal_weights, executed_weights, result Parquet files and metrics.json. |
| `--overwrite` | `boolean` / `false` | Allow replacement of existing output files. |

Output data fields: `metrics`, `weight_stats`, `rows`, `start`, `end`.

Inspect schemas: `uv run qs schema strategy.cs-run` (add `--part input|output` or `--file-field FIELD`).

<!-- END GENERATED: qs commands -->
