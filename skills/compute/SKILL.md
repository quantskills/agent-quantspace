---
name: compute
description: Use when tasks need strategy-agnostic OHLCV indicators, math utilities, generic factor examples, regime slicing, resampling, or label makers.
---

## Description

Compute derived values from OHLCV data. This skill is organized in reusable, strategy-agnostic layers:

| Layer | Module | Contents |
|-------|--------|----------|
| **Utils** | `skills.compute.utils` | Math primitives: `safe_divide`, `rolling_zscore`, `calculate_atr`, `clip_outliers`, etc. |
| **Indicators** | `skills.compute.indicators` | 41 public technical indicators: `rsi`, `trend_score`, `er`, `supertrend`, etc. |
| **Features** | `skills.compute.features` | Strategy-agnostic OHLCV feature builders such as `make_logdiff_features` |

Also: label makers (`label_maker.py`), compact generic factor examples, and the `Factor` wrapper.

Shared market-structure helpers used by strategy domains:

- `skills.compute.resample.resample_to_5m(df_1m)` — A-share 1m eob OHLCV to 5m eob bars without crossing lunch break; keeps `09:31-11:30` and `13:01-15:00`, removes zero-volume rows, and preserves OHLCV aggregation.
- `skills.compute.regime.split_by_regime(df, regimes=None)` — lithium-cycle date slicing for DatetimeIndex or MultiIndex inputs.

**Strategy-specific factors and feature engineering** live in `strategies/`, not here — except generic single-instrument OHLCV transforms such as log-difference grids, which belong in `skills.compute.features`.

## Prerequisites

- **Python**: `pandas`, `numpy`; some indicators use `statsmodels`.
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

41 public functions organized by category:

- **Price/Momentum**: `roc`, `ma`, `daily_return`, `ma_cross`, `price_above_ma`, `momentum_acceleration`, `momentum_weighted`, `bias_momentum`, `mom_skip`, `high_vol_odds`
- **Trend**: `rsrs`, `rsrs_v1`–`v3`, `rsrs_norm`, `trend_score`, `trend_score_v2`, `trend_score_v2_skip`, `supertrend`, `donchian_channel`
- **Volume**: `ma_vol`, `ma_vol_ratio`, `orb`, `orb_relvol`, `stand_orb_relvol`
- **Efficiency**: `er`, `er_enhanced`, `er_adaptive`, `er_directional`
- **Oscillators**: `cci`, `slowkdj`, `williams_r`, `rsi`, `rsi_divergence`
- **Mean-reversion**: `bollinger_reversal`, `mean_reversion`, `price_drawdown`
- **Volatility/Risk**: `atr_stop`, `volatility_regime`, `volatility_inv`, `fund_premium_rate`

### `Factor` wrapper (`skills.compute.wrappers`)

```python
from skills.compute.wrappers import Factor
from skills.compute.indicators import trend_score_v2
```

- `__init__(func: Callable, **params)` — binds callable and defaults; `name` from `func.__name__` and params.
- `calculate(data: pd.DataFrame, *, dropna: bool = True) -> pd.Series` — per-symbol apply with index contract checks. **Legacy default `dropna=True` is preserved** for existing research callers. Pass `dropna=False` for full-index / warm-up NaN preservation (factor_mining Phase 02 always does this).
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

- `make_logdiff_features(bars, *, factors=..., lags=..., shifts=None, lookback=5)` — single-symbol OHLC log-difference grid. Default aligns with the lesson-07 reference notebook: 4×4 factor pairs × 9 lags × 10 shifts = **1440** columns when `lookback=5`. Non-positive prices become NaN instead of `-inf`.
- `make_logdiff_panel_features(panel, ...)` — same grid applied per symbol on a `(symbol, eob)` panel, non-finite rows dropped, so the result is model-ready. Build once and reuse across horizons/models.
- `default_logdiff_shifts(lookback)` — `{0..lookback-1} ∪ {5,10,...,lookback*5}`.
- No duplicate log-difference implementation under `strategies/`.

### Label Generation (`skills.compute.label_maker`)

```python
from skills.compute.label_maker import ForwardReturnLabelMaker, TripleBarrierLabelMaker
```

Public supervised-learning labels:

- `ForwardReturnLabelMaker`: forward-return threshold labels.
- `TripleBarrierLabelMaker`: AFML-style volatility-scaled triple-barrier labels.

## Factor categories (illustrative)

Momentum/trend, volume, mean reversion, exit filters (`skills.strategy.cross_sectional.exits`), and label makers.
