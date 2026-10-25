---
name: analyze
description: Use when tasks need factor diagnostics, IC/grouped return analysis, attribution, robustness checks, deterministic factor-mining evaluation, or time-series distribution and stationarity checks.
---

# Analyze

Analyze is the research diagnostics boundary. Use it to understand factors,
returns, attribution, robustness, and time-series behavior after data and
signals have been produced. Strategy execution and portfolio construction live
in `skills.backtest`.

`AnalyzeFacade` is the deterministic entrypoint for factor-mining preflight,
evaluation, and explicit pool comparison. The facade is read-only (no implicit
I/O), fails fast on hard preflight/alignment/causality failures before return
evaluation, and returns analyze-native structured results. Formal portfolio
returns and costs call `skills.backtest.VectorBacktester` by default;
`AnalyzeFacade(backtester_factory=...)` can substitute the engine for `evaluate`,
while the formal pool pair always uses `VectorBacktester`.

`skills.analyze` must not import `skills.factor_mining`, `strategies`, report
rendering, controller/role/workflow code, or LLM SDKs; only `tearsheet.py` reads
the store workspace paths (for its default output directory).

Install plotting and parallel-analysis dependencies with
`uv sync --extra analyze`.

## Public API

```python
from skills.analyze import AnalyzeFacade, ProtocolSnapshot, SpecSnapshot
from skills.analyze.factor_analysis import IC_stat, group_stat, full_stat
from skills.analyze.factor_information import (
    ICInformationResult,
    compute_horizon_ic,
    compute_ic_information_surface,
    compute_lagged_ic,
    rolling_factor_rank_correlation,
)
from skills.analyze.ts_analysis import TimeSeriesAnalyzer, analyze_time_series
from skills.analyze.attribution_counterfactual import performance_metrics
```

## Components

| Module family | Purpose |
|---------------|---------|
| `facade` / `contracts` | Deterministic entrypoint and analyze-native snapshots |
| `validation` / `spec_checks` / `causality` | Panel, formula structure, parameter, and prefix-causality checks |
| `factor_evaluation` / `factor_robustness` / `factor_incremental` | IC/quantiles/turnover, robustness, pool incremental |
| `factor_analysis` | IC statistics, grouped returns, winsorization helpers |
| `factor_information` | Horizon/Lag IC surfaces, HAC summaries, rank correlation, rolling correlation, and Top-N overlap |
| `ts_analysis` | KDE/QQ plots, Hurst, ADF, KPSS, trend scoring |
| `attribution_*` | Symbol/category PnL, Brinson, decision edges, ranking buckets, Shapley, robustness, stat tests |
| `tearsheet` | Single-factor four-panel PNG tearsheet |

## Recipes

**Deterministic factor-mining evaluation (via the factor_mining adapter)**

```python
from skills.analyze import AnalyzeFacade
from skills.factor_mining.adapters.analyze import (
    AnalyzeAdapter,
    build_prefix_recompute_capability,
)

# Official issuer signature: FactorSpec + optional verified FactorExecutionResult.
# Preflight (no execution): build_prefix_recompute_capability(factor=spec)
# Evaluate: build_prefix_recompute_capability(factor=spec, execution=execution)
# AnalyzeAdapter.preflight / evaluate wire this automatically.
# The snippet below is illustrative (loaders/request omitted); production code
# injects real resolvers and must not treat ellipsis as runnable.

adapter = AnalyzeAdapter(
    facade=AnalyzeFacade(),
    resolve_brief=resolve_brief,
    resolve_factor=resolve_factor,
    resolve_protocol=resolve_protocol,
    resolve_execution=resolve_execution,
    load_series=load_series,
    load_panel=load_panel,
)
preflight_report = adapter.preflight(evaluation_request)
assert preflight_report.failure is None
# After FactorExecutionAdapter.execute(...):
eval_report = adapter.evaluate(evaluation_request_with_execution_ref)
assert eval_report.engine_version
```

