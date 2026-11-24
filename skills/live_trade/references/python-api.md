# Live Trade Python API

Read this when changing the `live_trade` Skill or writing strategy code. For
signal tasks use the `uv run qs live-trade` commands in [../SKILL.md](../SKILL.md).

Strategies produce date x symbol target weights. This Skill turns the latest row
into a rebalance signal, sizes it into tradable units, and delivers it: IM
webhooks for any symbol, and (later) the PandaAI live-trading client for futures.

## Public API

```python
from skills.live_trade import (
    TargetSnapshot,
    build_signal,
    size_targets,
    SignalLedger,
    format_signal,
    load_notify_urls,
    send_notifications,
    discover_cli,
)

snapshot = TargetSnapshot.from_frames(weights, "etf_rotation", prices=close)
ledger = SignalLedger("etf_rotation")
signal = build_signal(snapshot, ledger.base_weights())
sized = {
    item.symbol: item
    for item in size_targets(
        {change.symbol: change.target for change in signal.changes},
        1_000_000,
        signal.prices,
        multipliers={"RB2701.SHF": 10},
    )
}
title, body = format_signal(signal, sized)
urls = load_notify_urls()
results = send_notifications(title, body, urls)
ledger.record(signal, results, [result.channel for result in results])
```

## Components

| Module | Purpose |
|--------|---------|
| `skills.live_trade.contracts` | `TargetSnapshot`, `WeightChange`, `Signal`, `DeliveryResult`, `build_signal`, `diff_weights`, `is_futures_symbol` |
| `skills.live_trade.sizing` | `size_targets` and `SizingLimitError`: weights to contracts or board lots, with unit and notional caps that raise instead of clipping; `describe_lots` and `LotsTarget`: shares, value, and share of capital of lot targets for messages |
| `skills.live_trade.ledger` | `SignalLedger`: last fully delivered target and per-channel results under `data/live/<strategy_id>/ledger.json` |
| `skills.live_trade.notify` | `NOTIFY_ENV` per-IM variables (`QS_NOTIFY_WECOM`, `QS_NOTIFY_FEISHU`, `QS_NOTIFY_DINGTALK`, `QS_NOTIFY_SLACK`, `QS_NOTIFY_DISCORD`) with platform checks, IM URL normalization, redacted channel labels, message formatting, delivery (WeCom, Feishu, DingTalk posted directly and checked by error code; Slack, Discord via Apprise) |
| `skills.live_trade.runner` | `run_live`, `LiveInputs`, `RunOutcome`, `RunLog`, `DataNotReady`, `deliver_signal`, `send_alert`, `trade_target`, `futures_lots`, `stop_file`: one scheduled run of a trade date (trading-day and freshness checks, delivery, run log, alerts) and the futures order step shared with minute bars |
| `skills.live_trade.daily` | `load_daily_bars`, `DailyBars`, `DailyNotReady`, `CUTOFF`, `RUN_TIMES`, `INTRADAY_SOURCE`: a daily strategy's bars at 14:50, PandaData to yesterday plus today's bar from 1-minute bars of Sina or (futures) TqSdk |
| `skills.live_trade.history` | `daily_bars`, `daily_closes`, `close_table`, `adjustment_factors`, `today_factors`, `dominant_contracts`, `contract_multipliers`: PandaData daily data shared by the daily and minute feeds |
| `skills.live_trade.scheduler` | `ScheduleConfig`, `JobConfig`, `run_job`, `tick`, `catch_up`, `build_scheduler`, `next_runs`, `run_until_stopped`, `serve`: APScheduler 3.x cron triggers that start workflow processes |
| `skills.live_trade.workflow` | `daily_main`, `minute_main`, `workflow_arguments`, `is_trading_day`, `load_with_relogin`, `replay_mismatches`: the command-line entry of a strategy workflow module, and the check that a live run reproduces the backtest's rows |
| `skills.live_trade.spec` | `LiveSpec`, `Instrument`: what a minute-level strategy trades, its bar interval, warm-up, price adjustment, and bar timing |
| `skills.live_trade.clock` | `TradingCalendar`, `Session`, `parse_trading_hours`, `bar_ends`, `bars_per_day`, `has_night_session`, `due_bars`, `EQUITY_SESSIONS`: trading sessions and bar end times |
| `skills.live_trade.feeds` | `MinuteFeed`, `FeedState`, `read_feed_state`, `upcoming_trading_date`, `FeedNotReady`: PandaData history plus today's bars from the spec's intraday source (Sina, or TqSdk ticks for futures) in the live store |
| `skills.live_trade.minute` | `run_bar`, `refresh_day`, `reconcile_signals`, `RefreshOutcome`, `SignalMismatch`: one bar per run, the pre-open refresh, and reconciliation |
| `skills.live_trade.panda_cli` | The PandaAI client's bundled `panda-live-trading` CLI: `discover_cli`, `cli_version`, `run_cli`, `list_accounts` (`PandaAccount`), `capability_problems`, `version_problem`, `require_actual_contract`, `PandaCliError` |

