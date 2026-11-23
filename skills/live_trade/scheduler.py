"""Cross-platform scheduler for live runs, built on APScheduler 3.x.

The scheduler only decides when to run. Each run is a separate ``python -m <module>`` process
of a strategy workflow that calls ``run_live``; the run log, not the scheduler, decides whether
a trade date is finished. A run that was missed while the process was stopped or the computer
slept is made up once when the process starts or wakes, and finished days are skipped.

A minute-level job (``frequency`` such as ``5m``) runs ``--refresh`` at its ``times`` (the
pre-open reload) and, every few seconds, starts one ``--bar <end time>`` process for the
oldest bar that is ready and not finished. The bars of the day come from the feed state the
refresh wrote; a bar past its deadline is logged as ``missed`` and alerted once a day.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .clock import INTRADAY_MINUTES, due_bars
from .feeds import read_feed_state
from .ledger import validate_strategy_id
from .runner import DONE_STATUSES, RunLog, send_alert

LOGGER = logging.getLogger("skills.live_trade.scheduler")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEZONE = "Asia/Shanghai"
RUN_TIMEOUT_SECONDS = 1800
# A trigger missed by up to this long (sleep, busy machine) still runs once when noticed.
MISFIRE_GRACE_SECONDS = 6 * 3600
# Exit codes a workflow returns through run_live; anything else means it crashed.
KNOWN_EXIT_CODES = frozenset({0, 1, 3, 4})
# How often a minute-level job looks for a ready bar.
TICK_SECONDS = 10
# A --bar process may run at most this long, and never longer than one bar.
BAR_TIMEOUT_SECONDS = 300
_MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")
_TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


class JobConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy_id: str = Field(description="Strategy id; must match the workflow's ledger folder.")
    module: str = Field(description="Workflow module run as `python -m <module>`.")
    times: list[str] = Field(
        min_length=1, description="HH:MM run times; later times retry if data was not ready."
    )
    days: str = Field(
        "mon-fri", description="APScheduler day_of_week; holidays are skipped by the workflow."
    )
    args: list[str] = Field(default_factory=list, description="Extra workflow arguments.")
    frequency: Literal["1d", "1m", "5m", "15m", "30m", "60m"] = Field(
        "1d",
        description="1d runs the workflow at each time; a minute interval runs --refresh at "
        "each time and one --bar process per ready bar.",
    )

    @property
    def intraday(self) -> bool:
        return self.frequency != "1d"

    @field_validator("strategy_id")
    @classmethod
    def _strategy(cls, value: str) -> str:
        return validate_strategy_id(value)

    @field_validator("module")
    @classmethod
    def _module(cls, value: str) -> str:
        if not _MODULE.fullmatch(value):
            raise ValueError(f"{value!r} is not a dotted Python module name")
        return value

    @field_validator("times")
    @classmethod
    def _times(cls, values: list[str]) -> list[str]:
        bad = [value for value in values if not _TIME.fullmatch(value)]
        if bad:
            raise ValueError(f"times must be HH:MM: {bad}")
        return sorted(set(values))

    @property
    def run_times(self) -> list[time]:
        return [time(int(text[:2]), int(text[3:])) for text in self.times]


class ScheduleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = Field(DEFAULT_TIMEZONE, description="IANA time zone of the run times.")
    jobs: list[JobConfig] = Field(min_length=1, description="One entry per strategy.")

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"unknown time zone {value!r}") from exc
        return value

    @field_validator("jobs")
    @classmethod
    def _unique(cls, jobs: list[JobConfig]) -> list[JobConfig]:
        ids = [job.strategy_id for job in jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("each strategy_id may appear in only one job")
        return jobs


def _day_matches(days: str, day: date, zone: ZoneInfo) -> bool:
    """Whether ``day`` falls in an APScheduler ``day_of_week`` expression such as ``mon-fri``."""
    from apscheduler.triggers.cron import CronTrigger

    midnight = datetime(day.year, day.month, day.day, tzinfo=zone)
    trigger = CronTrigger(day_of_week=days, hour=0, minute=0, timezone=zone)
    fire = trigger.get_next_fire_time(None, midnight)
    return fire is not None and fire.date() == day


@dataclass(frozen=True)
class Attempt:
    strategy_id: str
    trade_date: str
    final: bool
    status: str
    exit_code: int | None = None
    detail: str = ""


def run_job(
    job: JobConfig,
    trade_date: date,
    *,
    final: bool,
    write: bool = True,
    data_root: str | Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Attempt:
    """Run one workflow process for ``trade_date`` unless the day is already finished.

    Without ``write`` the workflow only previews, and a crash is logged but not alerted.
    """
    runs = RunLog(job.strategy_id, data_root)
    if not job.intraday and runs.is_done(trade_date):
        previous = (runs.get(trade_date) or {}).get("status", "")
        return Attempt(job.strategy_id, trade_date.isoformat(), final, "skipped", detail=previous)
    command = [sys.executable, "-m", job.module, "--date", trade_date.isoformat()]
    command += ["--refresh"] if job.intraday else []
    command += ["--write"] if write else []
    command += ["--final"] if final and not job.intraday else []
    command += ["--data-root", str(data_root)] if data_root else []
    command += job.args
    LOGGER.info("run %s for %s (final=%s)", job.strategy_id, trade_date, final)
    try:
        completed = runner(
            command,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECONDS,
        )
        code, tail = completed.returncode, (completed.stderr or "").strip()[-500:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        code, tail = None, f"{type(exc).__name__}: {exc}"
    if code in KNOWN_EXIT_CODES:
        return Attempt(job.strategy_id, trade_date.isoformat(), final, "ran", code)
    # The workflow died before run_live could log or alert; do both here, once a day.
    LOGGER.error("%s crashed (exit %s): %s", job.strategy_id, code, tail)
    if write and runs.claim_alert(trade_date, "crash"):
        send_alert(
            job.strategy_id,
            trade_date,
            "crash",
            f"策略进程异常退出（退出码 {code}），今天的信号没有生成。\n{tail[-300:]}",
        )
    return Attempt(job.strategy_id, trade_date.isoformat(), final, "crashed", code, tail)


def bar_timeout(frequency: str) -> int:
    """Seconds a ``--bar`` process may run: one bar, at most :data:`BAR_TIMEOUT_SECONDS`."""
    return min(BAR_TIMEOUT_SECONDS, INTRADAY_MINUTES[frequency] * 60)


def tick(
    job: JobConfig,
    now: datetime,
    *,
    write: bool = True,
    data_root: str | Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    seen: set[str] | None = None,
) -> list[Attempt]:
    """Handle the ready bars of a minute-level job at ``now`` (naive Shanghai time).

    Bars past their deadline are logged as ``missed`` (alerted once a day); then one
    process runs for the oldest ready bar that is not finished. Nothing happens until a
    refresh has written the day's bars. ``seen`` remembers bars this process already
    finished or gave up, which is all a preview (no ``write``) has instead of the run log.
    """
    seen = set() if seen is None else seen
    state = read_feed_state(job.strategy_id, data_root)
    if state is None:
        return []
    runs = RunLog(job.strategy_id, data_root)
    attempts = []
    schedule = [(state.day, eob) for eob in state.schedule]
    ready = due_bars(
        now, schedule, delay_seconds=state.delay_seconds, deadline_seconds=state.deadline_seconds
    )
    for bar in ready:
        label = bar.eob.isoformat()
        entry = runs.get(bar.eob) or {}
        if label in seen or entry.get("status") in DONE_STATUSES:
            continue
        if bar.missed(now):
            seen.add(label)
            if write:
                runs.record(
                    bar.eob,
                    "missed",
                    "调度没有在截止时刻前处理这根 K 线",
                    trade_date=bar.trading_date,
                )
                if runs.claim_alert(bar.trading_date, "missed"):
                    send_alert(
                        job.strategy_id,
                        bar.trading_date,
                        "missed",
                        f"K 线：{label}\n到截止时刻仍没有处理这根 K 线，已跳过。",
                    )
            attempts.append(Attempt(job.strategy_id, label, True, "missed"))
            continue
        command = [sys.executable, "-m", job.module, "--bar", label]
        command += ["--write"] if write else []
        command += ["--data-root", str(data_root)] if data_root else []
        command += job.args
        try:
            completed = runner(
                command,
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                timeout=bar_timeout(state.frequency),
            )
            code, tail = completed.returncode, (completed.stderr or "").strip()[-500:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, tail = None, f"{type(exc).__name__}: {exc}"
        if code in KNOWN_EXIT_CODES:
            if code == 0:
                seen.add(label)
            attempts.append(Attempt(job.strategy_id, label, False, "ran", code))
        else:
            LOGGER.error("%s %s crashed (exit %s): %s", job.strategy_id, label, code, tail)
            if write and runs.claim_alert(bar.trading_date, "crash"):
                send_alert(
                    job.strategy_id,
                    bar.trading_date,
                    "crash",
                    f"K 线 {label} 的策略进程异常退出（退出码 {code}）。\n{tail[-300:]}",
                )
            attempts.append(Attempt(job.strategy_id, label, False, "crashed", code, tail))
        break
    return attempts


def catch_up(
    config: ScheduleConfig,
    now: datetime,
    *,
    write: bool = True,
    data_root: str | Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[Attempt]:
    """Run each job once whose first time today has passed and whose day is not finished."""
    attempts, zone = [], ZoneInfo(config.timezone)
    now = now.astimezone(zone) if now.tzinfo else now.replace(tzinfo=zone)
    for job in config.jobs:
        today = now.date()
        if job.intraday:
            # The refresh is cheap and idempotent; run it so the next bars can be handled.
            attempts.append(
                run_job(job, today, final=False, write=write, data_root=data_root, runner=runner)
            )
            continue
        if not _day_matches(job.days, today, zone) or now.time() < job.run_times[0]:
            continue
        final = now.time() >= job.run_times[-1]
        attempts.append(
            run_job(job, today, final=final, write=write, data_root=data_root, runner=runner)
        )
    return attempts


def build_scheduler(
    config: ScheduleConfig,
    *,
    write: bool = True,
    data_root: str | Path | None = None,
    scheduler_class=None,
):
    """An APScheduler scheduler with one cron trigger per job and run time."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    zone = ZoneInfo(config.timezone)
    scheduler = (scheduler_class or BlockingScheduler)(timezone=zone)

    def fire(job: JobConfig, final: bool) -> None:
        attempt = run_job(
            job, datetime.now(zone).date(), final=final, write=write, data_root=data_root
        )
        LOGGER.info("%s", attempt)

    seen: dict[str, set[str]] = {}

    def fire_tick(job: JobConfig) -> None:
        for attempt in tick(
            job,
            datetime.now(zone).replace(tzinfo=None),
            write=write,
            data_root=data_root,
            seen=seen.setdefault(job.strategy_id, set()),
        ):
            LOGGER.info("%s", attempt)

    for job in config.jobs:
        if job.intraday:
            scheduler.add_job(
                fire_tick,
                CronTrigger(second=f"*/{TICK_SECONDS}", timezone=zone),
                args=(job,),
                id=f"{job.strategy_id}@bars",
                misfire_grace_time=TICK_SECONDS,
                coalesce=True,
                max_instances=1,
            )
        last = job.run_times[-1]
        for moment in job.run_times:
            scheduler.add_job(
                fire,
                CronTrigger(
                    day_of_week=job.days, hour=moment.hour, minute=moment.minute, timezone=zone
                ),
                args=(job, moment == last),
                id=f"{job.strategy_id}@{moment:%H%M}",
                misfire_grace_time=MISFIRE_GRACE_SECONDS,
                coalesce=True,
                max_instances=1,
            )
    return scheduler