**Trust boundary (prefix recompute).** `BoundPrefixRecompute` cannot be
constructed publicly. The only production issuer is
`build_prefix_recompute_capability(*, factor: FactorSpec, execution=None)` —
it compiles the exact FactorSpec and optionally checks
`execution.callable_fingerprint`. Analyze does **not** expose a public API that
seals arbitrary callables with hash strings. Process trust boundary: private
helpers remain importable in-process; orchestration policy must only use the
`build_prefix_recompute_capability` adapter builder. Evaluate additionally requires an issued recompute to
reproduce evaluated values (`CAUSALITY_RECOMPUTE_VALUE_MISMATCH`).

`FunctionRef` has no module allowlist. It may point to generated strategy code,
`skills.compute`, or another importable local dependency. Analyze checks the
research contract—fields, parameter/window/lag consistency, output alignment,
and time causality—rather than treating the local Python module as untrusted.

**Trust boundary (formal pool pair).** Portfolio deltas require an officially
issued `FormalBacktestPair` from `run_official_formal_backtest_pair`, which
constructs module `VectorBacktester` twice on explicit before/after target
weights (no caller factory). Issuance is a canonical digest over before/after
`result_df`/`executed_weights` plus panel/candidate/pool/protocol/shared-sample/
target-weight hashes and engine name/version. The pair rejects ordinary
`setattr` after freeze; `is_issued()` recomputes the digest so
`object.__setattr__` tampering invalidates compare. There is no helper that
accepts caller-supplied `BacktestResult` objects as verified.

**Protocol vs Brief authority.** Brief owns horizon/rebalance/cost/universe/
`execution_delay_bars` (mapped to `signal_lag`). `trade_at` and `return_mode`
are Analyze/`ProtocolSnapshot` fields with no Brief counterpart — they are not
silently inferred from Brief; callers must set them on the protocol.

**Execution-aligned labels.** Predictive IC, group returns, and pool residual /
R² use one canonical label: forward `P[t+L+H]/P[t+L]-1` or backward
`P[t+L]/P[t+L-H]-1` on `protocol.trade_at` prices, with `signal_lag=L` and
holding window `horizon_bars=H`. Formal trading asserts the same semantics and
is unavailable for `horizon_bars != 1` (one-bar VectorBacktester limit) or
`return_mode != "forward"`.

Overlapping horizons (`horizon_bars > 1`) mark iid IC t-tests unavailable and
report Newey–West HAC t/se/p instead. Pool marginal value is joint CS R² delta /
residual IC under residual df and full-rank checks — never candidate IC minus
mean member IC, and never saturated `n == n_params` mechanical R²=1.

**Horizon IC and Lagged IC**

```python
from skills.analyze.factor_information import compute_horizon_ic, compute_lagged_ic

horizon_result = compute_horizon_ic(
    factors,
    close_prices,
    horizons=[1, 3, 5, 10, 20, 40, 60],
    signal_lag=1,
)
lagged_result = compute_lagged_ic(
    factors,
    close_prices,
    horizons=[1, 5, 10, 20],
    lags=[0, 1, 2, 3, 5, 10, 20, 40, 60],
    signal_lag=1,
)
```

Both return `ICInformationResult(summary, daily_ic)`. Horizon IC fixes
`lag=0`; Lagged IC changes signal-use delay independently of the return
horizon. The execution-aligned return is
`P[t+signal_lag+lag+horizon] / P[t+signal_lag+lag] - 1`, and each summary row
uses Newey-West lag `horizon-1`.

**Factor evaluation (IC_stat / group_stat)**

```python
from skills.analyze.factor_analysis import IC_stat, group_stat

ic_stat_dict, ic_series = IC_stat(df, rank_IC=True, n=5)
group_return, turnover = group_stat(df, n=5, g=5, verbose=True)
```