## Contracts

- `TargetSnapshot.from_frames(weights, strategy_id, as_of=None, prices=None,
  unit="percent")` takes the weights row at or before `as_of`, treats missing
  weights as zero, and keeps only nonzero targets. Missing prices stay missing.
  With `unit="lots"` the row holds whole lots (a futures contract, or 100 shares
  of a stock or fund, `skills.backtest.units`); fractions and negative stocks or
  funds raise `ValueError`. `TargetSnapshot.unit` and `Signal.unit` carry it.
- `build_signal(snapshot, previous)` hashes strategy, time, base, and target
  (and, for lots only, the unit) into `signal_id`, so the same inputs always give
  the same id and percent ids are unchanged. `changes` includes exits to zero.
- `describe_lots(lots, prices, multipliers=None, capital=None)` returns a
  `LotsTarget` per symbol (`lots`, `shares` of stocks and funds, `price`,
  `notional`, `share_of_capital`, and `units`: contracts or shares); it never
  rounds or resizes. `format_signal` writes a lots signal as
  `目标 3 手（原 2 手），参考价 2999，名义 89970，折合 89.97%`.
- `size_targets(weights, capital, prices, multipliers=..., lot_size=100,
  rounding="down", max_units=None, max_notional=None)` computes
  `weight * capital / (price * multiplier)`. Futures (PandaData suffixes `.SHF`,
  `.DCE`, `.CZC`, `.CFE`, `.INE`, `.GFE`) size in whole contracts and need a multiplier.
- `SignalLedger.record(signal, results, channels)` returns whether every
  channel has the signal; only then does the signal's target become the new base
  (a lots base also keeps `unit`). `base_unit()` is the base's unit (`percent`
  for a base without one) or None; `base_weights(unit=None)` is empty when the
  base is in another unit.
- `load_notify_urls(environ=None)` reads one variable per IM from `NOTIFY_ENV`
  (process environment, with `.env` filling unset ones); a variable may hold
  several comma-separated URLs, and a URL of another platform raises `ValueError`.
- `send_notifications(title, body, urls)` sends to each URL separately and
  returns one `DeliveryResult` per channel; failure details have the webhook
  URL redacted. WeCom, Feishu, and DingTalk reject messages with HTTP 200 and an
  error code in the body, so they are posted directly with `requests` and count
  as delivered only when that code is 0. Slack and Discord go through Apprise.
  Install both with `uv sync --extra live`.
- `discover_cli()` checks `PANDA_LIVE_CLI`, then the client's bundled CLI from
  `client_bundles()`, then `panda-live-trading` on `PATH`. On macOS that is the
  launcher (`CLIENT_RUNTIME` `/Applications/PandaAI.app/Contents/MacOS/PandaAI`
  running `BUNDLED_CLI` `.../Contents/Resources/cli/bundled-launcher.mjs`, the
  entry the client's AI guide gives). On Windows it is `PandaAI.exe` in the
  folder of the client's uninstall entry (`InstallLocation`, else the folder of
  `DisplayIcon`), then `%LOCALAPPDATA%\Programs\PandaAI` and
  `%ProgramFiles%\PandaAI`, running `resources\cli\bundled-launcher.mjs` or, in
  clients without it, `resources\cli\panda-live-trading.mjs`. CLI output is read
  as UTF-8 on every OS.
