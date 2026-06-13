# Skills and Strategies Pytest Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the pytest suite into a large-project layout and add deterministic unit coverage for the main logic in every public `skills/` and `strategies/` module.

**Architecture:** Mirror source boundaries in the test tree: `tests/skills/<skill>/`, `tests/strategies/<domain>/`, `tests/scripts/`, `tests/integration/`, `tests/contracts/`, `tests/regression/`, `tests/docs/`, and `tests/policy/`. Unit tests use synthetic in-memory fixtures and tmp paths. Integration tests run public pipelines without network, credentials, or private data. Contract tests protect public APIs and input data conventions. Regression tests pin deterministic strategy/backtest behavior. Policy tests only enforce the test layout.

**Tech Stack:** Python 3.10+, pytest, pandas, numpy, scipy, scikit-learn, xgboost, matplotlib Agg, uv, ruff.

---

## File Structure

Create this target structure and move existing tests into it:

```text
tests/
  conftest.py
  README.md
  README-zh.md
  fixtures/
    __init__.py
    market_data.py
    model_data.py
  skills/
    analyze/
    compute/
    construct/
    ingest/
    model/
    report/
    research/
    store/
  strategies/
    cross_sectional/
    time_series/
  scripts/
  integration/
  contracts/
  regression/
  docs/
  policy/
```

Existing test migration map:

```text
tests/test_data_manager_public.py              -> tests/skills/store/test_data_manager.py
tests/test_panda_data_client.py                -> tests/skills/ingest/test_panda_data_client.py
tests/test_panda_data_symbol_map.py            -> tests/skills/ingest/test_symbol_map.py
tests/test_panda_future_tick_ingest.py         -> tests/skills/ingest/test_panda_future_tick.py
tests/test_public_label_maker.py               -> tests/skills/compute/test_label_maker.py
tests/test_vector_backtest.py                  -> tests/skills/analyze/test_backtest.py
tests/test_strategy_markdown.py                -> tests/skills/report/test_strategy_markdown.py
tests/test_strategy_data_import.py             -> tests/scripts/test_import_strategy_data.py
tests/test_strategy_reports.py                 -> tests/scripts/test_run_strategy_reports.py
tests/test_cross_sectional_public.py           -> tests/integration/test_cross_sectional_pipeline.py
tests/test_time_series_public.py               -> tests/integration/test_time_series_pipeline.py
tests/test_imports.py                          -> tests/contracts/test_public_api.py
tests/test_workspace_structure.py              -> tests/policy/test_workspace_structure.py
tests/test_generic_factor_examples.py          -> tests/skills/compute/test_factor_examples.py
tests/test_strategy_modules.py                 -> split into strategies domain test files listed below
```

Add these new unit test files:

```text
tests/skills/analyze/test_attribution.py
tests/skills/analyze/test_exit_analysis.py
tests/skills/analyze/test_factor_analysis.py
tests/skills/analyze/test_overlay_metrics.py
tests/skills/analyze/test_ts_analysis.py
tests/skills/compute/test_adjust.py
tests/skills/compute/test_cost_model.py
tests/skills/compute/test_indicators.py
tests/skills/compute/test_regime.py
tests/skills/compute/test_resample.py
tests/skills/compute/test_ts_features.py
tests/skills/compute/test_utils.py
tests/skills/compute/test_wrappers.py
tests/skills/construct/test_combiner.py
tests/skills/construct/test_filters.py
tests/skills/construct/test_weighting.py
tests/skills/model/test_lasso_tracker.py
tests/skills/model/test_ml_engine_contract.py
tests/skills/model/test_ml_factor.py
tests/skills/report/test_charts.py
tests/skills/report/test_renderer.py
tests/skills/research/test_factor_screening.py
tests/skills/research/test_param_sensitivity.py
tests/skills/research/test_strategy_comparison.py
tests/skills/store/test_adjusted_quality.py
tests/strategies/cross_sectional/test_exits.py
tests/strategies/cross_sectional/test_factor_frame.py
tests/strategies/cross_sectional/test_factors.py
tests/strategies/cross_sectional/test_io_plotting.py
tests/strategies/cross_sectional/test_ml_rank.py
tests/strategies/cross_sectional/test_modular_backtester.py
tests/strategies/cross_sectional/test_rules.py
tests/strategies/cross_sectional/test_signals_top_pct.py
tests/strategies/time_series/test_features.py
tests/strategies/time_series/test_ml.py
tests/strategies/time_series/test_rules.py
tests/strategies/time_series/test_signal_engine.py
tests/contracts/test_data_contracts.py
tests/docs/test_documented_examples.py
tests/integration/test_strategy_report_structure.py
tests/policy/test_test_layout.py
tests/regression/test_strategy_weights_regression.py
tests/regression/test_vector_backtest_regression.py
```

