---
name: live-trade
description: Take a strategy's latest target weights live or to paper trading. Diff them against the last delivered target, size percent targets into contracts or board lots (lots strategies give whole lots directly), and push the rebalance signal to IM webhooks (WeCom, Feishu, Slack, Discord, DingTalk) with `uv run qs live-trade ...`; run daily (signal and trade at 14:50, the 14:50 price as the close) or minute-level (1m-60m) strategy workflows on a cross-platform schedule that refreshes PandaData, takes today's prices during the session from AKShare (Sina) or, for futures, bars built from TqSdk ticks, reconciles them against PandaData the next day, and alerts on failures. Futures go to the PandaAI live-trading client through its bundled `panda-live-trading` CLI.
---

# Live Trade

Use the `uv run qs live-trade` commands below; signal tasks do not require
reading `skills/live_trade/` source. Each command prints one JSON envelope on
stdout (`ok`, `data`, `artifacts`, `warnings`, or `error` with a `hint`).
Exact options: `uv run qs live-trade <command> --help` or
`uv run qs schema live-trade.<command>`.

## When to use

- Push a strategy's latest rebalance signal to IM groups for manual execution.
- Run strategies unattended every trading day: download fresh PandaData bars,
  recompute targets, push only when the target changed, and alert on errors or
  data that never arrived (`serve`).
- Run a minute-level strategy (1m to 60m bars of futures, stocks or listed
  funds) during the session: one signal per bar, from today's bars on Sina
  through AKShare (or, for futures, bars built from TqSdk ticks), reconciled
  against PandaData's bars after the close.
- Check that IM channels and the PandaAI client CLI are set up: CLI version,
  client capabilities, and which accounts the CLI may use.
- Trade a minute-level futures strategy automatically on a SimNow account
  through the PandaAI client CLI: each bar sizes the target into whole
  contracts and brings the account there with one target-position plan.

## Setup

```bash
uv sync --extra live
uv sync --extra live --extra panda_data --extra akshare   # minute-level strategies
uv sync --extra tqsdk                                      # futures bars from TqSdk
```

`live` installs Apprise, requests, and APScheduler 3.x; the scheduler runs the
same way on Windows, Linux, and macOS. Minute-level strategies also need
PandaData (history, calendar, dominant contracts) and AKShare (today's bars;
Python 3.11.5 or later). Taking futures bars from TqSdk instead needs a Shinny
account in `.env` as `TQ_USERNAME` and `TQ_PASSWORD` (see "Today's bars" below).

On Windows (checked on Windows 11, 2026-11-24) the setup is the same; uv brings
Python 3.11 and the `tzdata` package that `Asia/Shanghai` needs there.

- The PandaAI client's CLI is found in the folder its installer registered
  (Settings > Apps), else `%LOCALAPPDATA%\Programs\PandaAI` or
  `%ProgramFiles%\PandaAI`: `PandaAI.exe` runs
  `resources\cli\bundled-launcher.mjs`, or `resources\cli\panda-live-trading.mjs`
  in clients without the launcher. To use another one, set `PANDA_LIVE_CLI` to
  a `.mjs` file (run with `node` from `PATH`) or to an npm-installed
  `panda-live-trading.cmd`. Start the client and log in first: with the client
  closed, every CLI call fails with `fetch failed` and a hint to open the client
  and log in; `doctor` lists it under `warnings`.
- `qs` and the workflows print UTF-8 JSON, also into a pipe. A console shows it
  as is; to capture it in PowerShell, first run
  `[Console]::OutputEncoding = [Text.Encoding]::UTF8`.
- Stop `serve` with Ctrl+C (see "Stopping `serve`" below). Closing the window
  or `taskkill /F` kills the running workflow too and skips the stop message.
  To start it at logon, use a Task Scheduler task that runs only while you are
  logged on, since the PandaAI client runs on your desktop.

Paste each IM bot's webhook URL into its own `.env` variable; leave unused ones
empty. One variable may hold several groups of the same IM, separated by commas:

```text
QS_NOTIFY_WECOM=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...
QS_NOTIFY_FEISHU=https://open.feishu.cn/open-apis/bot/v2/hook/...
QS_NOTIFY_DINGTALK=https://oapi.dingtalk.com/robot/send?access_token=...
QS_NOTIFY_SLACK=https://hooks.slack.com/services/...
QS_NOTIFY_DISCORD=https://discord.com/api/webhooks/...
```

A URL of another IM than its variable is refused before anything is sent. The
matching [Apprise URL](https://github.com/caronc/apprise/wiki) form also works,
for example `feishu://<token>` or `dingtalk://<secret>@<token>` for DingTalk
signing. Feishu bots need no security setting; if you add a custom keyword, use
`QuantSpace`, which every message title contains. Feishu signature verification
is not supported.

## Workflow

```bash
uv run qs live-trade doctor
uv run qs live-trade doctor --send-test
uv run qs live-trade notify --weights out/weights.parquet --strategy-id etf_rotation \
  --prices out/close.parquet --capital 1000000
uv run qs live-trade notify --weights out/weights.parquet --strategy-id etf_rotation \
  --prices out/close.parquet --capital 1000000 --write
uv run qs live-trade serve --config live_schedule.json --check
uv run qs live-trade serve --config live_schedule.json
uv run qs live-trade serve --config live_schedule.json --write
```

One daily strategy run by hand (preview; add `--write` to push and log it). The
examples: 18 ETFs, six stocks, and rebar's dominant contract (`--account` trades it
on a SimNow account):

```bash
uv run python -m strategies.cross_sectional.workflows.live_asset_class_rotation --date 2026-11-20
uv run python -m strategies.cross_sectional.workflows.live_stock_ma_gap_1d --capital 1000000
uv run python -m strategies.time_series.workflows.live_rb_ma_atr_1d --capital 100000
```

Test the IM path at any hour, weekends and nights included. `--test` sends the
latest full target as a message marked 测试 and leaves the ledger and run log
untouched, so the next real run is unaffected:

```bash
uv run python -m strategies.cross_sectional.workflows.live_asset_class_rotation --test
uv run python -m strategies.cross_sectional.workflows.live_asset_class_rotation --test --write --capital 100000
```

A minute-level strategy by hand: the pre-open refresh, then one bar (`--now`
replays a past moment of the current trading day):

```bash
uv run python -m strategies.time_series.workflows.live_rb_ma_cross_5m --refresh
uv run python -m strategies.time_series.workflows.live_rb_ma_cross_5m --bar 2026-11-23T09:05:00
uv run python -m strategies.time_series.workflows.live_rb_ma_cross_5m --bar 2026-11-20T21:05:00 --now 2026-11-20T21:05:25
```

## Scheduled runs

`serve` reads a schedule such as
[references/schedule.example.json](references/schedule.example.json): per
strategy, its workflow module (run as `python -m <module>`), the run times, the
weekdays (`mon-fri`), and extra workflow arguments. At each time it starts
`python -m <module> --date <today> --write` (`--final` at the last time of the
day); without `serve --write` the runs only preview and nothing is sent. On start it makes up a run that was missed today, and it pushes a message
when it starts and when it stops. It does not start itself after a reboot; use
your system's login items, systemd user service, or Task Scheduler for that.

Stopping `serve`: press Ctrl+C once. Every workflow process runs in its own
process group (Windows) or session (macOS, Linux), so Ctrl+C reaches only
`serve`, never a bar that is placing orders. `serve` then starts no new run,
lets the running one finish (at most its own timeout: one bar for a minute
strategy, 30 minutes for a daily run), and only then pushes its stop message;
with nothing running it stops within a second. Press Ctrl+C again while it
waits to kill the running process and the PandaAI CLI calls it started: the
run alerts `forced_stop` and the stop message names it, so check its orders and
positions in the client before starting `serve` again.

### Daily strategies trade at 14:50