def next_runs(config: ScheduleConfig, now: datetime, count: int = 3) -> dict[str, list[str]]:
    """The next ``count`` trigger times per job, for checking a configuration."""
    from apscheduler.triggers.cron import CronTrigger

    zone = ZoneInfo(config.timezone)
    plan = {}
    for job in config.jobs:
        moments = []
        for moment in job.run_times:
            trigger = CronTrigger(
                day_of_week=job.days, hour=moment.hour, minute=moment.minute, timezone=zone
            )
            previous, current = None, now
            for _ in range(count):
                fire = trigger.get_next_fire_time(previous, current)
                moments.append(fire)
                previous, current = fire, fire
        plan[job.strategy_id] = [
            item.isoformat(timespec="minutes") for item in sorted(moments)[:count]
        ]
    return plan


def serve(
    config: ScheduleConfig,
    *,
    write: bool = True,
    data_root: str | Path | None = None,
    announce: Callable[[str, str], object] | None = None,
) -> None:
    """Make up missed runs, then block running the schedule until interrupted.

    ``announce(title, body)`` is called when the scheduler starts and stops, so a stopped
    scheduler is noticed in the IM groups. Without ``write`` every run only previews.
    """
    zone = ZoneInfo(config.timezone)
    names = ", ".join(f"{job.strategy_id} {'/'.join(job.times)}" for job in config.jobs)
    if announce:
        announce("QuantSpace 实盘调度已启动", f"任务：{names}（{config.timezone}）")
    try:
        for attempt in catch_up(config, datetime.now(zone), write=write, data_root=data_root):
            LOGGER.info("catch-up %s", attempt)
        build_scheduler(config, write=write, data_root=data_root).start()
    finally:
        if announce:
            announce("QuantSpace 实盘调度已停止", f"任务：{names}。停止期间不会生成信号。")