## Task 1: Establish Test Fixtures and Layout Policy

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/market_data.py`
- Create: `tests/fixtures/model_data.py`
- Modify: `tests/conftest.py`
- Create: `tests/policy/test_test_layout.py`
- Modify: `tests/README.md`
- Modify: `tests/README-zh.md`

- [ ] **Step 1: Create shared deterministic market fixtures**

Add this content to `tests/fixtures/market_data.py`:

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def make_ohlcv(
    prices: list[float] | np.ndarray | None = None,
    *,
    start: str = "2024-01-01",
    symbol: str | None = None,
) -> pd.DataFrame:
    close = pd.Series(
        prices if prices is not None else np.linspace(100.0, 110.0, 40),
        index=pd.date_range(start, periods=len(prices) if prices is not None else 40, name="eob"),
        dtype=float,
    )
    bars = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1000.0,
        },
        index=close.index,
    )
    if symbol is not None:
        return bars.assign(symbol=symbol).reset_index().set_index(["symbol", "eob"])
    return bars


def make_panel(symbols: tuple[str, ...] = ("AAA", "BBB", "CCC"), periods: int = 80) -> pd.DataFrame:
    frames = []
    for i, symbol in enumerate(symbols):
        prices = 100.0 + i * 5.0 + np.linspace(0.0, 8.0 + i, periods)
        frames.append(make_ohlcv(prices, symbol=symbol))
    return pd.concat(frames).sort_index()


def write_symbol_parquet(root: Path, symbol: str, bars: pd.DataFrame, frequency: str = "1d") -> Path:
    path = root / "market" / frequency / f"{symbol}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    bars.to_parquet(path)
    return path
```

- [ ] **Step 2: Create shared model fixtures**

Add this content to `tests/fixtures/model_data.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd


def make_classification_frame(rows: int = 24) -> pd.DataFrame:
    x = np.linspace(-1.0, 1.0, rows)
    return pd.DataFrame(
        {
            "feature_a": x,
            "feature_b": x**2,
            "label": (x > 0).astype(int),
        }
    )


def make_return_series(rows: int = 30) -> pd.Series:
    index = pd.date_range("2024-01-01", periods=rows, name="eob")
    return pd.Series(np.sin(np.arange(rows) / 5.0) / 100.0, index=index, name="return")
```

- [ ] **Step 3: Update root conftest**

Extend `tests/conftest.py` with repo root setup and stable matplotlib backend:

```python
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

matplotlib.use("Agg", force=True)
```

- [ ] **Step 4: Add layout policy test**

Add `tests/policy/test_test_layout.py`:

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_root_level_test_modules_except_conftest() -> None:
    root_test_files = sorted(path.name for path in (ROOT / "tests").glob("test_*.py"))
    assert root_test_files == []


def test_required_test_directories_exist() -> None:
    expected = {
        "fixtures",
        "integration",
        "contracts",
        "docs",
        "policy",
        "regression",
        "scripts",
        "skills",
        "strategies",
    }
    actual = {path.name for path in (ROOT / "tests").iterdir() if path.is_dir()}
    assert expected.issubset(actual)


def test_source_package_tests_have_matching_directories() -> None:
    assert (ROOT / "tests/skills/analyze").is_dir()
    assert (ROOT / "tests/skills/compute").is_dir()
    assert (ROOT / "tests/skills/construct").is_dir()
    assert (ROOT / "tests/skills/ingest").is_dir()
    assert (ROOT / "tests/skills/model").is_dir()
    assert (ROOT / "tests/skills/report").is_dir()
    assert (ROOT / "tests/skills/research").is_dir()
    assert (ROOT / "tests/skills/store").is_dir()
    assert (ROOT / "tests/strategies/cross_sectional").is_dir()
    assert (ROOT / "tests/strategies/time_series").is_dir()