- `run_cli(command, *args, env=None)` returns the CLI's `data` and raises
  `PandaCliError` (with the CLI's error `code`) on `ok: false` or output that is
  not JSON. Every call sets `ELECTRON_RUN_AS_NODE=1`, `PANDA_LIVE_ACTOR=AI` and
  `PANDA_LIVE_ACTOR_ID=quantspace-live-trade`; `env` adds more, such as
  `PANDA_LIVE_TRACE_ID`. The client's update check stays on.
- `execution.PandaTrader(command, account, trace_id="", runner=run_cli)` wraps
  the calls for one account (`accounts`, `connection`, `connect`, `positions`,
  `orders`, `operation`, `cancel`, `target-position --targets`, `plan execute
  --yes`); queries are tried twice, `connect`, cancels and plan executions once.
  `execution.execute_targets(trader, wanted, request_id=, wait_seconds=30,
  reconnect_seconds=20)` brings a SimNow account to `wanted` whole contracts per
  actual contract (negative is short) and returns an `ExecutionResult`
  (`status`, `detail`, `account`, `wanted`, `before`, `after`, `cancelled`,
  `plan_id`, `legs` of `LegResult`, `reconnected`); see the Skill for the steps
  and statuses. A counter that is not ready on an eligible account goes through
  `reconnect(trader, wait_seconds=)` first (one `connect` when disconnected,
  then waiting; `""` once ready, else why not; `reconnect_seconds=0` turns it
  off), and `reconnected` keeps what was wrong. `check_account` raises
  `ExecutionRefused` for anything but an eligible SimNow account;
  `account_problems(account)` lists why, `counter_problem(connection)` says why
  a counter takes no orders, and `trading_problems(trader)` returns the account
  and every reason it cannot trade now, counter state included (what `doctor
  --account` reports; `doctor` itself never reconnects).
- `list_accounts(command)` returns `PandaAccount` items; `is_simnow` means
  broker `9999` (`SIMNOW_BROKER_ID`), `cli_eligible` and `unavailable_reason`
  come from the client.
- `capability_problems(capabilities)` lists missing features this Skill needs
  (contract specs, GFD limit orders in batch plans); `version_problem(version)`
  checks the CLI is at least `0.1.11`.
- Symbols are PandaData codes everywhere (`510300.SH`, `RB2701.SHF`), the same
  strings the client CLI takes, so nothing is converted.
  `require_actual_contract("RB2701.SHF")` returns the code unchanged and refuses
  non-futures and dominant-continuous codes such as `RB_DOMINANT.SHF`, because
  orders and positions match actual contracts.

## Scheduled runs

A strategy workflow module (under `strategies/<domain>/workflows/live_*.py`)
supplies the data and the target table; `skills.live_trade` never imports it. The
steps and checks of writing one are in [backtest-to-live.md](backtest-to-live.md).

```python
from skills.live_trade.daily import load_daily_bars
from skills.live_trade.runner import LiveInputs
from skills.live_trade.workflow import daily_main

def load_inputs(client, trade_date, market_dir=None) -> LiveInputs:
    bars = load_daily_bars(client, SYMBOLS, HISTORY_START, trade_date, asset="fund")
    return bars.inputs(target_weights(bars.close))

def main(argv=None) -> int:
    return daily_main("my_strategy", load_inputs, argv)
```

- `load_daily_bars(client, instruments, start, trade_date, asset=None,
  adjust="post", cutoff=CUTOFF, now=None)` returns `DailyBars`: `panel` (signal
  bars) and `raw_panel` (unadjusted), `(symbol, eob)` panels of open, high, low,
  close, volume whose last day is `trade_date` at the cut-off (14:50); `close`
  and `raw_close`, their closes as eob by symbol tables; `contracts`,
  `multipliers`, today's `factors`, `suspended`, `notes` and `inputs(weights)` (a
  `LiveInputs` with raw closes as prices, multipliers, contracts and notes).
  History is PandaData daily bars (`daily_bars`) from `start` to the previous
  trading day; today's bar aggregates the 1-minute bars of the trading day
  up to `cutoff` (first open, highest high, lowest low, the cut-off close, summed
  volume), prices times today's factor
  (`today_factors(client, items, last, trading_date, last_closes=, pre_closes=)`:
  the previous day's post/raw ratio, times yesterday's close over today's
  previous close when they differ, as on an ex-date; a stock's published
  `ex_cum_factor` first). Today's previous close comes from PandaData once the
  day is published, else from `fetch_sina_quotes` (`skills.ingest.akshare_bars`).
  Futures continuous symbols take the dominant contract's price and are never
  adjusted. It raises `DailyNotReady` (a `DataNotReady`) while a cut-off bar or
  today's previous close is missing, or a stock with an announced ex-date has
  neither a published factor nor a moved previous close. A minute without trades
  has no Sina bar, so the close is the last trade at or before the cut-off once a
  later bar is out or `SETTLE` (two minutes, five for futures) has passed; a stock
  or fund with no trade today keeps the previous close with no volume and is
  listed in `suspended`. `instruments` are
  `Instrument`s, or symbols of one `asset`. `source` (`akshare` or `tqsdk`; None
  takes `INTRADAY_SOURCE`, which `daily_main` sets from `--intraday-source`)
  picks where futures' 1-minute bars come from; stocks and funds always come from
  Sina. `DailyBars.source` records what was used (`akshare`, `tqsdk`, or
  `tqsdk+akshare`) and the first note says it.
