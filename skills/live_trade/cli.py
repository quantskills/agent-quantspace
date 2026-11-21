"""qs live-trade commands: push rebalance signals to IM webhooks and check the live setup."""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from skills.cli.io import read_frame, read_json, write_json
from skills.cli.models import CLIError, CLIModel, CommandResult
from skills.cli.registry import Command

DATA_ROOT_HELP = "Data root holding live/<strategy-id>/ledger.json; otherwise QUANTSPACE_DATA_ROOT or repository data/."
NO_CHANNELS_HINT = (
    "Put each IM's webhook URL in its own .env variable: QS_NOTIFY_WECOM, QS_NOTIFY_FEISHU, "
    "QS_NOTIFY_DINGTALK, QS_NOTIFY_SLACK, QS_NOTIFY_DISCORD; separate several URLs of one IM "
    "with commas."
)


class NotifyInput(CLIModel):
    weights: Path = Field(
        description="Date by symbol target-weight table (Parquet/CSV with an eob index or column)."
    )
    strategy_id: str = Field(
        description="Strategy id; names the ledger folder data/live/<strategy-id>/."
    )
    as_of: str | None = Field(
        None, description="Use the last weights row at or before this time; default: the last row."
    )
    prices: Path | None = Field(
        None,
        description="Optional date by symbol reference-price table; its row at or before the signal time is used.",
    )
    capital: float | None = Field(
        None, gt=0, description="Optional capital; with --prices adds target units per symbol."
    )
    lot_size: int = Field(
        100, ge=1, description="Board lot for non-futures symbols; futures size in whole contracts."
    )
    multipliers: Path | None = Field(
        None,
        description="JSON object of contract multipliers by symbol; required for futures when --capital is set.",
    )
    write: bool = Field(
        False,
        description="Deliver to the configured IM webhooks and record the ledger; without it the command only previews.",
    )
    data_root: Path | None = Field(None, description=DATA_ROOT_HELP)
    output: Path | None = Field(None, description="Optional JSON file with the signal and results.")
    overwrite: bool = Field(False, description="Allow replacing an existing output file.")


class ChangeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(description="PandaData symbol, such as 510300.SH or RB2601.SHF.")
    previous: float = Field(description="Weight in the last delivered target.")
    target: float = Field(description="New target weight.")
    delta: float = Field(description="target - previous.")
    price: float | None = Field(description="Reference price, if supplied.")
    units: int | None = Field(description="Target units (contracts or shares), if sized.")


class DeliveryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: str = Field(description="Redacted channel label <platform>-<hash8>.")
    ok: bool = Field(description="Whether the channel accepted the message.")
    skipped: bool = Field(description="True when the channel already received this signal.")
    detail: str = Field(description="Failure detail with the webhook URL redacted.")


class NotifyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["preview", "unchanged", "sent", "partial", "failed", "already_sent"] = Field(
        description="preview without --write; unchanged when the target equals the last delivered one."
    )
    signal_id: str = Field(description="Deterministic id of (strategy, time, base, target).")
    strategy_id: str = Field(description="Strategy id.")
    as_of: str = Field(description="Signal time taken from the weights table.")
    changes: list[ChangeItem] = Field(description="Changed symbols, including exits to zero.")
    title: str = Field(description="Message title.")
    body: str = Field(description="Message body sent to every channel.")
    channels: list[str] = Field(description="Configured channels, redacted.")
    deliveries: list[DeliveryItem] = Field(description="Per-channel results of this run.")
    ledger: str = Field(description="Ledger file path.")