```

- [ ] **Step 5: Move existing tests into the new tree**

Run these moves after creating destination directories:

```bash
mkdir -p tests/{fixtures,integration,contracts,docs,policy,regression,scripts}
mkdir -p tests/skills/{analyze,compute,construct,ingest,model,report,research,store}
mkdir -p tests/strategies/{cross_sectional,time_series}
git mv tests/test_data_manager_public.py tests/skills/store/test_data_manager.py
git mv tests/test_panda_data_client.py tests/skills/ingest/test_panda_data_client.py
git mv tests/test_panda_data_symbol_map.py tests/skills/ingest/test_symbol_map.py
git mv tests/test_panda_future_tick_ingest.py tests/skills/ingest/test_panda_future_tick.py
git mv tests/test_public_label_maker.py tests/skills/compute/test_label_maker.py
git mv tests/test_vector_backtest.py tests/skills/analyze/test_backtest.py
git mv tests/test_strategy_markdown.py tests/skills/report/test_strategy_markdown.py
git mv tests/test_strategy_data_import.py tests/scripts/test_import_strategy_data.py
git mv tests/test_strategy_reports.py tests/scripts/test_run_strategy_reports.py
git mv tests/test_cross_sectional_public.py tests/integration/test_cross_sectional_pipeline.py
git mv tests/test_time_series_public.py tests/integration/test_time_series_pipeline.py
git mv tests/test_imports.py tests/contracts/test_public_api.py
git mv tests/test_workspace_structure.py tests/policy/test_workspace_structure.py
```

- [ ] **Step 6: Split existing broad tests**

Move content from `tests/test_generic_factor_examples.py` into:

```text
tests/skills/compute/test_factor_examples.py
```

Do not carry over open-source/private-path absence checks into this plan.

Move content from `tests/test_strategy_modules.py` into:

```text
tests/strategies/cross_sectional/test_rules.py
tests/strategies/cross_sectional/test_ml_rank.py
tests/strategies/time_series/test_rules.py
tests/strategies/time_series/test_ml.py
```

- [ ] **Step 7: Verify layout change**

Run:

```bash
uv run python -m pytest tests/policy/test_test_layout.py -q
```

Expected: all tests pass once root-level `test_*.py` files are removed.

## Task 2: Add Unit Tests for `skills.ingest` and `skills.store`

**Files:**
- Modify: `tests/skills/ingest/test_symbol_map.py`
- Modify: `tests/skills/ingest/test_panda_data_client.py`
- Modify: `tests/skills/ingest/test_panda_future_tick.py`
- Modify: `tests/skills/store/test_data_manager.py`
- Create: `tests/skills/store/test_adjusted_quality.py`

- [ ] **Step 1: Strengthen symbol conversion tests**

Add parametrized assertions for stock, ETF, index, futures dominant contracts, round trips, unknown prefixes, and missing separators in `tests/skills/ingest/test_symbol_map.py`. Use only pure functions from `skills.ingest.symbol_map`.

- [ ] **Step 2: Strengthen PandaDataClient environment tests**

Add tests in `tests/skills/ingest/test_panda_data_client.py` for:

```python
def test_client_prefers_panda_data_env_over_pandaai_alias(monkeypatch) -> None: ...
def test_client_raises_clear_error_without_credentials(monkeypatch) -> None: ...
def test_fetch_market_data_delegates_to_sdk_with_quantspace_symbol(monkeypatch) -> None: ...
```

Use monkeypatched fake SDK objects; do not perform network calls.

- [ ] **Step 3: Cover tick helper date-range logic**

Add tests in `tests/skills/ingest/test_panda_future_tick.py` for:

```python
def test_split_date_ranges_returns_single_range_for_same_month() -> None: ...
def test_split_date_ranges_splits_across_months() -> None: ...
def test_build_tick_tasks_reports_existing_files_as_skipped(tmp_path) -> None: ...
```

- [ ] **Step 4: Cover DataManager IO and failure modes**

Add tests in `tests/skills/store/test_data_manager.py` for:

```python
def test_read_symbols_reports_all_missing_symbols(tmp_path) -> None: ...
def test_create_pool_round_trips_symbols_and_frequency(tmp_path) -> None: ...
def test_save_and_read_backtest_run_round_trips_metadata(tmp_path) -> None: ...
def test_validate_ohlcv_reports_high_less_than_low() -> None: ...
```

- [ ] **Step 5: Cover adjusted quality helpers**

Add `tests/skills/store/test_adjusted_quality.py` with deterministic adjusted/unadjusted OHLCV frames. Assert quality checks identify non-monotonic indexes, missing adjustment factors, and pass a clean adjusted panel.

- [ ] **Step 6: Verify store and ingest tests**

Run:

```bash
uv run python -m pytest tests/skills/ingest tests/skills/store -q
```

Expected: all tests pass without PandaData credentials.

## Task 3: Add Unit Tests for `skills.compute`

**Files:**
- Modify: `tests/skills/compute/test_label_maker.py`
- Create: `tests/skills/compute/test_adjust.py`
- Create: `tests/skills/compute/test_cost_model.py`
- Create: `tests/skills/compute/test_indicators.py`
- Create: `tests/skills/compute/test_regime.py`
- Create: `tests/skills/compute/test_resample.py`
- Create: `tests/skills/compute/test_ts_features.py`
- Create: `tests/skills/compute/test_utils.py`
- Create: `tests/skills/compute/test_wrappers.py`
- Modify: `tests/skills/compute/test_factor_examples.py`

- [ ] **Step 1: Label maker tests**

Expand `test_label_maker.py` to cover:

```python
def test_forward_return_label_thresholds_up_flat_down() -> None: ...
def test_triple_barrier_hits_profit_stop_and_timeout() -> None: ...
def test_label_makers_preserve_eob_index() -> None: ...
```

- [ ] **Step 2: Indicator and utility tests**

Add deterministic tests for moving averages, volatility, trend score, ATR, and price validation. Expected values should be explicit small numbers, not snapshot strings.

- [ ] **Step 3: Time-series feature tests**

Add `test_ts_features.py` with:

```python
def test_diff_feature_logdiff_matches_manual_log_difference() -> None: ...
def test_feature_base_rejects_missing_required_columns() -> None: ...
def test_ts_factor_examples_return_aligned_series() -> None: ...
```

- [ ] **Step 4: Resample and regime tests**

Add tests for daily-to-weekly/monthly OHLCV aggregation and regime classification. Use monotonic synthetic bars from `tests.fixtures.market_data.make_ohlcv`.

- [ ] **Step 5: Cost model and adjustment tests**

Add tests for trigger-time cost layers, CN session validation, single-T PnL basis-point math, and adjustment factor application.

- [ ] **Step 6: Verify compute tests**

Run:

```bash
uv run python -m pytest tests/skills/compute -q
```

Expected: all compute tests pass and do not write files outside `tmp_path`.

## Task 4: Add Unit Tests for `skills.construct`

**Files:**
- Create: `tests/skills/construct/test_weighting.py`
- Create: `tests/skills/construct/test_filters.py`
- Create: `tests/skills/construct/test_combiner.py`

- [ ] **Step 1: Weighting tests**

Cover `equal_weight`, `risk_parity`, `inverse_variance`, and `epo`:

```python
def test_equal_weight_normalizes_votes_by_row() -> None: ...
def test_risk_parity_allocates_more_to_lower_vol_asset() -> None: ...
def test_inverse_variance_allocates_more_to_lower_variance_asset() -> None: ...
def test_epo_returns_non_negative_row_weights_summing_to_one() -> None: ...
```

- [ ] **Step 2: Filter tests**

Cover market breadth, index trend scaling, and portfolio volatility targeting:

```python
def test_market_breadth_scale_reduces_exposure_below_threshold() -> None: ...
def test_index_trend_scale_applies_defensive_scale() -> None: ...
def test_portfolio_vol_targeting_caps_high_realized_volatility() -> None: ...
```

- [ ] **Step 3: Combiner tests**

Cover equal, custom, and risk-parity strategy combinations:

```python
def test_strategy_combiner_equal_method_averages_returns() -> None: ...
def test_strategy_combiner_custom_weights_are_respected() -> None: ...
def test_strategy_combiner_rejects_invalid_custom_weight_sum() -> None: ...
```

- [ ] **Step 4: Verify construct tests**

Run:

```bash
uv run python -m pytest tests/skills/construct -q
```

Expected: all construct tests pass.

## Task 5: Add Unit Tests for `skills.analyze`

**Files:**
- Modify: `tests/skills/analyze/test_backtest.py`
- Create: `tests/skills/analyze/test_factor_analysis.py`
- Create: `tests/skills/analyze/test_overlay_metrics.py`
- Create: `tests/skills/analyze/test_attribution.py`
- Create: `tests/skills/analyze/test_ts_analysis.py`
- Create: `tests/skills/analyze/test_exit_analysis.py`

- [ ] **Step 1: Backtest core tests**

Keep existing `VectorBacktester` tests and add:

```python
def test_vector_backtester_applies_signal_lag() -> None: ...
def test_vector_backtester_applies_commission_and_slippage_costs() -> None: ...
def test_vector_backtester_raises_on_active_missing_returns() -> None: ...
def test_benchmark_return_corr_aligns_on_index() -> None: ...
```

- [ ] **Step 2: Factor analysis tests**

Use a small MultiIndex factor frame and assert:

```python
def test_ic_stat_returns_expected_rank_correlation() -> None: ...
def test_group_stat_returns_group_columns_and_turnover() -> None: ...
def test_winsorize_percentile_clips_extreme_values() -> None: ...
```

- [ ] **Step 3: Overlay metric tests**

Assert explicit output for alpha, Sharpe, win rate, drawdown, and trades-per-year on deterministic series.

- [ ] **Step 4: Attribution smoke and invariant tests**

Group attribution modules into `test_attribution.py`. Cover core invariants:

```python
def test_compute_symbol_pnl_sums_to_portfolio_pnl() -> None: ...
def test_brinson_attribution_components_sum_to_total_effect() -> None: ...
def test_block_bootstrap_metric_is_deterministic_with_seed() -> None: ...
def test_white_reality_check_returns_p_value_between_zero_and_one() -> None: ...
```

- [ ] **Step 5: Time-series analysis tests**

Cover `TimeSeriesAnalyzer`, ADF/KPSS wrappers, and windowed result DataFrame shape using stationary and trending synthetic series.

- [ ] **Step 6: Exit analysis tests**

Use a two-symbol panel, one entry factor, and one exit filter. Assert `evaluate_exit_factor` returns `baseline_result_df`, `variant_result_df`, `ab_comparison`, and trigger diagnostics without plotting.

- [ ] **Step 7: Verify analyze tests**

Run:

```bash
uv run python -m pytest tests/skills/analyze -q
```

Expected: all analyze tests pass.

## Task 6: Add Unit Tests for `skills.model`, `skills.report`, and `skills.research`

**Files:**
- Create: `tests/skills/model/test_lasso_tracker.py`
- Create: `tests/skills/model/test_ml_factor.py`
- Create: `tests/skills/model/test_ml_engine_contract.py`
- Create: `tests/skills/report/test_charts.py`
- Create: `tests/skills/report/test_renderer.py`
- Modify: `tests/skills/report/test_strategy_markdown.py`
- Create: `tests/skills/research/test_factor_screening.py`
- Create: `tests/skills/research/test_param_sensitivity.py`
- Create: `tests/skills/research/test_strategy_comparison.py`

- [ ] **Step 1: Model tests**

Cover:

```python
def test_make_precomputed_factor_reads_pivot_value_for_group_dates() -> None: ...
def test_lasso_track_returns_sparse_weights_with_row_sums_bounded() -> None: ...
def test_backtest_lasso_tracker_returns_tracking_metrics() -> None: ...
def test_ml_engine_lazy_import_error_is_actionable(monkeypatch) -> None: ...
```

Do not require PyCaret to be installed; monkeypatch import failure and assert the message.

- [ ] **Step 2: Report tests**

Cover chart bytes and renderer:

```python
def test_plot_backtest_performance_returns_png_bytes() -> None: ...
def test_plot_factor_ranking_returns_png_bytes() -> None: ...
def test_report_renderer_renders_known_template() -> None: ...
def test_strategy_markdown_index_orders_metrics_table() -> None: ...
```

- [ ] **Step 3: Research tests**

Use monkeypatched small factor configs and deterministic returns. Cover:

```python
def test_screen_all_indicators_returns_ranked_dataframe() -> None: ...
def test_param_sensitivity_runs_grid_and_sorts_metric() -> None: ...
def test_strategy_comparison_aligns_return_series_on_common_index() -> None: ...
```

- [ ] **Step 4: Verify model/report/research tests**

Run:

```bash
uv run python -m pytest tests/skills/model tests/skills/report tests/skills/research -q
```

Expected: all tests pass without optional PyCaret runtime.

## Task 7: Add Unit Tests for `strategies.cross_sectional`

**Files:**
- Create: `tests/strategies/cross_sectional/test_factors.py`
- Create: `tests/strategies/cross_sectional/test_factor_frame.py`
- Create: `tests/strategies/cross_sectional/test_signals_top_pct.py`
- Create: `tests/strategies/cross_sectional/test_modular_backtester.py`
- Create: `tests/strategies/cross_sectional/test_exits.py`
- Create: `tests/strategies/cross_sectional/test_io_plotting.py`
- Modify: `tests/strategies/cross_sectional/test_rules.py`
- Modify: `tests/strategies/cross_sectional/test_ml_rank.py`

- [ ] **Step 1: Factor tests**

Cover momentum, volatility, trend, and mean-reversion scores with small explicit series. Assert NaN warmup windows and final values.

- [ ] **Step 2: Factor frame tests**

Assert `FactorFrameBuilder.build()` preserves `(symbol, eob)` order, adds `factor__<name>` columns, and returns wide pivots with date x symbol shape.

- [ ] **Step 3: TopPctStrategy tests**

Cover votes, equal weights, risk-parity weights, rebalance frequency, exit filters, and defensive allocation policies. Assert row sums and selected symbols.

- [ ] **Step 4: ModularBacktester tests**

Add tests:

```python
def test_modular_backtester_requires_explicit_slippage() -> None: ...
def test_modular_backtester_runs_with_vector_backtester_metrics() -> None: ...
def test_get_daily_weights_returns_nearest_available_date() -> None: ...
```

- [ ] **Step 5: Cross-sectional strategy example tests**

Keep migrated tests for `ma_gap_reversal_weights` and `xgboost_rank_weights`. Add:

```python
def test_rank_scores_to_weights_selects_top_n_and_normalizes() -> None: ...
def test_cross_sectional_rank_labels_align_to_panel_index() -> None: ...
```

- [ ] **Step 6: IO and plotting tests**

Use `tmp_path` and matplotlib Agg to assert IO helpers read/write expected files and plotting functions return figures/bytes without requiring a display.

- [ ] **Step 7: Verify cross-sectional strategy tests**

Run:

```bash
uv run python -m pytest tests/strategies/cross_sectional -q
```

Expected: all cross-sectional tests pass.

## Task 8: Add Unit Tests for `strategies.time_series`

**Files:**
- Modify: `tests/strategies/time_series/test_rules.py`
- Create: `tests/strategies/time_series/test_features.py`
- Modify: `tests/strategies/time_series/test_ml.py`
- Create: `tests/strategies/time_series/test_signal_engine.py`

- [ ] **Step 1: Rule tests**

Keep migrated MA/ATR stop test and add:

```python
def test_ma_reversion_atr_stop_signal_stays_flat_during_warmup() -> None: ...
def test_ma_reversion_atr_stop_signal_rejects_invalid_parameters() -> None: ...
```

- [ ] **Step 2: Feature tests**

Assert `make_price_volume_features` creates expected return, MA gap, volatility, intraday, range, and volume columns; assert returned frame has no inf values.

- [ ] **Step 3: ML signal tests**

Keep migrated probability spread and empty split tests. Add:

```python
def test_class_probability_extracts_requested_column() -> None: ...
def test_xgboost_triple_barrier_weights_returns_single_symbol_matrix() -> None: ...
```

Use a deterministic bar series with enough rows; keep estimator size as implemented and assert only shape, index, and allowed weights `{-1.0, 0.0, 1.0}`.

- [ ] **Step 4: SignalEngine tests**

Monkeypatch model predictor and feature builder. Assert the engine emits the expected prediction label, score, and mapped position for a small OHLCV buffer without loading a real model file.

- [ ] **Step 5: Verify time-series strategy tests**

Run:

```bash
uv run python -m pytest tests/strategies/time_series -q
```

Expected: all time-series tests pass.

## Task 9: Rebuild Script and Integration Tests

**Files:**
- Modify: `tests/scripts/test_import_strategy_data.py`
- Modify: `tests/scripts/test_run_strategy_reports.py`
- Create: `tests/scripts/test_demo_entrypoints.py`
- Modify: `tests/integration/test_cross_sectional_pipeline.py`
- Modify: `tests/integration/test_time_series_pipeline.py`
- Create: `tests/integration/test_strategy_reports_pipeline.py`

- [ ] **Step 1: Script unit tests**

Cover import chunking, explicit report directory behavior, stale report cleanup, and no automatic `strategy_examples` suffixing:

```python
def test_generate_reports_writes_to_exact_report_dir(tmp_path) -> None: ...
def test_generate_reports_removes_stale_markdown_and_png(tmp_path) -> None: ...
```

- [ ] **Step 2: Demo entrypoint tests**

Use `subprocess.run` with `uv run python scripts/run_cross_sectional_demo.py` and `uv run python scripts/run_time_series_demo.py` only if fixture data exists. If the implementation needs deterministic data, call `scripts/generate_sample_data.py` into a temp `QUANTSPACE_DATA_ROOT`.

- [ ] **Step 3: Integration report pipeline**

Run `scripts/run_strategy_reports.py` against local committed/sanitized data or a test-specific tmp data root. Assert four `.md` and four `_performance.png` outputs and verify both ML reports contain `sharpe_ratio`.

- [ ] **Step 4: Verify script and integration tests**

Run:

```bash
uv run python -m pytest tests/scripts tests/integration -q
```

Expected: all tests pass without network or credentials.

## Task 10: Add Contract, Regression, Documentation, and Report Structure Tests

**Files:**
- Create: `tests/contracts/test_public_api.py`
- Create: `tests/contracts/test_data_contracts.py`
- Create: `tests/regression/test_vector_backtest_regression.py`
- Create: `tests/regression/test_strategy_weights_regression.py`
- Create: `tests/docs/test_documented_examples.py`
- Create: `tests/integration/test_strategy_report_structure.py`

- [ ] **Step 1: Public API contract tests**

Add `tests/contracts/test_public_api.py` with import-contract assertions for stable public paths:

```python
def test_public_skill_import_paths_are_available() -> None:
    from skills.analyze.backtest import VectorBacktester
    from skills.store.data_manager import DataManager
    from skills.report.strategy_markdown import StrategyReport

    assert VectorBacktester is not None
    assert DataManager is not None
    assert StrategyReport is not None