def load_schedule(path: str | Path) -> ScheduleConfig:
    return ScheduleConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))


def workflow_arguments(argv: Sequence[str] | None = None):
    """Shared argparse options every live workflow accepts from ``run_job``."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Trade date YYYY-MM-DD; default: today in Asia/Shanghai.")
    parser.add_argument("--bar", help="Minute strategies: end time of the bar to run.")
    parser.add_argument(
        "--refresh", action="store_true", help="Minute strategies: pre-open reload and reconcile."
    )
    parser.add_argument("--now", help="Override the current time (YYYY-MM-DDTHH:MM:SS).")
    parser.add_argument("--write", action="store_true", help="Push and log; otherwise preview.")
    parser.add_argument("--final", action="store_true", help="Last attempt of the day.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send the latest full target as a marked test message at any hour; "
        "no trading-day check, ledger, run log, or alerts.",
    )
    parser.add_argument("--data-root", default=None, help="Data root for live state and data.")
    parser.add_argument("--capital", type=float, default=None, help="Capital for target units.")
    parser.add_argument("--lot-size", type=int, default=100, help="Board lot for non-futures.")
    parser.add_argument(
        "--account",
        default=None,
        help="Minute futures strategies: PandaAI account code or id to trade with --write; "
        "only SimNow accounts (broker 9999) are traded.",
    )
    args = parser.parse_args(argv)
    args.bar = datetime.fromisoformat(args.bar) if args.bar else None
    args.now = (
        datetime.fromisoformat(args.now)
        if args.now
        else datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).replace(tzinfo=None)
    )
    args.date = (
        date.fromisoformat(args.date)
        if args.date
        else datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()
    )
    return args


__all__ = [
    "Attempt",
    "JobConfig",
    "ScheduleConfig",
    "build_scheduler",
    "catch_up",
    "load_schedule",
    "next_runs",
    "run_job",
    "serve",
    "tick",
    "workflow_arguments",
]