A daily strategy (stocks, funds or futures) signals and trades at 14:50 of the
trading day, not after the close: the night session moves prices before the next
morning. The 14:50 price stands in for the day's close. `load_daily_bars`
(`skills.live_trade.daily`) takes PandaData's daily bars (open, high, low, close,
volume) up to the previous trading day and adds today's bar from the Sina 1-minute
bars of the trading day up to 14:50: the first open, the highest high, the lowest
low, the 14:50 close and the summed volume; prices times today's
backward-adjustment factor for stocks and funds, the dominant contract's bars for a
futures continuous symbol (the night session before belongs to the day). On
2026-11-20 the 1-minute bars of 510300.SH and 000001.SZ added up to PandaData's day
exactly; rebar's matched the high and close but Sina leaves out the night
session's opening auction and 15% of the volume. Today's factor is
yesterday's unless the exchange's previous close for today (Sina's quote) differs
from yesterday's close, which happens on an ex-date: then it grows by their ratio
(PandaData's `ex_cum_factor` when a stock's is already published). PandaData
publishes no fund dividends, so this is how an ETF's ex-date is caught; it matched
PandaData's factor within 1.3e-5 on all seven ex-dates of the rotation ETFs since
2023. Schedule the job at `["14:51", "14:53", "14:55"]`: until every symbol's 14:50
bar and today's previous close are there the run is `stale` and the next time
retries, and the last time alerts. Sina has no bar for a minute without trades
(510170.SH had 82 such minutes on 2026-11-23, 14:50 among them), so the close is the
last trade at or before 14:50 once a later bar is out or two minutes have passed
(five for futures). A stock or fund with no trade today keeps the previous close
with no volume, as PandaData's bar of such a day does, and the message lists it. The matching backtest trades
at the signal day's close (`trade_at="close", signal_lag=0`). With
`--capital --account` a futures daily job also trades its target, the same way
as a minute bar (below).

A workflow loads its data and computes the full target table, and `daily_main`
hands it to `run_live` (see the Python API). One run of a trade date ends as one of:

| Status | Meaning | Exit |
|--------|---------|------|
| `not_trading_day` | PandaData's calendar says the date is closed; nothing is fetched. | 0 |
| `unchanged` / `sent` / `already_sent` | The day is finished; later runs skip it (`done`). | 0 |
| `preview` | No `--write`: nothing sent or logged. | 0 |
| `stale` | Today's 14:50 bars, or weights for the date, are not there yet; the next time retries. | 3 |
| `partial` / `failed` | Some channels failed; the next time retries only those. | 4 |
| `error` | Loading or computing raised. | 1 |
| `test_sent` / `test_partial` / `test_failed` | `--test --write`: the marked test message reached all, some, or no channels. | 0 / 4 / 4 |

## Today's bars: Sina or TqSdk

During the session today's bars come from one of two sources, Sina by default:

| `intraday_source` | What | Covers | Bar used after its end |
|---|---|---|---|
| `akshare` (default) | Sina's bars through AKShare | stocks, funds, futures | 40 s (`bar_delay_seconds`) |
| `tqsdk` | bars built from TqSdk's ticks | futures only | 3 s |

Choose it per job with `--intraday-source tqsdk` in the job's `args` (refresh
and bar runs get the same args), or in the workflow: `LiveSpec(...,
intraday_source="tqsdk")` for a minute strategy, `load_daily_bars(...,
source="tqsdk")` for a daily one. The flag wins over the workflow; without
either, Sina. Stocks and funds always come from Sina, so a daily strategy that
mixes them with futures takes only its futures from TqSdk, and a minute strategy
of stocks or funds refuses `tqsdk`.

Why TqSdk: measured on RB2701 on 2026-11-23 and 11-24, Sina's 5-minute bars first
appeared 173 seconds after their end in the median and 323 at most, and kept
changing for up to 813 seconds; three bars of 11-24 (11:00, 11:05, 11:30) missed
their deadline. A bar built from TqSdk's ticks is final as soon as the next tick
arrives, and one fetch (log in, ticks, log out) takes about 4 seconds, up to 12
on a cold start. The ticks are cut with PandaData's boundaries: the 1-minute bar
ending at E holds the ticks from E - 1 minute up to but not including E, and a
trading day's first bar also holds the opening auction, with volume counted from
zero. Such bars matched PandaData's close and volume on all 74 minutes of 11-24's
13:47–15:00 and 72 checked live that evening. TqSdk's own K lines put the tick
stamped exactly E:00.000 in the earlier bar and matched only 47 of those 74 closes,
so they fill only the minutes before the ticks TqSdk keeps (8964 ticks, about 75
minutes of rebar); such bars have `source` `tqsdk_kline`, the others
`tqsdk_tick`. A bar with no tick after its end (a session's last bar, a quiet
market) counts as finished 3 seconds after its end by the local clock.