- `daily_main(strategy_id, load, argv=None, *, unit="percent")` parses `workflow_arguments(argv)`
  (`--date`, `--write`, `--final`, `--test`, `--data-root`, `--capital`,
  `--lot-size`, `--account`, `--max-lots`, `--intraday-source`), asks PandaData's calendar
  `is_trading_day(client, date)` (a calendar failure becomes the run's `error`),
  and passes `run_live` a loader that calls `load(client, trade_date, market_dir)`
  through `load_with_relogin(load, make_client, trade_date, market_dir)`: once
  more on a fresh client when PandaData drops the login. `--test` loads
  `latest_inputs(load, make_client, date)` instead: the newest trading day at or
  before the date whose data is ready. `market_dir` is
  `<data_root>/live/<strategy_id>/market` with `--write` outside `--test`, else
  None. With `--account` a futures strategy's target is traded at the cut-off
  (`run_live(..., execute=, max_lots=)`). `unit` is the unit of the table
  `load` returns and goes to `run_live(..., unit=)`. It prints one JSON report
  (`strategy_id`, `trade_date`, `status`, `detail`, `execution`, `signal_id`,
  `target`, `message`, `deliveries`, `alerts`) and returns `RunOutcome.exit_code`.
- `run_live` returns `not_trading_day` without calling `load`, and `done`
  without calling it when `RunLog` already finished the date (`write` only).
  A loader that raises `DataNotReady`, or weights whose last row is before the
  date, are `stale`; weights after it, an `error`. The signal is the row of the
  date itself, with `LiveInputs.notes` appended to the message. With `write` and
  `execute`, the full target goes through `trade_target` (below) after the signal.
- `trade_target(strategy_id, trade_date, label, wanted, execute, request_id=,
  runs=, urls=None, closed="")` is the order step of daily runs and minute bars:
  no order when `closed` says why the market takes none now (`closed`, not
  alerted), while `stop_file(strategy_id, data_root)` (`live/<id>/STOP`) exists
  (`stopped`), or when `wanted()` raises `SizingLimitError` (`over_limit`);
  otherwise `execute(wanted(), request_id)`. A run that placed orders pushes a
  `trade` message, other problems alert `execution_<status>` once per trade
  date, and a result with `reconnected` alerts `execution_reconnected` once per
  trade date. `run_live(..., closed="")` passes `closed` on; `daily_main` sets it
  outside 14:50–15:00 (`daily.CUTOFF`, `daily.DAY_CLOSE`) of the trade date, and
  `run_bar` outside the day's sessions (`clock.in_session(now, bar_ends,
  frequency)`, from `clock.trading_windows`). `futures_lots(weights, prices, contracts=, multipliers=, capital=,
  max_lots=None, unit="percent")` sizes a target into whole contracts per actual contract,
  rounded toward zero; with `unit="lots"` the targets are the contracts (no
  capital, nothing rounded) and only `max_lots` is checked; it raises for anything
  but futures.
- `run_live(..., unit="percent")` and `run_bar` (from `LiveSpec.unit`) diff,
  message, and trade a lots table as lots. `deliver_signal` starts the base over
  when the ledger's base is in another unit: the whole target goes out and the
  message says the baseline was reset.
- `run_live(..., test=True)` is for checking the IM path outside trading
  hours: no trading-day or freshness check, the row at or before the date, the
  whole target in a message marked 测试 (`format_signal(..., test=True)`), and
  no ledger, run log, or alerts. `deliver_signal(..., test=True)` is the same
  delivery step.
- `deliver_signal(snapshot, ledger, write=..., urls=None, capital=None,
  multipliers=None, lot_size=100, notes=())` is the diff, sizing, push, and
  ledger step shared with `qs live-trade notify`; it raises `NoChannelsError`
  when `write` has no channels. `notes` are lines appended to the message and
  never change the signal id.
- `RunLog(strategy_id, data_root)` stores `data/live/<id>/runs.json`:
  `record(when, status, detail, signal_id, target=None, trade_date=None)`,
  `get(when)`, `is_done(when)`, `bars(trade_date)`, and
  `claim_alert(trade_date, kind)`, which returns `False` when that alert already
  went out. `when` is a date for a daily run and a bar end `datetime` for a
  minute run (keyed `2026-11-23T09:05:00`); the last 90 calendar days are kept.
  `DONE_STATUSES` are `sent`, `unchanged`, `already_sent`, `not_trading_day`,
  and `missed`.
- `run_job(job, date, final=...)` runs `python -m <module> --date ... --write`
  from the repository root, skips finished dates, and alerts once when the
  process exits with a code other than 0, 1, 3, or 4. The process prints UTF-8
  (`PYTHONIOENCODING=utf-8`) and its output is read as UTF-8 on every OS.
  `catch_up(config, now)` runs each job whose first time today has passed.
  `build_scheduler` returns a `BackgroundScheduler` with one coalesced cron job
  per run time and a six-hour misfire grace, so a run missed during sleep still
  happens once. `serve` runs it through `run_until_stopped`, whose thread
  sleeps one second at a time: on Windows Ctrl+C interrupts a sleep but not a
  `BlockingScheduler`'s wait for the next trigger.
- State files (`ledger.json`, `runs.json`, `feed.json`) are written by
  `ledger.write_json_atomic`: a temporary file, then
  `skills.store.files.replace_file`, which retries for about two seconds while
  Windows reports the target in use. A
  strategy id is one path segment that is valid on every OS (no trailing dot,
  no Windows device name such as `con` or `nul`).

## Minute-level runs

A minute-level workflow declares a spec and a weight function shared with the
backtest; `minute_main` hands both to `refresh_day` or `run_bar`:

```python
from skills.live_trade.spec import Instrument, LiveSpec
from skills.live_trade.workflow import minute_main