def test_public_strategy_import_paths_are_available() -> None:
    from strategies.cross_sectional.ml_rank import xgboost_rank_weights
    from strategies.cross_sectional.rules import ma_gap_reversal_weights
    from strategies.time_series.ml import xgboost_triple_barrier_weights
    from strategies.time_series.rules import ma_reversion_atr_stop_weights

    assert ma_gap_reversal_weights is not None
    assert xgboost_rank_weights is not None
    assert ma_reversion_atr_stop_weights is not None
    assert xgboost_triple_barrier_weights is not None


def test_removed_backtester_import_paths_stay_removed() -> None:
    import importlib
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("strategies.cross_sectional.execution")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("strategies.time_series.backtester")
```

- [ ] **Step 2: Data contract tests**

Add `tests/contracts/test_data_contracts.py` covering standard data shapes:

```python
def test_single_symbol_bars_use_eob_datetime_index() -> None: ...
def test_panel_uses_symbol_eob_multiindex() -> None: ...
def test_vector_backtester_rejects_non_panel_input() -> None: ...
def test_data_manager_read_symbols_returns_timezone_naive_eob() -> None: ...
def test_strategy_weight_contract_is_date_by_symbol_dataframe() -> None: ...
```

Use `tests.fixtures.market_data.make_ohlcv`, `make_panel`, and `tmp_path`.

- [ ] **Step 3: Vector backtest regression tests**

Add `tests/regression/test_vector_backtest_regression.py` with deterministic expected metrics:

```python
def test_vector_backtest_fixture_metrics_do_not_drift() -> None: ...
def test_transaction_cost_regression_for_known_turnover() -> None: ...
def test_signal_lag_regression_for_known_weight_schedule() -> None: ...
```

Pin exact values for `total_return`, `turnover`, `transaction_cost`, and first/last `cum_return` on a tiny synthetic fixture.

- [ ] **Step 4: Strategy weight regression tests**

Add `tests/regression/test_strategy_weights_regression.py`:

```python
def test_ma_gap_reversal_fixture_weights_do_not_drift() -> None: ...
def test_ma_reversion_atr_stop_fixture_weights_do_not_drift() -> None: ...
def test_probability_spread_weight_mapping_do_not_drift() -> None: ...
```

Pin selected dates and selected symbols, not a full DataFrame snapshot.

- [ ] **Step 5: Documentation example tests**

Add `tests/docs/test_documented_examples.py`:

```python
def test_readme_public_import_examples_are_current() -> None: ...
def test_strategy_docs_do_not_reference_removed_backtesters() -> None: ...
def test_documented_commands_reference_existing_scripts() -> None: ...
```

Read Markdown files as text and assert documented import paths and script names are current.

- [ ] **Step 6: Report structure tests**

Add `tests/integration/test_strategy_report_structure.py`:

```python
def test_strategy_report_markdown_has_required_sections(tmp_path) -> None: ...
def test_strategy_report_index_links_all_four_reports(tmp_path) -> None: ...
def test_strategy_report_png_references_exist(tmp_path) -> None: ...
```

Do not snapshot entire Markdown files; assert title, summary, performance chart, metrics, notes, recent rows, and linked PNG existence.

- [ ] **Step 7: Verify non-unit tests**

Run:

```bash
uv run python -m pytest tests/contracts tests/regression tests/docs tests/integration -q
```

Expected: all tests pass without performance tests or private-path absence assertions.

## Task 11: Update Pytest Config, Docs, and Final Verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/README.md`
- Modify: `tests/README-zh.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add pytest markers and testpaths**

Update `[tool.pytest.ini_options]` in `pyproject.toml`:

```toml
testpaths = ["tests"]
markers = [
    "agent: live codex CLI skill checks — opt-in via RUN_AGENT_TESTS=1 (requires codex in PATH and OPENAI_API_KEY)",
    "unit: deterministic unit tests for skills and strategies",
    "integration: local integration tests without network or credentials",
    "contract: public API and data-shape contract tests",
    "regression: deterministic regression tests for key strategy/backtest behavior",
    "docs: documentation example smoke tests",
]
```

- [ ] **Step 2: Update test README docs**

Document:

```text
tests/skills/          mirrors skills/
tests/strategies/      mirrors strategies/
tests/scripts/         script entrypoint tests
tests/integration/     local end-to-end flows
tests/contracts/       public API and data contract tests
tests/regression/      deterministic behavior regression tests
tests/docs/            documentation example smoke tests
tests/policy/          test layout tests
tests/fixtures/        deterministic test data builders
```

Add commands:

```bash
uv run python -m pytest tests/skills tests/strategies -q
uv run python -m pytest tests/contracts tests/regression tests/docs -q
uv run python -m pytest tests/
```

- [ ] **Step 3: Update AGENTS.md**

Add a testing rule:

```text
When adding or changing a skill or strategy module, add or update the matching tests under tests/skills/<skill>/ or tests/strategies/<domain>/. Do not add new root-level test_*.py files.
```

- [ ] **Step 4: Run full verification**

Run:

```bash
uv run ruff check .
uv run python -m py_compile $(find skills strategies scripts tests -name '*.py' -not -path '*/__pycache__/*')
uv run python -m pytest tests/
```

Expected:

```text
All checks passed!
pytest exits 0
```

- [ ] **Step 5: Inspect final tree**

Run:

```bash
find tests -maxdepth 3 -type f | sort
rg -n "from tests.test_|import tests.test_|tests/test_.*\\.py" tests skills strategies docs AGENTS.md || true
```

Expected: no imports or docs point to old root-level test file paths.

## Implementation Notes

- Use `git mv` for existing test moves so reviewers can see renames.
- Do not use real PandaData credentials, network calls, or private market data in tests.
- Do not add compatibility wrappers for removed modules.
- Prefer exact numeric assertions on small deterministic frames over snapshots.
- Use `tmp_path`, `monkeypatch`, and local fake objects for storage, environment, SDK, and model tests.
- Keep XGBoost tests small; assert contract shape and allowed signal values, not model quality.
- Preserve unrelated dirty worktree changes unless the user explicitly asks to revert them.

## Self-Review

- Spec coverage: the plan covers all `skills/` packages, both `strategies/` domains, script/integration tests, and test directory restructuring.
- Placeholder scan: every task names exact files, concrete test functions, and verification commands.
- Type consistency: the test layout paths, package names, and current public APIs match the inspected repository state after the strategy refactor.