`group_stat` semantics: `n` is the rebalance period only (regroup every `n` bars on the
rebalance-day factor). `group_return` is always **one-bar** forward returns
(`close.pct_change().shift(-1)`, equal-weight within each group, daily rebalanced to equal
weight), so `(1 + group_return).cumprod()` is a valid NAV for any `n`. Do not feed it
`n`-bar returns: that would count each holding window `n` times. `IC_stat(n=...)` is
different and correctly uses the `n`-bar forward return as its label.

**Time-series stationarity check**

```python
from skills.analyze.ts_analysis import TimeSeriesAnalyzer

analyzer = TimeSeriesAnalyzer(price_series)
analyzer.analyze_windows([60, 120, 240])
results_df = analyzer.get_results_dataframe()
```

**Return-distribution KDE and QQ analysis**

```python
from skills.analyze.ts_analysis import ts_analysis

fig, axes = ts_analysis(
    price_series,
    plot_title="asset",
    plot_path="reports/asset.png",
    show=False,
    save_csv=True,
)
```

The input is a price-level series. The combined chart and CSV summarize
standardized log-return distributions for lags 1 through 34; QQ theoretical
quantiles are deterministic standard-normal quantiles.

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

### `uv run qs analyze factor-ic`

IC statistics and grouped returns with full_stat.

Priority: P0. Side effects: read-only, writes-output.

Shared parameters: `PanelSource`.

| Option | Type / default | Description |
|---|---|---|
| `--factor` | `path` / `required` | Long factor table indexed by symbol and eob with one value column. |
| `--horizon` | `integer` / `1` | Rebalance period n in bars. |
| `--groups` | `integer` / `5` | Number of factor quantile groups g. |
| `--pearson` | `boolean` / `false` | Use Pearson IC instead of rank IC. |
| `--out-dir` | `path?` / `null` | Optional directory for ic_series, group_return and turnover Parquet files. |
| `--tearsheet` | `path?` / `null` | Optional .png path for the 4-panel factor tearsheet (generate_factor_tearsheet). |
| `--name` | `string?` / `null` | Factor label on the tearsheet; defaults to the --factor file stem. |
| `--namespace` | `string` / `-` | Namespace label printed in the tearsheet title. |
| `--overwrite` | `boolean` / `false` | Replace existing output files. |

Output data fields: `ic_stats`, `group_mean_return`, `ic_rows`, `group_rows`, `turnover_rows`.

Inspect schemas: `uv run qs schema analyze.factor-ic` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs analyze ic-surface`

Execution-aligned factor x horizon x lag rank-IC surface with HAC summaries.

Priority: P1. Side effects: read-only, writes-output.

Shared parameters: `PanelSource`.

| Option | Type / default | Description |
|---|---|---|
| `--factors` | `object` / `required` | Wide factor tables (date by symbol) by name, e.g. mom=mom.parquet. |
| `--price-field` | `string` / `close` | Panel column used as the execution price. |
| `--horizons` | `list[integer]` / `required` | Forward return horizons in bars. |
| `--lags` | `list[integer]` / `factory` | Extra signal-use delays in bars; 0 is Horizon IC. |
| `--signal-lag` | `integer` / `1` | Bars between signal and execution. |
| `--directions` | `object?` / `null` | Optional direction (1 or -1) for every factor; the factors are oriented with orient_factor_frames before the IC is computed. Pass the same directions as strategy combine when the daily_ic feeds combine --ic-history. |
| `--segments` | `object?` / `null` | Named [start, end] summary windows, e.g. {"is": ["2015-01-01", "2019-12-31"]}; null bounds are open. Omitted means one "full" segment. |
| `--min-cross-section` | `integer` / `6` | Minimum symbols per date for an IC observation. |
| `--out-dir` | `path?` / `null` | Optional directory for summary and daily_ic Parquet files. |
| `--overwrite` | `boolean` / `false` | Replace existing output files. |

Output data fields: `summary`, `daily_rows`.

Inspect schemas: `uv run qs schema analyze.ic-surface` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs analyze factor-correlation`

