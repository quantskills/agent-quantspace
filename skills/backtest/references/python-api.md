# Backtest Python API

Read this when changing the `backtest` Skill or writing strategy code. For research tasks use the `uv run qs backtest` commands in [../SKILL.md](../SKILL.md).

Backtest is the shared portfolio execution and construction boundary. Strategy
domains should produce date x symbol weights; this skill turns those weights
into executed weights, returns, costs, diagnostics, and report-ready metrics.

## Public API

```python
from skills.backtest import VectorBacktester, annual_return_metrics, percent_to_lots
from skills.backtest.units import SHARES_PER_LOT, check_lots, is_futures_symbol
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
| `skills.backtest.units` | Target units `percent` and `lots`: `SHARES_PER_LOT` (100), `is_futures_symbol`, `is_continuous_future`, `units_per_lot`, `check_lots`, `check_lots_table` (whole lots, no short stocks; raise, never round). Live trading uses the same rules |
| `skills.backtest.quantity` | Lots bookkeeping behind `VectorBacktester(unit="lots")` (`lots_frame`, `lots_metrics`), `percent_to_lots`, `trading_days` (night session to the next trading day), `apply_tplus` |
| `skills.backtest.weighting` | Equal weight, risk parity, inverse variance, EPO, `WEIGHT_METHODS` |
| `skills.backtest.filters` | Market breadth, index trend, and volatility targeting overlays |
| `skills.backtest.combiner` | Blend multiple strategy return streams |
| `skills.backtest.cost_model` | A-share trigger-time cost layers and single-trade PnL helpers |
| `skills.backtest.exit_analysis` | Baseline vs filtered exit A/B evaluation |
| `skills.backtest.overlay_metrics` | Overlay alpha, win rate, drawdown, Sharpe, and regime metrics |

`VectorBacktester` requires explicit `commission` and `slippage_bp` (a missing
value raises `ValueError`). Each date's executed weight always earns the
next bar's return, which is the safe convention for close-derived signals.

`unit="lots"` (keyword-only, with `capital`) books a lots table by quantity:
`data` holds unadjusted prices, including every actual contract a continuous
future maps to; `multipliers` by target symbol; `contracts` is the trading day by
continuous symbol table (`DataManager.read_dominant`); `adjusted` the
post-adjusted `(symbol, eob)` panel of stocks and funds; `margin_rates` only
reports the margin in use. The profit of bar t is lots x units per lot x the
held contract's move to bar t+1 (stocks: unadjusted value x adjusted return);
a roll closes the old contract and opens the new one at their own prices on
the roll bar, both legs paying `commission + slippage_bp` on traded value;
equity starts at `capital` and a bar's return is its net profit over the
equity before it. Intraday stock and fund lots follow T+1. `result_df` adds
`pnl`, `cost`, `equity_value`, `gross_exposure`, `rolls`, `blocked_sell_lots`
(and `margin_ratio`); `BacktestResult.executed_lots` holds the lots held and
`executed_weights` the exposure they imply; metrics add `total_pnl` (before
costs), `total_cost`, `final_equity_value` (capital + `total_pnl` - `total_cost`),
`max_gross_exposure`, `roll_count`, `blocked_sell_lots`.
Lots-only options with `unit="percent"`, and `enforce_trade_constraints` with
lots, raise.

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

**Backtest whole lots, futures on the contracts actually held**

```python
from skills.backtest import VectorBacktester
from skills.store.data_manager import DataManager

dm = DataManager()
contracts = dm.read_dominant(["RB_DOMINANT.SHF"])          # qs ingest contracts --write
codes = sorted(set(contracts.stack().dropna()))
data = dm.read_symbols(["RB_DOMINANT.SHF", *codes], frequency="1d")
result = VectorBacktester(
    data, trade_at="close", signal_lag=1, commission=0.0001, slippage_bp=1.0,
    unit="lots", capital=1_000_000, multipliers={"RB_DOMINANT.SHF": 10},
    contracts=contracts,
).run(lots_df)                                              # whole contracts per bar
```

**What D11 costs: a percent strategy held as live trading holds it**

```python
lots = percent_to_lots(weights_df, raw_close, capital=1_000_000,
                       multipliers={"RB_DOMINANT.SHF": 10})
held = VectorBacktester(..., unit="lots", capital=1_000_000, ...).run(lots)
```

`percent_to_lots` sizes a symbol only on rows where its weight changed (toward
zero, stocks in 100-share lots) and keeps the lots while prices drift; compare
`held` with the percent backtest, which returns to the weights on every bar.

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
