---
name: construct
description: Portfolio weighting (equal, risk parity, inverse variance, EPO), portfolio-level risk filters, and multi-strategy return blending.
---

## Description

Turn **signals into weights**, apply **macro-style overlays** (breadth, index trend, vol targeting), and **blend multiple strategy return series** (equal, risk parity, or custom weights).

## Prerequisites

- **Python**: `pandas`, `numpy`; **EPO** needs `scipy` (`scipy.linalg.solve`).
- **Weighting**: `votes_df` (date × symbol, non-zero = selected); `returns_df` (date × symbol daily returns) for variance-based methods.
- **Filters**: `weights_df` aligned with `close_pivot` and `returns_df`; optional `index_close` for trend scaling.
- **Combiner**: `dict[str, pd.Series]` of **daily** returns on a common index.

## API Reference

### Weighting (`skills.construct.weighting`)

```python
from skills.construct.weighting import WEIGHT_METHODS, equal_weight, risk_parity, inverse_variance, epo
```

- `equal_weight(votes_df, **kwargs) -> pd.DataFrame`
- `risk_parity(votes_df, returns_df, lookback=60, min_periods=20, **kwargs)`
- `inverse_variance(votes_df, returns_df, lookback=60, min_periods=20, **kwargs)`
- `epo(votes_df, returns_df, lookback=1200, min_periods=60, lambda_=10.0, shrink_w=0.2, **kwargs)`

`WEIGHT_METHODS = {"equal": equal_weight, "risk_parity": risk_parity, "inverse_variance": inverse_variance, "epo": epo}`.

### Portfolio filters (`skills.construct.filters`)

```python
from skills.construct.filters import (
    calculate_market_breadth,
    calculate_index_trend,
    apply_market_breadth_scale,
    apply_index_trend_scale,
    apply_portfolio_vol_targeting,
    apply_portfolio_filters,
)
```

- `apply_portfolio_filters(weights_df, close_pivot, returns_df, index_close=None, market_breadth_config=None, index_trend_config=None, vol_target_config=None) -> pd.DataFrame`

Helpers may print summary lines when applied.

### Strategy combiner (`skills.construct.combiner`)

```python
from skills.construct.combiner import StrategyCombiner
```

- `StrategyCombiner(strategies: Dict[str, pd.Series], method="equal", custom_weights=None, lookback=60)`
- `method`: `'equal'`, `'risk_parity'`, or `'custom'`.
- `run() -> pd.DataFrame` — sets `result_df` and `metrics`; columns include per-strategy returns, `combined_return`, `cum_combined`, `drawdown`.

## Recipes

**1. Weight selected names**

```python
import pandas as pd
from skills.construct.weighting import equal_weight, epo

w_equal = equal_weight(votes_df)
w_epo = epo(votes_df, returns_df, lookback=252, min_periods=60)
```

**2. Overlays after base weights**

```python
from skills.construct.filters import apply_portfolio_filters

w_scaled = apply_portfolio_filters(
    w_equal,
    close_pivot,
    returns_df,
    index_close=bench_close,
    market_breadth_config={"breadth_threshold": 0.35, "scale_below": 0.6},
    vol_target_config={"vol_target": 0.12, "lookback": 60},
)
```

**3. Combine sub-strategies**

```python
from skills.construct.combiner import StrategyCombiner

combiner = StrategyCombiner(
    {"mom": mom_ret, "carry": carry_ret},
    method="custom",
    custom_weights={"mom": 0.6, "carry": 0.4},
)
out = combiner.run()
```

Use `WEIGHT_METHODS[backtester_weight_method]` when matching cross-sectional engine `weight_method` strings (`equal`, `risk_parity`, etc.).
