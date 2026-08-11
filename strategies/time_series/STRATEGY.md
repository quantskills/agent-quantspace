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
| Cash-flow index trend rule | `strategies.time_series.cashflow_trend` | `from strategies.time_series.cashflow_trend import cashflow_trend_weights` |
| Cash-flow volatility/recovery rules | `strategies.time_series.cashflow_vol_recovery` | `from strategies.time_series.cashflow_vol_recovery import cashflow_vol_recovery_weights` |
| Cash-flow Donchian/ATR rule | `strategies.time_series.cashflow_donchian_atr` | `from strategies.time_series.cashflow_donchian_atr import donchian_atr_weights` |
| Cash-flow total-return mean reversion | `strategies.time_series.cashflow_total_return_mean_reversion` | `from strategies.time_series.cashflow_total_return_mean_reversion import cashflow_mean_reversion_weights` |
| ML weights | `strategies.time_series.ml` | `from strategies.time_series.ml import xgboost_triple_barrier_weights` |
| Signal to weights | `skills.strategy.time_series` | `from skills.strategy.time_series import signal_to_single_asset_weights` |
| Backtest | `skills.backtest` | `from skills.backtest import VectorBacktester` |

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
- `skills.strategy.time_series.TimeSeriesBacktester` is a research-only adapter
  backed by `VectorBacktester`; formal public results use explicit target weights.
- Private label experiments are outside the open-source boundary.
- `cashflow_trend_weights` is a close-only rule for index histories whose
  official pre-launch backfill lacks usable OHLC. Its documented ATR proxy is
  Wilder-smoothed absolute close change; it never substitutes invented highs
  or lows.
- `cashflow_vol_recovery_weights` compares continuous target-volatility,
  volatility-band, and hybrid loss-reduction sizing. A close-based loss stop
  enters a recovery state; re-entry requires a cooldown, a configured price
  recovery, and restoration of the positive trend regime.
- `donchian_atr_weights` is a long-only close-channel breakout with closing-low
  and initial/trailing ATR-proxy exits. It supports fixed or target-volatility
  sizing while retaining the close-only historical-data constraint.
- `cashflow_mean_reversion_weights` keeps a long core, adds a bounded satellite
  during oversold pullbacks in a rising long trend, and temporarily de-risks
  after a first crossing of the distance from the rolling low. Loss stops apply
  only to the incremental satellite and recovery re-entry uses hysteresis.