def _multipliers(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError("--multipliers must be a JSON object of symbol to number")
    values = {}
    for symbol, value in payload.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Multiplier for {symbol} must be a number")
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Multiplier for {symbol} must be positive")
        values[str(symbol)] = float(value)
    return values


def _notify(args: NotifyInput) -> CommandResult:
    from skills.live_trade import SignalLedger, TargetSnapshot
    from skills.live_trade.runner import NoChannelsError, deliver_signal

    weights = read_frame(args.weights)
    prices = read_frame(args.prices) if args.prices else None
    if args.capital is not None and prices is None:
        raise CLIError("INVALID_INPUT", "--capital needs --prices to size targets")
    snapshot = TargetSnapshot.from_frames(
        weights, args.strategy_id, as_of=args.as_of, prices=prices
    )
    ledger = SignalLedger(args.strategy_id, args.data_root)
    try:
        delivery = deliver_signal(
            snapshot,
            ledger,
            write=args.write,
            capital=args.capital,
            multipliers=_multipliers(args.multipliers),
            lot_size=args.lot_size,
        )
    except NoChannelsError as exc:
        raise CLIError("CONFIG_MISSING", str(exc), hint=NO_CHANNELS_HINT) from exc
    signal, sized, status = delivery.signal, delivery.sized, delivery.status
    title, body, channels = delivery.title, delivery.body, delivery.channels
    deliveries = [
        DeliveryItem(channel=item.channel, ok=item.ok, skipped=False, detail=item.detail)
        for item in delivery.results
    ] + [DeliveryItem(channel=name, ok=True, skipped=True, detail="") for name in delivery.skipped]
    warnings, exit_code = [], 0
    if status in ("partial", "failed"):
        exit_code = 4
        warnings.append("Some channels failed; rerun the same command to retry only those.")
    elif status == "preview" and not channels:
        warnings.append("No IM webhook is configured; --write would fail.")

    data = NotifyOutput(
        status=status,
        signal_id=signal.signal_id,
        strategy_id=signal.strategy_id,
        as_of=signal.as_of,
        changes=[
            ChangeItem(
                symbol=change.symbol,
                previous=change.previous,
                target=change.target,
                delta=change.delta,
                price=signal.prices.get(change.symbol),
                units=sized[change.symbol].units if sized else None,
            )
            for change in signal.changes
        ],
        title=title,
        body=body,
        channels=channels,
        deliveries=deliveries,
        ledger=str(ledger.path),
    )
    artifacts = []
    if args.output:
        artifacts.append(
            write_json(data, args.output, overwrite=args.overwrite, data_root=args.data_root)
        )
    return CommandResult(data=data, artifacts=artifacts, warnings=warnings, exit_code=exit_code)


class DoctorInput(CLIModel):
    send_test: bool = Field(
        False, description="Also send a short test message to every configured channel."
    )


class ChannelItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: str = Field(description="Redacted channel label <platform>-<hash8>.")
    platform: str = Field(description="Platform: wecom, feishu, dingtalk, slack, or discord.")
    variable: str = Field(description="Environment variable the URL came from.")
    recognized: bool | None = Field(
        description="Whether Apprise accepts the URL; null without Apprise."
    )


class AccountItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int = Field(description="Client account id, passed to the CLI as --account.")
    code: str = Field(description="Account code at the broker.")
    name: str = Field(description="Account name in the client.")
    broker_id: str = Field(description="CTP broker id; 9999 is SimNow.")
    company: str = Field(description="Futures company name.")
    simnow: bool = Field(description="SimNow account (broker 9999); only these may auto-execute.")
    cli_eligible: bool = Field(description="Whether the client lets the CLI use this account now.")
    reason: str = Field(description="Why the account is not CLI-eligible, if it is not.")


class PandaCliItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    found: bool = Field(description="Whether the PandaAI client CLI was located.")
    command: list[str] = Field(description="Command prefix used to run it.")
    version: str | None = Field(description="Reported CLI version.")
    error: str | None = Field(description="Why a CLI check failed, if one did.")
    problems: list[str] = Field(
        default_factory=list,
        description="Version or client capabilities this Skill needs but lacks.",
    )
    accounts: list[AccountItem] = Field(
        default_factory=list, description="Accounts from the client's accounts command."
    )


class DoctorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notify_ready: bool = Field(description="Apprise installed and every channel recognized.")
    apprise_version: str | None = Field(description="Installed Apprise version, if any.")
    channels: list[ChannelItem] = Field(description="Channels from the QS_NOTIFY_* variables.")
    test_deliveries: list[DeliveryItem] = Field(description="Results of --send-test.")
    panda_cli: PandaCliItem = Field(description="PandaAI client CLI discovery result.")


def _doctor(args: DoctorInput) -> CommandResult:
    from skills.live_trade import (
        NOTIFY_ENV,
        PandaCliError,
        capability_problems,
        channel_name,
        cli_version,
        discover_cli,
        list_accounts,
        load_notify_urls,
        normalize_webhook_url,
        platform_of,
        run_cli,
        send_notifications,
        version_problem,
    )

    warnings = []
    urls = load_notify_urls()
    try:
        import apprise
    except ImportError:
        apprise = None
        warnings.append("Apprise is not installed; run uv sync --extra live.")
    channels = [
        ChannelItem(
            channel=channel_name(url),
            platform=platform_of(url),
            variable=NOTIFY_ENV[platform_of(url)],
            recognized=bool(apprise.Apprise().add(normalize_webhook_url(url))) if apprise else None,
        )
        for url in urls
    ]
    if not urls:
        warnings.append("No IM webhook is configured. " + NO_CHANNELS_HINT)
    notify_ready = bool(apprise and channels and all(item.recognized for item in channels))

    tests = []
    if args.send_test:
        if not notify_ready:
            raise CLIError(
                "CONFIG_MISSING",
                "Notification channels are not ready; fix the doctor warnings first",
                hint=NO_CHANNELS_HINT,
            )
        tests = [
            DeliveryItem(channel=item.channel, ok=item.ok, skipped=False, detail=item.detail)
            for item in send_notifications(
                "QuantSpace 通知测试", "这是一条 QuantSpace live-trade 测试消息，无需处理。", urls
            )
        ]

    command = discover_cli()
    version, error, problems, accounts = None, None, [], []
    if command:
        try:
            version = cli_version(command)
            problem = version_problem(version)
            problems += [problem] if problem else []
            problems += capability_problems(run_cli(command, "capabilities") or {})
            accounts = list_accounts(command)
        except (subprocess.CalledProcessError, TimeoutError, OSError, PandaCliError) as exc:
            error = str(exc)
        warnings += [f"PandaAI client: {problem}." for problem in problems]
        if version and not error and not any(account.cli_eligible for account in accounts):
            reasons = "; ".join(
                f"{account.name} ({account.code}): {account.unavailable_reason}"
                for account in accounts
            )
            warnings.append(
                "No PandaAI account can be used through the CLI yet"
                + (f" ({reasons})" if reasons else "; add an account in the client")
                + "."
            )
    else:
        warnings.append(
            "PandaAI client CLI not found; install the PandaAI client or set PANDA_LIVE_CLI."
        )

    exit_code = 0
    if not notify_ready:
        exit_code = 1
    if any(not item.ok for item in tests):
        exit_code = 4
    data = DoctorOutput(
        notify_ready=notify_ready,
        apprise_version=getattr(apprise, "__version__", None),
        channels=channels,
        test_deliveries=tests,
        panda_cli=PandaCliItem(
            found=command is not None,
            command=command or [],
            version=version,
            error=error,
            problems=problems,
            accounts=[
                AccountItem(
                    account_id=account.account_id,
                    code=account.code,
                    name=account.name,
                    broker_id=account.broker_id,
                    company=account.company,
                    simnow=account.is_simnow,
                    cli_eligible=account.cli_eligible,
                    reason=account.unavailable_reason,
                )
                for account in accounts
            ],
        ),
    )
    return CommandResult(data=data, warnings=warnings, exit_code=exit_code)


class ServeInput(CLIModel):
    config: Path = Field(
        description="Schedule JSON: timezone and jobs (strategy_id, module, times, days, args)."
    )
    check: bool = Field(
        False, description="Validate the schedule and list upcoming runs, then exit."
    )
    write: bool = Field(
        False,
        description="Let scheduled runs push signals, alerts, and start/stop messages and log "
        "their results; without it every run only previews.",
    )
    data_root: Path | None = Field(None, description=DATA_ROOT_HELP)


class ServeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = Field(description="Time zone of the run times.")
    jobs: list[str] = Field(description="Strategy ids in the schedule.")
    next_runs: dict[str, list[str]] = Field(description="Upcoming run times per strategy.")
    stopped: bool = Field(description="True after a running scheduler was stopped.")


def _serve(args: ServeInput) -> CommandResult:
    import logging
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from skills.live_trade import load_notify_urls, send_notifications
    from skills.live_trade.scheduler import load_schedule, next_runs, serve

    try:
        config = load_schedule(args.config)
    except (OSError, ValueError) as exc:
        raise CLIError("INVALID_INPUT", f"Cannot use schedule {args.config}: {exc}") from exc
    upcoming = next_runs(config, datetime.now(ZoneInfo(config.timezone)))
    warnings = []
    urls = load_notify_urls()
    if not urls:
        warnings.append("No IM webhook is configured; runs and alerts will not reach anyone.")
    data = {"timezone": config.timezone, "jobs": [job.strategy_id for job in config.jobs]}
    if args.check:
        return CommandResult(
            data=ServeOutput(**data, next_runs=upcoming, stopped=False), warnings=warnings
        )

    # The qs transport logs at WARNING by default; a scheduler should say what it runs.
    logger = logging.getLogger("skills.live_trade")
    if logger.getEffectiveLevel() > logging.INFO:
        logger.setLevel(logging.INFO)
    if not logging.getLogger().handlers:
        logging.basicConfig(stream=sys.stderr, format="%(asctime)s %(levelname)s %(message)s")

    def announce(title: str, body: str) -> None:
        for item in send_notifications(title, body, urls) if urls else []:
            if item.ok:
                logger.info("announced %r to %s", title, item.channel)
            else:
                logger.warning("announce to %s failed: %s", item.channel, item.detail)

    if not args.write:
        warnings.append("Without --write every scheduled run only previews; nothing is sent.")
    try:
        serve(
            config,
            write=args.write,
            data_root=args.data_root,
            announce=announce if args.write else None,
        )
    except (KeyboardInterrupt, SystemExit):
        pass
    return CommandResult(data=ServeOutput(**data, next_runs={}, stopped=True), warnings=warnings)


COMMANDS = [
    Command(
        "live-trade.notify",
        NotifyInput,
        NotifyOutput,
        _notify,
        "Diff the latest target weights against the last delivered target and push the "
        "rebalance signal to IM webhooks; previews unless --write.",
        side_effects=("network", "writes-store", "writes-output"),
        priority="P0",
    ),
    Command(
        "live-trade.doctor",
        DoctorInput,
        DoctorOutput,
        _doctor,
        "Check IM notification channels and the PandaAI client CLI (version, capabilities, "
        "accounts); --send-test pushes a test message.",
        side_effects=("read-only", "network"),
        priority="P0",
    ),
    Command(
        "live-trade.serve",
        ServeInput,
        ServeOutput,
        _serve,
        "Run live strategy workflows on a schedule (APScheduler), making up missed runs; "
        "--check only lists upcoming runs.",
        side_effects=("network", "writes-store"),
        priority="P1",
    ),
]
