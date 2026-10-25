---
name: backtest
description: Use when tasks need vectorized strategy execution, portfolio weighting, portfolio-level filters, transaction cost helpers, exit A/B analysis, overlay metrics, or multi-strategy return blending.
---

# Backtest

Backtest is the shared portfolio execution and construction boundary. Strategy
domains should produce date x symbol weights; this skill turns those weights
into executed weights, returns, costs, diagnostics, and report-ready metrics.

## Public API

```python
from skills.backtest import VectorBacktester, annual_return_metrics
from skills.backtest.weighting import WEIGHT_METHODS, risk_parity
from skills.backtest.filters import apply_portfolio_filters
from skills.backtest.cost_model import cost_bp_for_trigger_time
from skills.backtest.exit_analysis import evaluate_exit_factor
from skills.backtest.overlay_metrics import overlay_alpha
```

## Components

| Module | Purpose |
|--------|---------|
| `skills.backtest.vector` | `VectorBacktester`, `BacktestResult`, annual/activity/benchmark metrics |
| `skills.backtest.weighting` | Equal weight, risk parity, inverse variance, EPO, `WEIGHT_METHODS` |
| `skills.backtest.filters` | Market breadth, index trend, and volatility targeting overlays |
| `skills.backtest.combiner` | Blend multiple strategy return streams |
| `skills.backtest.cost_model` | A-share trigger-time cost layers and single-trade PnL helpers |
| `skills.backtest.exit_analysis` | Baseline vs filtered exit A/B evaluation |
| `skills.backtest.overlay_metrics` | Overlay alpha, win rate, drawdown, Sharpe, and regime metrics |

`VectorBacktester` requires explicit `commission` and `slippage_bp` (a missing
value raises `ValueError`). Each date's executed weight always earns the
next bar's return, which is the safe convention for close-derived signals.

## Recipes

**Run weights through the shared vectorized backtester**

```python
from skills.backtest import VectorBacktester

result = VectorBacktester(
    data=panel,
    trade_at="close",
    signal_lag=1,
    commission=0.0002,
    slippage_bp=2.0,
).run(weights_df)
```

**Convert votes to risk-aware weights**

```python
from skills.backtest.weighting import risk_parity

weights = risk_parity(votes_df, returns_df=returns_df, lookback=60, min_periods=20)
```

**Evaluate an exit filter**

```python
from skills.backtest.exit_analysis import evaluate_exit_factor
from skills.strategy.cross_sectional import ModularBacktester

result = evaluate_exit_factor(
    data,
    factor_configs,
    exit_filter,
    backtester_cls=ModularBacktester,
    commission=0.0002,
    slippage_bp=2.0,
)
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

### `uv run qs backtest run`

Execute target weights through VectorBacktester with costs and metrics.

Priority: P0. Side effects: writes-output.

Shared parameters: `PanelSource`.

| Option | Type / default | Description |
|---|---|---|
| `--start` | `string?` / `null` | First result date (start_date); earlier bars still load. Pass a trimmed --panel from `qs store read` to limit history. |
| `--end` | `string?` / `null` | Last result date (end_date); later bars still load. Pass a trimmed --panel from `qs store read` to limit history. |
| `--weights` | `path` / `required` | Date by symbol target weights table (eob index or column). |
| `--commission` | `number` / `required` | One-way commission rate, e.g. 0.0002. |
| `--slippage-bp` | `number` / `required` | One-way slippage in basis points. |
| `--trade-at` | `open\|close` / `close` | Execution price field. |
| `--signal-lag` | `integer` / `1` | Bars between signal and execution. |
| `--enforce-trade-constraints` | `boolean` / `false` | Apply suspension and limit masks; the panel needs is_suspended, is_limit_up and is_limit_down. |
| `--out-dir` | `path?` / `null` | Optional directory for result.parquet, executed_weights.parquet and metrics.json. |
| `--overwrite` | `boolean` / `false` | Allow replacement of existing output files. |

Output data fields: `metrics`, `annual_returns`, `activity`, `rows`, `start`, `end`.

Inspect schemas: `uv run qs schema backtest.run` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs backtest weigh`

Convert a vote matrix into portfolio weights.

Priority: P1. Side effects: writes-output.

Shared parameters: `PanelSource`, `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination weights table. |
| `--votes` | `path` / `required` | Date by symbol vote matrix; nonzero means selected. |
| `--returns` | `path?` / `null` | Date by symbol asset returns; otherwise close-to-close returns of a panel source. |
| `--method` | `equal\|risk_parity\|inverse_variance\|epo` / `equal` | WEIGHT_METHODS key. |
| `--lookback` | `integer?` / `null` | Trailing return window; defaults to the method default (60, epo 1200). |
| `--min-periods` | `integer?` / `null` | Minimum trailing observations; defaults to the method default (20, epo 60). |
| `--lambda` | `number` / `10.0` | EPO risk aversion. |
| `--shrink-w` | `number` / `0.2` | EPO correlation shrinkage. |

Output data fields: `method`, `rows`, `columns`, `start`, `end`, `preview`.

Inspect schemas: `uv run qs schema backtest.weigh` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs backtest overlay`

Scale weights with market breadth, index trend, or volatility targeting.

Priority: P2. Side effects: writes-output.

Shared parameters: `PanelSource`, `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--output` | `path` / `required` | Destination scaled weights table. |
| `--weights` | `path` / `required` | Date by symbol weights to scale. |
| `--index-close` | `path?` / `null` | Benchmark close table with an eob index and one value column; required by index_trend. |
| `--market-breadth` | `object?` / `null` | apply_market_breadth_scale options, e.g. {"breadth_threshold": 0.3, "scale_below": 0.5, "ma_period": 20}. |
| `--index-trend` | `object?` / `null` | apply_index_trend_scale options, e.g. {"scale_downtrend": 0.5, "ma_period": 120}. |
| `--vol-target` | `object?` / `null` | apply_portfolio_vol_targeting options, e.g. {"vol_target": 0.1, "lookback": 60}. |

Output data fields: `method`, `rows`, `columns`, `start`, `end`, `preview`.

Inspect schemas: `uv run qs schema backtest.overlay` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs backtest combine`

Blend strategy return streams with StrategyCombiner.

Priority: P2. Side effects: writes-output.

Shared parameters: `OutputOptions`.

| Option | Type / default | Description |
|---|---|---|
| `--returns` | `path` / `required` | Strategy daily returns: eob index or column plus one column per strategy. |
| `--method` | `equal\|risk_parity\|custom` / `equal` | StrategyCombiner method. |
| `--weights` | `object` / `factory` | Custom strategy weights, normalized to sum to one. |
| `--lookback` | `integer` / `60` | Risk parity volatility window. |

Output data fields: `strategies`, `weights`, `metrics`, `rows`.

Inspect schemas: `uv run qs schema backtest.combine` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs backtest cost`

Look up the A-share trigger-time cost layer and single T PnL.

Priority: P2. Side effects: read-only.

| Option | Type / default | Description |
|---|---|---|
| `--time` | `string` / `required` | A-share trigger timestamp, e.g. "2026-09-23 14:50". |
| `--sell-price` | `number?` / `null` | Sell price of a single T trade; needs buyback_price. |
| `--buyback-price` | `number?` / `null` | Buyback price of a single T trade; needs sell_price. |

Output data fields: `time`, `layer`, `cost_bp`, `gross_bp`, `net_bp`.

Inspect schemas: `uv run qs schema backtest.cost` (add `--part input|output` or `--file-field FIELD`).

<!-- END GENERATED: qs commands -->