## Minute-level strategies

A minute-level job has `"frequency": "5m"` (or `1m`, `15m`, `30m`, `60m`) in
the schedule; its workflow declares a `LiveSpec` (instruments, bar interval,
warm-up bars, price adjustment). Each trading day runs in two parts:

1. **Refresh** at the job's `times`: `python -m <module> --refresh --write`.
   Futures refresh after 17:55 (PandaData publishes the day's futures minute
   bars at 16:41-17:01 and the next day's dominant contracts at 17:35-17:55),
   for example `18:00` with `20:00` as a retry; stocks and funds before the
   open, for example `08:30`. It reloads the warm-up window from PandaData,
   maps continuous contracts such as `RB_DOMINANT.SHF` to the dominant contract
   of the next trading day, takes futures sessions and multipliers from
   `get_future_detail`, and writes the day's bar end times. `serve` also runs it
   once when it starts.
2. **Bars** during the session: every 10 seconds `serve` starts
   `python -m <module> --bar <end time> --write` for the oldest bar that is due,
   `bar_delay_seconds` (default 40 for Sina, 3 for TqSdk) after the bar ends and until
   `deadline_seconds` (default one bar plus the delay, when the next bar becomes
   due). The delay is there because Sina keeps revising a bar for 10–30 seconds
   after it closes (up to 80 seconds for the first bars after the open, measured
   2026-11-23); what slips through is caught by the next refresh's
   reconciliation. A `--bar` process may run one bar at most (five minutes for
   bars of five minutes or longer). The run fetches today's finished bars
   from the intraday source, recomputes the whole target table on the stored
   window, and pushes the bar's row if it changed.

The next refresh compares the intraday bars of the finished day with
PandaData's, recomputes that day's bars, and alerts `reconcile` for every bar
whose target would have been different.

| Bar status | Meaning | Exit |
|------------|---------|------|
| `sent` / `unchanged` / `already_sent` | The bar is finished. | 0 |
| `preview` | No `--write`: nothing sent or logged. | 0 |
| `stale` | The intraday source has no bar at that time yet; the next tick retries. | 3 |
| `source_error` | The intraday source failed for a symbol without that bar; retried. | 3 |
| `not_ready` | No refresh for the trading day yet. | 3 |
| `missed` | Past the deadline; skipped. | 0 |
| `partial` / `failed` | Some channels failed; the next tick retries only those. | 4 |
| `error` | Fetching or computing raised, or the time is not a bar end. | 1 |

### Automatic orders (SimNow only)

Add `--capital <amount> --account <PandaAI account code>` to a futures job's
`args`, minute or daily (`--write` is added by `serve`), and `--max-lots <N>` to
cap the contracts any actual contract may target. Check the account first:

```bash
uv run qs live-trade doctor --account <code> --strategy-id rb_ma_cross_5m
```

`auto_trade.ready` says whether a bar would place orders now, and `reasons`
why not (not SimNow, CLI mode off, running asset units, counter not ready, CLI
too old, stop file). After each bar's (or day's) signal, the run turns the full target
into whole contracts of the actual contract (`RB_DOMINANT.SHF` maps to the day's
dominant contract) and calls `execute_targets`. A percent weight's contracts are the
ones held since its weight last changed (see "Target units": a price crossing a
rounding edge never trades); they are sized on the bar the weight changes even when
that bar places no order (`closed`, `stopped`), and the message's `目标 N 手` is the
same number. The contracts belong to the continuous symbol, so a roll moves them to
the new month unchanged; partial fills and manual trades are brought back to them by
the next bar (to take over by hand, use the stop file). A lots strategy's targets are
the contracts already: they go to the actual contract as they are, and `--capital` is
not needed:

1. It re-reads the account and trades only a SimNow account (broker `9999`) with
   CLI mode on, no running asset unit, and the counter connected and ready;
   anything else is `blocked`. A real account is never traded automatically.
   SimNow drops the counter now and then and the client does not reconnect by
   itself (2026-11-23: `FAILED` from 19:48 until reconnected by hand at 21:24),
   so a disconnected counter gets one `connect` and up to 20 seconds to be ready
   (it took about a second); one still connecting or syncing is only waited for.
   If it is not ready by then, the bar is `blocked` and the next bar tries again.
2. An order the client marks `UNKNOWN` stops trading (`unknown`) until you check
   it in the client. Working orders of the same products left from an earlier
   bar are cancelled first; if a cancel does not finish within 30 seconds, the
   bar places nothing (`pending_cancel`).
3. One `target-position` plan sets each wanted contract (and every other month
   of the same products still held, to 0); the client prices its orders at the
   best opposite quote, good for the day, and handles closing today's or
   yesterday's position and reversing. The client submits a plan's legs one at
   a time in target order, so closes come first (an old month before the new
   one, a reversal closes before it opens), and `plan execute --yes` is called
   on the same frozen plan again each time the earlier legs have filled. All of
   it is followed for 30 seconds (a reversal took 13.9 seconds on Windows, where
   each CLI call takes about 3); a leg that has not filled holds back the rest.

| Execution status | Meaning |
|------------------|---------|
| `in_position` | The account already holds the target. |
| `filled` | Orders filled and the account holds the target. |
| `working` | Orders still open or legs not yet sent; the next bar cancels them and re-targets. |
| `rejected` | An order was rejected or cancelled by the counter. |
| `pending_cancel` / `blocked` / `unknown` / `error` | Nothing new was sent; see the detail. |
| `stopped` | The stop file exists; no order was placed. |
| `over_limit` | The target exceeds `--max-lots`; no order was placed. |
| `closed` | The run is outside the trading session; no order was placed and nothing is alerted. |

A minute bar orders only while the market trades: a session's last bar (10:15,
11:30, 15:00 and 23:00 for rebar) runs after its session ends, when the client
refuses plans for lack of a live quote, so it signals but is `closed`; the next
session's first bar re-targets from the account's position. A daily futures run
orders only from 14:50 to 15:00 of its trade date (`--now` for a replay); a run
made up later, such as by `serve` started after the close, signals and is
`closed`.

Emergency stop: create `data/live/<strategy-id>/STOP` (any content) and every
later bar still signals but places no orders, alerting `execution_stopped`
once per trade date; delete the file to resume. Orders already working stay
with the counter; cancel them in the client if needed.

The result is logged with the bar in `runs.json` (`execution`). Every bar that
placed orders pushes a `trade` message with the fills and the position after;
each other status except `in_position`, `filled`, `working`, and `closed` alerts
once per trade date as `execution_<status>`, and a counter that had to be
reconnected first alerts `execution_reconnected` with the client's reason. The
bar's own status stays the delivery status, so a finished bar never trades
twice, and a later bar always re-targets from the account's actual position.
Measured on SimNow on 2026-11-23: one call takes 8–12 seconds with one order and
15–17 seconds for a reversal or a roll (two orders).

## From a backtest to a live workflow

A live workflow is one module under `strategies/<domain>/workflows/live_<name>.py`
with the strategy id (daily) or a `LiveSpec` (minute), a data loader (daily), and the
`target_weights` function the backtest calls; `main` is one line,
`daily_main(STRATEGY_ID, load_inputs, argv)` or `minute_main(SPEC, target_weights, argv)`
from `skills.live_trade.workflow`, which handles the arguments, modes, JSON report,
exit codes, and `--account`. Before writing one, read
[references/backtest-to-live.md](references/backtest-to-live.md): which strategies can
go live, how the backtest's `trade_at`, `signal_lag`, adjustment, and rounding map to
live timing, how to test that the live target is the backtest's row
(`replay_mismatches`), and how to schedule it.

