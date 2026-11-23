# Backtest to Live

Read this when turning a strategy backtested in this repository into a live workflow.
The rule: the live workflow and the backtest call the same `target_weights` function,
so a live run's target is the backtest's row for that day or bar. Complete examples:
`strategies/cross_sectional/workflows/live_asset_class_rotation.py` (daily) and
`strategies/time_series/workflows/live_rb_ma_cross_5m.py` (5-minute futures).

## 1. Can it go live?

All of these must hold:

- [ ] One function `target_weights(data)` returns the eob by symbol table that
  `VectorBacktester.run` takes. No I/O, no state kept between calls, no unseeded
  randomness.
- [ ] Causal: row t uses data up to bar t's close only. `shift(-1)`,
  `rolling(center=True)`, whole-sample z-scores or a model fitted on all data fail.
- [ ] Bounded history:
  - daily: any history from a fixed `HISTORY_START`; counts that start at the
    first row (rebalance dates, holding periods) are anchored at that date
    (`rebalance_start=HISTORY_START`);
  - minute: only the last `warmup_bars` bars. The live store keeps the warm-up
    window plus `spare_days`, so trailing stops since entry, counters from the first
    row, or other state older than the window do not reproduce.
- [ ] Data the live run has: daily, whatever `load_inputs` downloads from PandaData;
  minute, `open`, `high`, `low`, `close`, `volume`, `open_interest` of the `LiveSpec`
  symbols only.
- [ ] Minute: a fixed list of futures, or of stocks and funds (not both); `1m`, `5m`,
  `15m`, `30m` or `60m`; every session a whole number of bars (rebar rules out 30m
  and 60m).
- [ ] Fast enough: a `--bar` process gets one bar, at most five minutes, including
  the Sina fetch and 7–8 seconds of orders; a daily run gets 30 minutes. Fit models
  offline or on a causal schedule, not on every bar.
- [ ] Stock and fund weights are not negative; futures may be (short). The sum of
  absolute weights is the exposure of `--capital`.

## 2. Write the workflow

One module `strategies/<domain>/workflows/live_<name>.py`. It holds only the strategy;
`skills.live_trade.workflow` parses the arguments, runs the mode, prints the JSON
report, returns the exit code, and wires `--account`.

Daily:

```python
from skills.live_trade.runner import LiveInputs
from skills.live_trade.workflow import daily_main

STRATEGY_ID = "my_rotation"          # = data/live/<id>/ and the schedule's strategy_id
HISTORY_START = "2019-01-02"         # fixed; anchors everything counted from row one

def target_weights(close):           # the backtest calls this too
    return my_rule_weights(close, rebalance_start=HISTORY_START)

def load_inputs(client, trade_date, market_dir=None) -> LiveInputs:
    adjusted = ...                   # PandaData from HISTORY_START to trade_date
    raw = ...                        # unadjusted closes, for sizing
    if market_dir is not None:       # --write only; never write data/market/
        ...
    return LiveInputs(weights=target_weights(adjusted), prices=raw)

def main(argv=None) -> int:
    return daily_main(STRATEGY_ID, load_inputs, argv)

if __name__ == "__main__":
    raise SystemExit(main())
```

Minute:

```python
from skills.live_trade.spec import Instrument, LiveSpec
from skills.live_trade.workflow import minute_main

SPEC = LiveSpec(
    strategy_id="my_rule_5m",
    frequency="5m",
    instruments=(Instrument(symbol="RB_DOMINANT.SHF", asset="future"),),
    warmup_bars=48,                  # the longest lookback, in bars
    adjust="none",                   # futures; stocks and funds default to "post"
)

def target_weights(panel):           # (symbol, eob) OHLCV panel, as in the backtest
    ...

def main(argv=None) -> int:
    return minute_main(SPEC, target_weights, argv)
```

- Keep the backtest's parameters in one place (module constants, or the strategy
  module when a backtest script shares them).
- The panel is the layout of `DataManager.read_symbols` (backtest) and
  `MinuteFeed.panel()` (live); continuous futures such as `RB_DOMINANT.SHF` keep
  their code, and the live run maps them to the day's dominant contract.
- Backtest the live function on research data of the same frequency
  (`uv run qs ingest bars --asset future --symbols RB_DOMINANT.SHF --freq 5m ...`):

  ```python
  from skills.backtest import VectorBacktester
  from skills.store.data_manager import DataManager
  from strategies.time_series.workflows import live_rb_ma_cross_5m as live

  panel = DataManager().read_symbols(live.SPEC.symbols, frequency=live.SPEC.frequency)
  result = VectorBacktester(panel, trade_at="open", signal_lag=1,
                            commission=..., slippage_bp=...).run(live.target_weights(panel))
  ```

