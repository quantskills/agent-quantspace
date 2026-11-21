---
name: live-trade
description: Take a strategy's latest target weights live or to paper trading. Diff them against the last delivered target, size them into contracts or board lots, and push the rebalance signal to IM webhooks (WeCom, Feishu, Slack, Discord, DingTalk) with `uv run qs live-trade ...`; run strategy workflows on a cross-platform schedule that refreshes PandaData and alerts on failures. Futures go to the PandaAI live-trading client through its bundled `panda-live-trading` CLI.
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
- Check that IM channels and the PandaAI client CLI are set up: CLI version,
  client capabilities, and which accounts the CLI may use.
- Futures orders through the PandaAI client are not wired yet; this Skill only
  checks the client so far.

## Setup

```bash
uv sync --extra live
```

`live` installs Apprise, requests, and APScheduler 3.x; the scheduler runs the
same way on Windows, Linux, and macOS.

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

One strategy run by hand (preview; add `--write` to push and log it):

```bash
uv run python -m strategies.cross_sectional.workflows.live_asset_class_rotation --date 2026-11-20
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

A workflow loads its data and computes the full target table, then calls
`run_live` (see the Python API). One run of a trade date ends as one of:

| Status | Meaning | Exit |
|--------|---------|------|
| `not_trading_day` | PandaData's calendar says the date is closed; nothing is fetched. | 0 |
| `unchanged` / `sent` / `already_sent` | The day is finished; later runs skip it (`done`). | 0 |
| `preview` | No `--write`: nothing sent or logged. | 0 |
| `stale` | Weights do not reach the date yet; the next time retries. | 3 |
| `partial` / `failed` | Some channels failed; the next time retries only those. | 4 |
| `error` | Loading or computing raised. | 1 |

## Files

- `--weights` and `--prices` are date by symbol tables (`eob` index or column,
  one column per symbol), the same layout `qs backtest run` reads. The row at
  or before `--as-of` (default: the last row) is the signal.
- `--multipliers` is a JSON object such as `{"RB2601.SHF": 10}`.
- The ledger `data/live/<strategy-id>/ledger.json` keeps the last target that
  every channel received and the per-channel results of recent signals.
- `data/live/<strategy-id>/runs.json` keeps each trade date's run status,
  attempts, and the alerts already sent.
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
- A channel counts as delivered only when the IM accepts the message. WeCom,
  Feishu, and DingTalk answer HTTP 200 even when they reject one, so their error
  code in the response body must be 0.
- Webhook URLs are secrets. They are read only from the `QS_NOTIFY_*`
  variables (the environment or `.env`); output shows redacted labels such as
  `wecom-1a2b3c4d`.
- The PandaAI client keeps the trading account and its password. This Skill
  only calls the client's bundled CLI (`PANDA_LIVE_CLI` overrides its path); it
  never reads the client's files, database, or internal HTTP API.
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

## References

- [references/python-api.md](references/python-api.md): contracts, sizing,
  ledger, notification, and PandaAI CLI APIs. Read it when changing
  this Skill or writing strategy code.

## CLI command reference

<!-- BEGIN GENERATED: qs commands -->

Before using a command, run it with `--help` to see its options and defaults. `uv run qs schema <skill>.<command>` shows its input and output fields; add `--file-field FIELD` for the structure of an option that takes a JSON file.

| Command | What it does | Side effects |
|---|---|---|
| `uv run qs live-trade notify` | Diff the latest target weights against the last delivered target and push the rebalance signal to IM webhooks; previews unless --write. | network, writes-store, writes-output |
| `uv run qs live-trade doctor` | Check IM notification channels and the PandaAI client CLI (version, capabilities, accounts); --send-test pushes a test message. | read-only, network |
| `uv run qs live-trade serve` | Run live strategy workflows on a schedule (APScheduler), making up missed runs; --check only lists upcoming runs. | network, writes-store |

<!-- END GENERATED: qs commands -->