## Target units: percent or lots

A strategy declares the unit of its target table once and the backtest uses the same
value (`VectorBacktester(unit=...)`, see the backtest Skill):

- `percent` (default): shares of capital, 1.0 is 100%. Units come from
  `--capital`: `weight x capital / (unadjusted price x units per lot)`, rounded toward
  zero to whole lots (a futures contract, or `--lot-size` shares, 100 by default, of
  a stock or fund). A `--write` run sizes a weight only when it changes (by more than
  `1e-6` from the last run), when the symbol is new, or when `--capital` or
  `--lot-size` changes, and keeps the units otherwise, whatever the price does
  (`data/live/<strategy-id>/sized_lots.json`, see Files). Messages (`目标 N 股`,
  `目标 N 手`) and futures orders use those units, which are what the backtest's
  `percent_to_lots` gives bar by bar. Previews and `--test` size at their own prices
  and keep nothing; if the record cannot be used, the message is sized at today's
  prices and says so.
- `lots`: whole lots, a futures contract or 100 shares (`SHARES_PER_LOT`) of a stock
  or fund. Declare it with `LiveSpec(unit="lots")` (minute) or
  `daily_main(STRATEGY_ID, load_inputs, argv, unit="lots")` (daily), and
  `notify --unit lots` for a table file. Fractions, and negative stocks or funds,
  make the run an `error` instead of being rounded.

In lots mode the signal compares lots with the last delivered lots; the message reads
`RB_DOMINANT.SHF：目标 3 手（原 2 手），参考价 2999，名义 89970` (stocks and funds add
the shares: `目标 30 手（3000 股，原 0 手）`), and with `--capital` the share of capital
(`，折合 89.97%`). Futures orders take the target lots per actual contract, capped by
`--max-lots`; stocks and funds still only push signals. The ledger keeps the unit of
its base: when a strategy changes unit, the base starts over, the whole target goes
out once, and the message says the baseline was reset. Ledgers without a unit are
percent, and percent signal ids are what they always were.

## Files

- `--weights` and `--prices` are date by symbol tables (`eob` index or column,
  one column per symbol), the same layout `qs backtest run` reads. The row at
  or before `--as-of` (default: the last row) is the signal.
- `--multipliers` is a JSON object such as `{"RB2701.SHF": 10}`.
- The ledger `data/live/<strategy-id>/ledger.json` keeps the last target that
  every channel received and the per-channel results of recent signals.
- `data/live/<strategy-id>/runs.json` keeps each trade date's run status,
  attempts, and the alerts already sent; a minute strategy logs each bar under
  its end time with the target it computed and its trade date.
- `data/live/<strategy-id>/sized_lots.json` (percent strategies run with
  `--write` and `--capital`, or with automatic orders) keeps, per symbol (continuous
  for futures), the last weight, the units it was sized to (`lots`, and `units`:
  contracts or shares), and the price and run of that sizing, with the `--capital`
  and `--lot-size` used. Delete it to size everything at the next run's prices; a
  lots run removes it.
- A minute strategy keeps `data/live/<strategy-id>/feed.json` (the trading day
  the last refresh prepared: contracts, factors, sessions, bar end times,
  halted symbols), its bars in
  `data/live/<strategy-id>/market/<frequency>/<symbol>.parquet` with a `source`
  column (`pandadata`, `akshare_sina`, `tqsdk_tick` or `tqsdk_kline`), and the
  reconciliation of each day in
  `data/live/<strategy-id>/reconcile/<date>.bars.json` and `.signals.json`.
- A workflow keeps its own downloaded bars under
  `data/live/<strategy-id>/market/` and never writes the research store
  `data/market/`.

## Rules

- `notify` only previews unless `--write` is given; previews never touch the
  network or the ledger.
- A signal is the change from the last fully delivered target. A rerun with the
  same target sends nothing (`unchanged`). After a partial failure, a rerun
  sends the same signal only to the channels that failed.
