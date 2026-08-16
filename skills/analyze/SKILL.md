---
name: analyze
description: Use when tasks need factor diagnostics, IC/grouped return analysis, attribution, robustness checks, deterministic factor-mining evaluation, or time-series distribution and stationarity checks.
---

# Analyze

Analyze is the research diagnostics boundary. Use it to understand factors,
returns, attribution, robustness, and time-series behavior after data and
signals have been produced. Strategy execution and portfolio construction live
in `skills.backtest`.

Phase 03 adds a deterministic `AnalyzeFacade` for factor-mining preflight,
evaluation, and explicit pool comparison. The facade is read-only (no implicit
I/O), fails fast on hard preflight/alignment/causality failures before return
evaluation, and returns analyze-native structured results. Formal portfolio
returns and costs always call `skills.backtest.VectorBacktester`.

`skills.analyze` must not import `skills.factor_mining`, `strategies`, store
global paths, report rendering, controller/role/workflow code, or LLM SDKs.

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
| `facade` / `contracts` | Deterministic Phase 03 entrypoint and analyze-native snapshots |
| `validation` / `spec_checks` / `causality` | Panel, formula structure, parameter, and prefix-causality checks |
| `factor_evaluation` / `factor_robustness` / `factor_incremental` | IC/quantiles/turnover, robustness, pool incremental |
| `factor_analysis` | Legacy IC statistics, grouped returns, winsorization helpers |
| `factor_information` | Horizon/Lag IC surfaces, HAC summaries, rank correlation, rolling correlation, and Top-N overlap |
| `ts_analysis` | KDE/QQ plots, Hurst, ADF, KPSS, trend scoring |
| `attribution_*` | Symbol/category PnL, Brinson, decision edges, ranking buckets, Shapley, robustness, stat tests |
| `tearsheet` | Factor and artifact-namespace summary report helpers |

## Recipes

**Deterministic factor-mining evaluation (via Phase 02 adapter)**

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
# After Phase02 execute(...):
eval_report = adapter.evaluate(evaluation_request_with_execution_ref)
assert eval_report.engine_version
```

**Trust boundary (prefix recompute).** `BoundPrefixRecompute` cannot be
constructed publicly. The only production issuer is
`build_prefix_recompute_capability(factor: FactorSpec, execution=None)` —
it compiles the exact FactorSpec and optionally checks
`execution.callable_fingerprint`. Analyze does **not** expose a public API that
seals arbitrary callables with hash strings. Process trust boundary: private
helpers remain importable in-process; orchestration policy must only use the
Phase02 adapter builder. Evaluate additionally requires an issued recompute to
reproduce evaluated values (`CAUSALITY_RECOMPUTE_VALUE_MISMATCH`).

`FunctionRef` has no module allowlist. It may point to generated strategy code,
`skills.compute`, or another importable local dependency. Analyze checks the
research contract—fields, parameter/window/lag consistency, output alignment,
and time causality—rather than treating the local Python module as untrusted.

**Trust boundary (resolvers / artifact loaders).** Production
`resolve_brief` / `resolve_factor` / `resolve_execution` / `load_series` ports
are trusted orchestration inputs. `ArtifactRef.content_hash` must be verified by
a store-backed loader (e.g. `DataManagerArtifactStore.get`). Arbitrary
in-process malicious reflection is outside the security boundary; private
issuers only prevent accidental public-API misuse, not same-process attackers.

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
is unavailable for `horizon_bars != 1` (one-bar VectorBacktester limit).

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

**Factor evaluation (legacy helpers)**

```python
from skills.analyze.factor_analysis import IC_stat, group_stat

ic_stat_dict, ic_series = IC_stat(df, rank_IC=True, n=5)
group_return, turnover = group_stat(df, n=5, g=5, verbose=True)
```

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