Factor rank-correlation, Top-N overlap and rolling correlation history.

Priority: P1. Side effects: read-only, writes-output.

| Option | Type / default | Description |
|---|---|---|
| `--factors` | `object` / `required` | Wide factor tables (date by symbol) by name, at least two, e.g. mom=mom.parquet. |
| `--directions` | `object?` / `null` | Optional direction (1 or -1) for every factor; the factors are oriented with orient_factor_frames before ranking. Pass the same directions as strategy combine when feeding combine. |
| `--segments` | `object?` / `null` | Named [start, end] summary windows, e.g. {"is": ["2015-01-01", "2019-12-31"]}; null bounds are open. Omitted means one "full" segment. Names are safe path segments (letters, digits, underscore, hyphen). |
| `--window` | `integer` / `252` | Rolling correlation window in bars. |
| `--min-periods` | `integer` / `126` | Minimum observations in the rolling window. |
| `--top-n` | `integer` / `3` | Names per date in the Top-N overlap. |
| `--out-dir` | `path?` / `null` | Optional directory for correlation_<segment>, top_n_overlap_<segment> and correlation_history Parquet files; correlation_history feeds strategy combine --correlation-history. |
| `--data-root` | `path?` / `null` | Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/. |
| `--overwrite` | `boolean` / `false` | Replace existing output files. |

Output data fields: `pairs`, `correlation`, `top_n_overlap`, `history_rows`.

Inspect schemas: `uv run qs schema analyze.factor-correlation` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs analyze perf`

Scalar performance metrics of a return stream.

Priority: P0. Side effects: read-only.

| Option | Type / default | Description |
|---|---|---|
| `--returns` | `path` / `required` | Dated table of periodic returns, such as a backtest result table. |
| `--column` | `string` / `return` | Return column in the input table. |
| `--annualization` | `integer` / `252` | Periods per year. |

Output data fields: `metrics`, `rows`.

Inspect schemas: `uv run qs schema analyze.perf` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs analyze drawdowns`

List peak-to-trough drawdown episodes.

Priority: P1. Side effects: read-only.

| Option | Type / default | Description |
|---|---|---|
| `--returns` | `path` / `required` | Dated periodic returns table. |
| `--column` | `string` / `return` | Return column. |
| `--top-n` | `integer` / `5` | Maximum number of episodes. |
| `--min-depth` | `number` / `0.0` | Minimum drawdown depth. |

Output data fields: `episodes`, `rows`.

Inspect schemas: `uv run qs schema analyze.drawdowns` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs analyze overfit`

Deflated Sharpe, PBO, Reality Check/SPA, bootstrap and rolling diagnostics.

Priority: P1. Side effects: read-only.

| Option | Type / default | Description |
|---|---|---|
| `--candidates` | `path` / `required` | Date by candidate returns table. |
| `--tests` | `list[dsr\|pbo\|pbo-sensitivity\|spa\|bootstrap\|rolling]` / `factory` | Diagnostics: deflated Sharpe, CSCV PBO, PBO split grid, Reality Check and SPA, block bootstrap of the mean return, rolling metric slices. |
| `--benchmark-col` | `string?` / `null` | Optional benchmark column excluded from candidate tests. |
| `--n-trials` | `integer?` / `null` | Trial count for the deflated Sharpe; defaults to the candidate column count. |
| `--benchmark-sr` | `number` / `0.0` | Benchmark Sharpe for the deflated Sharpe. |
| `--n-splits` | `integer` / `4` | Even number of CSCV blocks for PBO. |
| `--split-values` | `list[integer]` / `factory` | CSCV block counts for pbo-sensitivity. |
| `--promotion-threshold` | `number` / `0.2` | PBO threshold reported by pbo-sensitivity. |
| `--n-bootstrap` | `integer?` / `null` | Bootstrap replications; defaults per function (spa 500, bootstrap 200). |
| `--block-size` | `integer` / `20` | Bootstrap block length. |
| `--seed` | `integer?` / `null` | Random seed; omitted leaves the bootstrap unseeded. |
| `--windows` | `list[integer]` / `factory` | Rolling metric windows. |
| `--annualization` | `integer` / `252` | Observations per year. |

Output data fields: `results`.

Inspect schemas: `uv run qs schema analyze.overfit` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs analyze stationarity`