- Sizing never guesses: futures need a multiplier, every changed symbol needs a
  price, and units round toward zero to whole contracts or `--lot-size` shares.
  Lots targets are never rounded or resized. Live percent runs size a weight
  once, when it (or `--capital`, `--lot-size`) changes, and hold the units until
  then, for every asset.
- A channel counts as delivered only when the IM accepts the message. WeCom,
  Feishu, and DingTalk answer HTTP 200 even when they reject one, so their error
  code in the response body must be 0.
- Webhook URLs are secrets. They are read only from the `QS_NOTIFY_*`
  variables (the environment or `.env`); output shows redacted labels such as
  `wecom-1a2b3c4d`.
- The PandaAI client keeps the trading account and its password. This Skill
  only calls the client's bundled CLI (its launcher on the client's own runtime;
  `PANDA_LIVE_CLI` overrides the path; on Windows the install folder comes from
  the installer's uninstall entry); it never reads the client's files,
  database, or internal HTTP API, and leaves the client's update reminders on.
- An account is usable only after you turn on its CLI mode in the client and
  stop its running asset units; `doctor` lists each account's state and reason.
- Only SimNow accounts (broker `9999`) may ever execute without a human
  confirming; a real account always needs confirmation. This is fixed in code.
- Scheduled runs are silent when nothing changed. Errors alert at once; stale
  data and incomplete delivery alert at the last run time of the day. Each kind
  alerts once per trade date; a workflow process that crashes is alerted by
  `serve`.
- A live workflow recomputes the whole history each run from a fixed start date
  and uses the same weight function as the backtest, so the day's target equals
  the backtest's row for that day. Rebalance counts start at that fixed date.
- Minute strategies: a bar is used only once it has finished; Sina's forming
  bar and its placeholder for the next session are dropped. Each kind of bar
  problem (`not_ready`, `source_error`, `missed`, `error`, delivery failures)
  alerts once per trade date.
- A futures night session belongs to the next trading day, and there is none
  before a trading day that follows a holiday. A session whose length is not a
  whole number of bars is refused (rebar's 09:00-10:15 rules out 30m and 60m).
- One minute strategy trades either futures or stocks and funds. Futures are
  never adjusted. Stock and fund signals use backward-adjusted prices by
  default (`adjust="post"`): history is PandaData's raw minute bars times each
  day's post/raw daily close ratio, and today's Sina bars are raw prices times
  the factor known before the open. A stock whose ex-date is today without a
  published factor is halted for the day: its last delivered weight is kept,
  the message says so, and `halted` alerts. Sizing always uses raw prices.
- Sina is a free source without a service guarantee; the `reconcile` alert is
  how differences from PandaData show up. Keep the live store separate from the
  research store: minute strategies never write `data/market/`.
- Sina's futures bars are late now and then and count volume differently. On
  2026-11-23 most rebar 5-minute bars were there 46–54 seconds after their end,
  but the 14:10 bar 2.5 minutes and the 15:00 bar 4.5 minutes after; the day's
  closes matched PandaData's on all but 2 of 69 bars (at most 1 yuan apart), while
  its volume added up to 61% of PandaData's. A futures rule on volume or open
  interest gets different inputs live than in the backtest; check it with
  `replay_mismatches` before relying on it.

## References

- [references/backtest-to-live.md](references/backtest-to-live.md): turning a
  backtested strategy into a live workflow, step by step, with the checks.
- [references/python-api.md](references/python-api.md): contracts, sizing,
  ledger, notification, PandaAI CLI, scheduled and minute-level run APIs. Read
  it when changing this Skill or writing strategy code.

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs live-trade notify` | Diff the latest target weights against the last delivered target and push the rebalance signal to IM webhooks; previews unless --write. | network, writes-store, writes-output |
| `uv run qs live-trade doctor` | Check IM notification channels and the PandaAI client CLI (version, capabilities, accounts); --account reports whether automatic orders can run on that account now; --send-test pushes a test message. | read-only, network |
| `uv run qs live-trade serve` | Run live strategy workflows on a schedule (APScheduler), making up missed runs; --check only lists upcoming runs. | network, writes-store |

<!-- END GENERATED: qs commands -->
