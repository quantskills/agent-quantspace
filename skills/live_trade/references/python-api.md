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
        multipliers={"RB2601.SHF": 10},
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
| `skills.live_trade.sizing` | `size_targets` and `SizingLimitError`: weights to contracts or board lots, with unit and notional caps that raise instead of clipping |
| `skills.live_trade.ledger` | `SignalLedger`: last fully delivered target and per-channel results under `data/live/<strategy_id>/ledger.json` |
| `skills.live_trade.notify` | `NOTIFY_ENV` per-IM variables (`QS_NOTIFY_WECOM`, `QS_NOTIFY_FEISHU`, `QS_NOTIFY_DINGTALK`, `QS_NOTIFY_SLACK`, `QS_NOTIFY_DISCORD`) with platform checks, IM URL normalization, redacted channel labels, message formatting, delivery (WeCom, Feishu, DingTalk posted directly and checked by error code; Slack, Discord via Apprise) |
| `skills.live_trade.runner` | `run_live`, `LiveInputs`, `RunOutcome`, `RunLog`, `deliver_signal`, `send_alert`: one scheduled run of a trade date (trading-day and freshness checks, delivery, run log, alerts) |
| `skills.live_trade.scheduler` | `ScheduleConfig`, `JobConfig`, `run_job`, `catch_up`, `build_scheduler`, `next_runs`, `serve`, `workflow_arguments`: APScheduler 3.x cron triggers that start workflow processes |
| `skills.live_trade.panda_cli` | The PandaAI client's bundled `panda-live-trading` CLI: `discover_cli`, `cli_version`, `run_cli`, `list_accounts` (`PandaAccount`), `capability_problems`, `version_problem`, `require_actual_contract`, `PandaCliError` |

## Contracts

- `TargetSnapshot.from_frames(weights, strategy_id, as_of=None, prices=None)`
  takes the weights row at or before `as_of`, treats missing weights as zero,
  and keeps only nonzero targets. Missing prices stay missing.
- `build_signal(snapshot, previous)` hashes strategy, time, base, and target
  into `signal_id`, so the same inputs always give the same id. `changes`
  includes exits to zero.
- `size_targets(weights, capital, prices, multipliers=..., lot_size=100,
  rounding="down", max_units=None, max_notional=None)` computes
  `weight * capital / (price * multiplier)`. Futures (PandaData suffixes `.SHF`,
  `.DCE`, `.CZC`, `.CFE`, `.INE`, `.GFE`) size in whole contracts and need a multiplier.
- `SignalLedger.record(signal, results, channels)` returns whether every
  channel has the signal; only then does the signal's target become the new base.
- `load_notify_urls(environ=None)` reads one variable per IM from `NOTIFY_ENV`
  (process environment, with `.env` filling unset ones); a variable may hold
  several comma-separated URLs, and a URL of another platform raises `ValueError`.
- `send_notifications(title, body, urls)` sends to each URL separately and
  returns one `DeliveryResult` per channel; failure details have the webhook
  URL redacted. WeCom, Feishu, and DingTalk reject messages with HTTP 200 and an
  error code in the body, so they are posted directly with `requests` and count
  as delivered only when that code is 0. Slack and Discord go through Apprise.
  Install both with `uv sync --extra live`.
- `discover_cli()` checks `PANDA_LIVE_CLI`, then the macOS client bundle
  `/Applications/PandaAI.app/Contents/Resources/cli/bin/panda-live-trading.mjs`
  (run with `node`), then `panda-live-trading` on `PATH`.
- `run_cli(command, *args)` returns the CLI's `data` and raises `PandaCliError`
  (with the CLI's error `code`) on `ok: false` or output that is not JSON. Every
  call sets `PANDA_LIVE_ACTOR=AI` and `PANDA_LIVE_ACTOR_ID=quantspace-live-trade`
  for the client's audit trail and turns off its update check.
- `list_accounts(command)` returns `PandaAccount` items; `is_simnow` means
  broker `9999` (`SIMNOW_BROKER_ID`), `cli_eligible` and `unavailable_reason`
  come from the client.
- `capability_problems(capabilities)` lists missing features this Skill needs
  (contract specs, GFD limit orders in batch plans); `version_problem(version)`
  checks the CLI is at least `0.1.11`.
- Symbols are PandaData codes everywhere (`510300.SH`, `RB2601.SHF`), the same
  strings the client CLI takes, so nothing is converted.
  `require_actual_contract("RB2601.SHF")` returns the code unchanged and refuses
  non-futures and dominant-continuous codes such as `RB_DOMINANT.SHF`, because
  orders and positions match actual contracts.

## Scheduled runs

A strategy workflow module (under `strategies/<domain>/workflows/live_*.py`)
supplies the data and the target table; `skills.live_trade` never imports it.

```python
from skills.live_trade.runner import LiveInputs, run_live
from skills.live_trade.scheduler import workflow_arguments

args = workflow_arguments()          # --date, --write, --final, --data-root, --capital, --lot-size

def load() -> LiveInputs:
    close = ...                      # download history up to args.date
    return LiveInputs(weights=target_weights(close), prices=raw_close)

outcome = run_live("my_strategy", load, trade_date=args.date, is_trading_day=True,
                   write=args.write, final=args.final, capital=args.capital)
raise SystemExit(outcome.exit_code)
```

- `run_live` returns `not_trading_day` without calling `load`, and `done`
  without calling it when `RunLog` already finished the date (`write` only).
  Weights whose last row is before the date are `stale`; after it, an `error`.
  The signal is the row of the date itself.
- `run_live(..., test=True)` is for checking the IM path outside trading
  hours: no trading-day or freshness check, the row at or before the date, the
  whole target in a message marked 测试 (`format_signal(..., test=True)`), and
  no ledger, run log, or alerts. `deliver_signal(..., test=True)` is the same
  delivery step.
- `deliver_signal(snapshot, ledger, write=..., urls=None, capital=None,
  multipliers=None, lot_size=100)` is the diff, sizing, push, and ledger step
  shared with `qs live-trade notify`; it raises `NoChannelsError` when `write`
  has no channels.
- `RunLog(strategy_id, data_root)` stores `data/live/<id>/runs.json`:
  `record(date, status, detail, signal_id)`, `is_done(date)`, and
  `claim_alert(date, kind)`, which returns `False` when that alert already went
  out. `DONE_STATUSES` are `sent`, `unchanged`, `already_sent`, and
  `not_trading_day`.
- `run_job(job, date, final=...)` runs `python -m <module> --date ... --write`
  from the repository root, skips finished dates, and alerts once when the
  process exits with a code other than 0, 1, 3, or 4. `catch_up(config, now)`
  runs each job whose first time today has passed. `build_scheduler` adds one
  coalesced cron job per run time with a six-hour misfire grace, so a run missed
  during sleep still happens once.