Hurst, ADF and KPSS over trailing windows.

Priority: P1. Side effects: read-only.

| Option | Type / default | Description |
|---|---|---|
| `--series` | `path` / `required` | Dated table such as OHLCV bars or a single series. |
| `--column` | `string` / `close` | Value column to analyze. |
| `--windows` | `list[integer]` / `factory` | Trailing windows; the analyze_time_series default is 20, 40, 60. |

Output data fields: `windows`.

Inspect schemas: `uv run qs schema analyze.stationarity` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs analyze preflight`

AnalyzeFacade hard checks of panel, spec and protocol.

Priority: P1. Side effects: read-only.

Shared parameters: `PanelSource`.

| Option | Type / default | Description |
|---|---|---|
| `--spec-json` | `path` / `required` | Analyze-native SpecSnapshot JSON file. |
| ↳ JSON payload | `qs schema analyze.preflight --file-field spec_json` | Generate a fillable file with `uv run qs analyze preflight --print-template spec_json`. |
| `--protocol-json` | `path` / `required` | Analyze-native ProtocolSnapshot JSON file. |
| ↳ JSON payload | `qs schema analyze.preflight --file-field protocol_json` | Generate a fillable file with `uv run qs analyze preflight --print-template protocol_json`. |
| `--allowed-fields` | `list[string]` / `factory` | Optional permitted input columns. |

Output data fields: `completion_status`, `hard_failed`, `sections`, `failed_findings`, `metrics`.

Inspect schemas: `uv run qs schema analyze.preflight` (add `--part input|output` or `--file-field FIELD`).

### `uv run qs analyze evaluate`

Deterministic AnalyzeFacade evaluation of precomputed factor values.

Priority: P1. Side effects: read-only, writes-output.

Shared parameters: `PanelSource`.

| Option | Type / default | Description |
|---|---|---|
| `--spec-json` | `path` / `required` | Analyze-native SpecSnapshot JSON file. |
| ↳ JSON payload | `qs schema analyze.evaluate --file-field spec_json` | Generate a fillable file with `uv run qs analyze evaluate --print-template spec_json`. |
| `--protocol-json` | `path` / `required` | Analyze-native ProtocolSnapshot JSON file. |
| ↳ JSON payload | `qs schema analyze.evaluate --file-field protocol_json` | Generate a fillable file with `uv run qs analyze evaluate --print-template protocol_json`. |
| `--allowed-fields` | `list[string]` / `factory` | Optional permitted input columns. |
| `--values` | `path` / `required` | Long factor values on exactly the panel's (symbol, eob) index, e.g. from `qs compute factor --keep-na`. |
| `--valid-mask` | `path?` / `null` | Optional long boolean validity table; defaults to non-missing values. |
| `--backtest` | `boolean` / `true` | Run the formal backtest section; --no-backtest skips it. |
| `--regime-masks-json` | `path?` / `null` | Optional JSON file mapping regime names to long boolean mask tables. |
| ↳ JSON payload | `qs schema analyze.evaluate --file-field regime_masks_json` | Generate a fillable file with `uv run qs analyze evaluate --print-template regime_masks_json`. |
| `--output` | `path?` / `null` | Optional full AnalyzeResult JSON output. |
| `--overwrite` | `boolean` / `false` | Replace an existing output file. |

Output data fields: `completion_status`, `hard_failed`, `sections`, `failed_findings`, `metrics`.

Inspect schemas: `uv run qs schema analyze.evaluate` (add `--part input|output` or `--file-field FIELD`).

<!-- END GENERATED: qs commands -->
