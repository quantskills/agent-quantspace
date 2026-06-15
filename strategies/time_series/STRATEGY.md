---
name: time_series
description: Public single-instrument time-series workflow covering raw bars, features, labels, weights, and vectorized backtesting.
---

# Time-Series Strategy

This domain demonstrates a single-instrument workflow:

```text
raw OHLCV bars -> features/rules/public labels -> weights -> VectorBacktester
```

## Components

| Step | Module | Import |
|------|--------|--------|
| Features | `strategies.time_series.features` | `from strategies.time_series.features import make_price_volume_features` |
| Labels | `skills.compute.label_maker` | `from skills.compute.label_maker import TripleBarrierLabelMaker` |
| Rule weights | `strategies.time_series.rules` | `from strategies.time_series.rules import ma_reversion_atr_stop_weights` |
| ML weights | `strategies.time_series.ml` | `from strategies.time_series.ml import xgboost_triple_barrier_weights` |
| Backtest | `skills.backtest` | `from skills.backtest import VectorBacktester` |
| Live signal | `strategies.time_series.signal_engine` | `from strategies.time_series.signal_engine import SignalEngine` |

## Typical Workflow

```python
from skills.backtest import VectorBacktester
from strategies.time_series.ml import xgboost_triple_barrier_weights

weights = xgboost_triple_barrier_weights(
    bars,
    symbol="CFFEX.IF99",
    split_date="2024-01-01",
)
panel = bars.assign(symbol="CFFEX.IF99").reset_index().set_index(["symbol", "eob"])

result = VectorBacktester(
    panel,
    trade_at="close",
    signal_lag=1,
    commission=0.0002,
    slippage_bp=2.0,
).run(weights)
```

## Design Notes

- Public time-series labels use `TripleBarrierLabelMaker` from `skills.compute`.
- Strategy-specific code maps features, rules, and model outputs to target weights.
- Return accounting and metrics use `skills.backtest.VectorBacktester`.
- Private label experiments are outside the open-source boundary.