## 3. Backtest assumptions and live timing

| Item | Backtest | Live | Where live departs |
|------|----------|------|--------------------|
| Signal row | row t from bar t's close | daily: after the close at the schedule's times; minute: `bar_delay_seconds` (default 40) after bar t ends | none; `stale` until the data has bar t |
| Execution | `signal_lag=1`: row t is held from bar t+1 (`executed_weights = weights.shift(1)`), filled at `trade_at` | daily: pushed in the evening, filled by hand next session; minute orders: best opposite quote about 50 seconds into bar t+1 | daily matches `trade_at="open"` (or `"close"` if you trade the close); minute lies between `"open"` (optimistic) and `"close"` (pessimistic). `signal_lag=0` with `trade_at="close"` fills at the close the signal used, which live cannot do |
| Adjustment | the series you backtested | daily: whatever `load_inputs` builds (rotation: post, like `1d_adj`); minute stocks and funds `adjust="post"`; futures never | scale-free signals (returns, MA cross sign, ranks) agree under pre and post; level-based ones (price thresholds, ATR in points) need the same series. Futures on a post-adjusted dominant series can differ from live near rolls; backtest the unadjusted series for the same signals (its returns then include roll gaps) |
| Units | fractional weights | `weight * capital / (raw close * multiplier)` rounded toward zero to whole contracts or `--lot-size` shares | under-exposure with little capital: 100000 on rebar at 3010 x 10 is 3 contracts, 90% |
| Costs and fills | constant `commission`, `slippage_bp`; constraints only with `enforce_trade_constraints` | the spread; `working` orders are re-targeted next bar; `rejected` | real costs and partial fills |
| Continuous futures | holds the continuous series | trades the dominant actual contract; on a roll day other months go to 0 | roll trades and their cost |
| Data | final PandaData bars | Sina bars, revised 10–30 seconds after the close (80 for the first bars after the open) | the next refresh alerts `reconcile` for every bar whose target changed |
| Missing runs | none | `missed` past the deadline, `stale` days, halted stocks keep their last weight | gaps the backtest never has |

## 4. Verify

Offline tests in `tests/strategies/<domain>/test_live_<name>.py`, with the fakes in
`tests/skills/live_trade/fakes.py`:

- [ ] Same function: `workflow.target_weights(panel).equals(rule(bars, ...))` with the
  backtest's parameters, as in `test_target_weights_are_the_backtest_function`
  (`tests/strategies/time_series/test_live_rb_ma_cross_5m.py`).
- [ ] Live reproduces the backtest rows, on synthetic history where the weights change:
  `replay_mismatches(workflow.target_weights, history, window=SPEC.warmup_bars) == []`
  for minute, `window=None` (from the first row) for daily. Also assert that a shorter
  window fails, so the check is known to bite.
- [ ] End to end: monkeypatch `skills.ingest.PandaDataClient` (and
  `skills.ingest.akshare_bars._load_akshare` with `FakeSina`), run
  `main(["--refresh", "--now", ...])` then `main(["--bar", ..., "--now", ...])`, and
  check the report's `target` is the backtest's row. Daily: a fake client with
  `get_trade_cal` and the download calls.
- [ ] By hand, previews only: `--bar <end> --now <end + 45 s>` on a bar of the current
  trading day; `--test`, then `--test --write` for the IM path.
- [ ] Live: `reconcile` alerts and `data/live/<id>/reconcile/<date>.signals.json`.

## 5. Schedule

Add a job to the schedule file (see [schedule.example.json](schedule.example.json)):

- Daily: `strategy_id`, `module`, `days`, `times` after PandaData has the day (ETFs
  `17:30`, then retries), `args` such as `["--capital", "100000"]`. The last time runs
  with `--final` and alerts stale data.
- Minute: add `"frequency": "5m"`; `times` are the refreshes (futures `18:00` and
  `20:00`, stocks and funds `08:30`); bars are ticked every 10 seconds.
- `strategy_id` equals the workflow's. Then
  `uv run qs live-trade serve --config <file> --check`, a run without `--write`
  (previews), and `--write`.

## 6. Automatic futures orders: SimNow only

- Minute futures only: add `--capital <amount> --account <PandaAI account code>` to
  the job's `args`; `serve` adds `--write`. Daily workflows only push signals.
- Each bar trades only a SimNow account (broker `9999`) with CLI mode on and the
  counter ready; anything else is `blocked`. A real account never trades
  automatically; this is fixed in code, not configuration.
- Run without `--account` until the signals look right; `uv run qs live-trade doctor`
  lists the accounts and why each is or is not usable.