SPEC = LiveSpec(
    strategy_id="rb_ma_cross_5m",
    frequency="5m",
    instruments=(Instrument(symbol="RB_DOMINANT.SHF", asset="future"),),
    warmup_bars=48,
    adjust="none",
)

def target_weights(panel):           # (symbol, eob) panel -> eob x symbol weights
    ...

def main(argv=None) -> int:
    return minute_main(SPEC, target_weights, argv)
```

- `minute_main(spec, compute, argv=None)` builds a `MinuteFeed` on a
  `PandaDataClient` and runs one mode: `--refresh` (`refresh_day`; report
  `strategy_id`, `trade_date`, `status`, `detail`, `contracts`, `bars_today`, `rows`,
  `mismatches`, `alerts`), `--bar <end time>` (`run_bar`; report `strategy_id`, `bar`,
  `execution`, `status`, `detail`, the delivery's `signal_id`, `target`, `message`,
  `deliveries` when there is one, and `alerts`), or `--test` (`run_live(...,
  test=True)` on the stored bars; no `alerts`). `--now` overrides the clock; no mode
  exits 2. With `--account`, `run_bar` gets an `execute` that runs
  `execution.execute_targets` on a `PandaTrader` for that account, traced as
  `<strategy_id>-<bar %Y%m%dT%H%M>`; a missing client CLI exits with an error.
- `replay_mismatches(compute, data, window=None, last=50, tolerance=1e-9)` recomputes
  `compute` on the data a live run has at each of the last `last` rows of
  `compute(data)`: everything from the first row, or the last `window` bars
  (`LiveSpec.warmup_bars`). It returns the rows whose target differs, missing and zero
  weights counting as equal; `[]` means live runs reproduce the backtest's rows. `data`
  is a `(symbol, eob)` panel or an `eob`-indexed table.

- `LiveSpec(strategy_id, frequency, instruments, warmup_bars, adjust="post",
  bar_delay_seconds=None, deadline_seconds=None, spare_days=2,
  intraday_source="akshare", unit="percent")`. `unit="lots"` makes the
  target table whole lots (see `TargetSnapshot`). `Instrument` checks that the code matches its
  asset (`stock`, `fund`, `future`); `continuous` is true for codes such as
  `RB_DOMINANT.SHF`. One spec trades either futures or stocks and funds;
  `intraday_source="tqsdk"` (bars built from TqSdk ticks) needs futures.
  `delay_seconds` is `bar_delay_seconds` or the source's default
  (`DEFAULT_BAR_DELAY`: 40 for `akshare`, 3 for `tqsdk`). `deadline` defaults to
  one bar plus the delay (340 seconds for Sina's `5m`, 100 for its `1m`, 303 for
  TqSdk's `5m`) and must exceed the delay. `with_source(source)` is the same spec
  on another source, validated again; `minute_main` applies `--intraday-source`
  with it.
- `MinuteFeed(spec, client, data_root=None, akshare=None, tqsdk=None, pause=0.3)`
  (`tqsdk`: a function returning a logged-in TqSdk API, for tests):
  `refresh(trading_date, now=None)` reloads `ceil(warmup_bars / bars per day) +
  spare_days + 1` trading days from PandaData into
  `data/live/<id>/market/<frequency>/`, first comparing the intraday bars stored
  for those days (`RefreshReport.comparisons`, `BarComparison`), and writes
  `feed.json` (`FeedState`). `update(now)` appends today's finished bars of the
  spec's source (`fetch_intraday_bars` or `skills.ingest.tqsdk_bars.fetch_tq_bars`) of
  the scheduled bar ends and reports `latest`, `added`, and per-symbol `errors`
  (`UpdateReport`). `panel()` is the `(symbol, eob)` panel the weight function
  gets; `closes()` the signal closes; `raw_closes()` the unadjusted closes used
  for sizing. `state()` raises `FeedNotReady` before the first refresh.
- The store keeps `open`, `high`, `low`, `close` (adjusted as the spec says),
  `volume`, `open_interest`, `factor` (the multiplier applied; raw price is
  `close / factor`), `contract` (the actual contract), `trading_date`, and
  `source`. Futures night bars carry the next trading day's `trading_date`.
- Stock and fund factors are the daily post-adjusted close over the raw close of
  each day (`fetch_market_data` with `adjust="post"`, `get_fund_daily_post`).
  Today's factor is the last known one, or for a stock whose ex-date is today
  (`get_stock_dividend`) the published `ex_cum_factor` of `get_adj_factor`; if
  that is missing the stock is in `FeedState.halted`. A fund's ex-date is not
  caught before the open: PandaData publishes no fund dividends, and the
  exchange's previous close (what the 14:50 daily path checks) is only quoted
  once the session starts.
- `run_bar(spec, feed, compute, bar=, now=, write=False, capital=None,
  lot_size=100, data_root=None, urls=None, execute=None, max_lots=None)` returns a `RunOutcome`
  whose status is a delivery status or `not_ready`, `stale`, `source_error`,
  `missed`, `done`, or `error`. It computes on the stored bars up to `bar` (a late
  run may already hold the next bar), and the weights' last row must be the bar itself.
  With `write` it logs the bar and the target it computed in `RunLog`. With
  `write` and `execute(wanted, request_id)` (futures only) it also sizes the
  full target with `wanted_contracts(spec, snapshot, state, capital,
  max_lots=)` and trades it through `trade_target`, `closed` when `now` is
  outside the day's sessions; `RunOutcome.execution` and the run log's
  `execution` hold the result.
- `refresh_day(spec, feed, compute, now=, write=False, ...)` refreshes the
  trading day after `now` (`upcoming_trading_date`: today before 15:30, else
  the next trading day), recomputes the days it replaced, and returns
  `RefreshOutcome.mismatches`: per day, the bars whose logged target differs
  from `reconcile_signals(spec, weights, runs, day)`. With `write` it alerts
  `refresh_error`, `halted`, and `reconcile` once per trade date.
- `bar_ends(trading_date, frequency, sessions, calendar)` counts bars from each
  session's start; `parse_trading_hours` reads PandaData's `trading_hours`
  (bar-end ranges such as `21:01-23:00,09:01-10:15,...`). `has_night_session`
  is true after a plain weekday or a weekend only.
- `tick(job, now, write=True, data_root=None, runner=..., seen=None)` reads
  `feed.json`, logs bars past their deadline as `missed`, and runs one
  `--bar` process (timeout `bar_timeout(frequency)`: one bar, at most five
  minutes) for the oldest due bar that is not
  finished; `seen` stands in for the run log in previews. `run_job` for a
  minute job adds `--refresh` and never `--final`, and `build_scheduler` adds a
  `<id>@bars` tick every 10 seconds.

