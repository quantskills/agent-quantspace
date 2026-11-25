"""Cross-platform scheduler for live runs, built on APScheduler 3.x.

The scheduler only decides when to run. Each run is a separate ``python -m <module>`` process
of a strategy workflow that calls ``run_live``; the run log, not the scheduler, decides whether
a trade date is finished. A run that was missed while the process was stopped or the computer
slept is made up once when the process starts or wakes, and finished days are skipped.

A minute-level job (``frequency`` such as ``5m``) runs ``--refresh`` at its ``times`` (the
pre-open reload) and, every few seconds, starts one ``--bar <end time>`` process for the
oldest bar that is ready and not finished. The bars of the day come from the feed state the
refresh wrote; a bar past its deadline is logged as ``missed`` and alerted once a day.

``serve`` starts every workflow process in its own process group (Windows) or session
(POSIX), so a Ctrl+C in the console reaches only ``serve``, not a bar that may be placing
orders. ``serve`` then starts nothing new, waits for the running processes to finish within
their own timeouts, and only then pushes its stop message; a second Ctrl+C kills them and
alerts that they were stopped by force (:class:`Workflows`).
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time as clock_time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time
from functools import cache
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
# How often serve's main thread wakes up. It sleeps rather than waits on the scheduler:
# on Windows Ctrl+C interrupts time.sleep but not a wait on a lock or event.
POLL_SECONDS = 1.0
# Once its last process has ended, a job still logs and alerts; serve waits this long for it.
JOB_GRACE_SECONDS = 30.0
# Windows: a child in its own process group does not get the console's Ctrl+C.
_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
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


def _report_summary(stdout: str | None) -> str:
    """``status: detail`` from the JSON report a workflow prints, so the serve log says why."""
    try:
        report = json.loads(stdout or "")
    except ValueError:
        return ""
    if not isinstance(report, dict):
        return ""
    status, detail = str(report.get("status") or ""), str(report.get("detail") or "")
    return (f"{status}: {detail}" if detail else status)[:300]


class WorkflowStopped(RuntimeError):
    """``serve`` is stopping: the process was not started, or a forced stop killed it."""

    def __init__(self, message: str, *, killed: bool = False, returncode: int | None = None):
        super().__init__(message)
        self.killed, self.returncode = killed, returncode


class _WindowsJob:
    """A Windows job object holding a workflow process and every process it starts.

    ``Popen.kill`` ends only the direct child, the venv's ``python.exe`` launcher, and
    ``taskkill /T`` walks the process list, which can take 15 seconds; ending the job ends
    the whole tree at once. A process may still leave the job on request
    (``CREATE_BREAKAWAY_FROM_JOB``), so a program that asks keeps working, unkilled.
    """

    _ACCESS = 0x0101  # PROCESS_SET_QUOTA | PROCESS_TERMINATE
    _BREAKAWAY_OK = 0x0800  # JOB_OBJECT_LIMIT_BREAKAWAY_OK, an extended limit
    _EXTENDED_LIMITS = 9  # JobObjectExtendedLimitInformation

    def __init__(self, handle) -> None:
        self._handle, self._lock = handle, threading.Lock()

    @staticmethod
    @cache
    def _kernel32():
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle, dword, boolean = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL
        for name, argtypes, restype in (
            ("CreateJobObjectW", (wintypes.LPVOID, wintypes.LPCWSTR), handle),
            ("SetInformationJobObject", (handle, ctypes.c_int, wintypes.LPVOID, dword), boolean),
            ("OpenProcess", (dword, boolean, dword), handle),
            ("AssignProcessToJobObject", (handle, handle), boolean),
            ("TerminateJobObject", (handle, wintypes.UINT), boolean),
            ("CloseHandle", (handle,), boolean),
        ):
            function = getattr(kernel32, name)
            function.argtypes, function.restype = argtypes, restype
        return kernel32

    @classmethod
    def holding(cls, pid: int) -> _WindowsJob | None:
        """A job holding process ``pid``, or None if one cannot be made."""
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class Limits(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
            _fields_ = [
                ("BasicLimitInformation", Basic),
                ("IoInfo", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        try:
            kernel32 = cls._kernel32()
            job = kernel32.CreateJobObjectW(None, None)
        except (AttributeError, OSError):
            return None
        if not job:
            return None
        limits = Limits(BasicLimitInformation=Basic(LimitFlags=cls._BREAKAWAY_OK))
        made = kernel32.SetInformationJobObject(
            job, cls._EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)
        )
        process = kernel32.OpenProcess(cls._ACCESS, False, pid) if made else None
        if process:
            made = kernel32.AssignProcessToJobObject(job, process)
            kernel32.CloseHandle(process)
        if not (made and process):
            kernel32.CloseHandle(job)
            return None
        return cls(job)

    def kill(self) -> bool:
        with self._lock:
            return bool(self._handle) and bool(self._kernel32().TerminateJobObject(self._handle, 1))

    def close(self) -> None:
        """Forget the job; its processes keep running."""
        with self._lock:
            if self._handle:
                self._kernel32().CloseHandle(self._handle)
                self._handle = None


def _kill_tree(process: subprocess.Popen, job: _WindowsJob | None = None) -> None:
    """Kill a workflow process and every process it started, such as a PandaAI CLI call.

    The child leads its own session on POSIX (see :class:`Workflows`), so its process group
    is killed; on Windows its job, else ``taskkill /T``.
    """
    pid = getattr(process, "pid", None)
    if isinstance(pid, int) and pid > 0 and process.returncode is None:
        try:
            if os.name != "nt":
                os.killpg(pid, signal.SIGKILL)
            elif job is None or not job.kill():
                command = ["taskkill", "/F", "/T", "/PID", str(pid)]
                subprocess.run(command, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        process.kill()
    except OSError:
        pass


class Workflows:
    """The workflow processes of one ``serve``, called like ``subprocess.run``.

    Each process gets its own process group (Windows ``CREATE_NEW_PROCESS_GROUP``) or
    session (POSIX ``start_new_session``), so the console's Ctrl+C reaches only ``serve``.
    After :meth:`stop` no process starts (:class:`WorkflowStopped`); :meth:`wait` lets the
    running ones finish within their own timeouts, and :meth:`kill` ends them by force, with
    the processes they started (on Windows through a job object). A process waits in steps
    of :data:`POLL_SECONDS`, so a Ctrl+C in the main thread (the
    catch-up) is noticed on Windows too: the first stops ``serve`` after this run, the
    second kills it.
    """

    def __init__(
        self, *, popen=subprocess.Popen, clock: Callable[[], float] = clock_time.monotonic
    ):
        self._popen, self._clock = popen, clock
        self._lock = threading.Lock()
        self._running: dict[subprocess.Popen, str] = {}
        self._trees: dict[subprocess.Popen, _WindowsJob | None] = {}
        self._jobs = 0
        self.stopping = threading.Event()
        self.killed: list[str] = []

    def __call__(self, command, *, timeout: float, **options) -> subprocess.CompletedProcess:
        if self.stopping.is_set():
            raise WorkflowStopped("serve 正在停止，没有启动新的策略进程")
        options.pop("capture_output", None)
        if os.name == "nt":
            options["creationflags"] = options.get("creationflags", 0) | _NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        process = self._popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
        label = " ".join(str(part) for part in command[2:5])
        pid = getattr(process, "pid", None)
        tree = _WindowsJob.holding(pid) if os.name == "nt" and isinstance(pid, int) else None
        with self._lock:
            self._running[process], self._trees[process] = label, tree
        deadline, interrupted = self._clock() + timeout, False
        try:
            while True:
                try:
                    step = max(0.0, min(POLL_SECONDS, deadline - self._clock()))
                    stdout, stderr = process.communicate(timeout=step)
                    break
                except subprocess.TimeoutExpired:
                    if self._clock() >= deadline:
                        _kill_tree(process, tree)
                        stdout, stderr = process.communicate()
                        raise subprocess.TimeoutExpired(command, timeout, stdout, stderr) from None
                except KeyboardInterrupt:
                    # Only the main thread gets here, during the catch-up.
                    if interrupted:
                        self.kill()
                    else:
                        interrupted = True
                        self.stop()
                        LOGGER.warning(
                            "stopping: waiting for %s to finish; press Ctrl+C again to kill it",
                            label,
                        )
        finally:
            with self._lock:
                self._running.pop(process, None)
                self._trees.pop(process, None)
            if tree is not None:
                tree.close()
        if label in self.killed:
            raise WorkflowStopped(
                f"serve 被强制停止，策略进程已终止（退出码 {process.returncode}）",
                killed=True,
                returncode=process.returncode,
            )
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    @contextmanager
    def job(self) -> Iterator[None]:
        """Mark a scheduled job as running, so :meth:`wait` lets it log and alert."""
        with self._lock:
            self._jobs += 1
        try:
            yield
        finally:
            with self._lock:
                self._jobs -= 1

    def stop(self) -> None:
        self.stopping.set()

    def running(self) -> list[str]:
        with self._lock:
            return list(self._running.values())

    def kill(self) -> None:
        """Kill every running process and its children; their runs raise
        :class:`WorkflowStopped`."""
        with self._lock:
            processes = [
                (process, label, self._trees.get(process))
                for process, label in self._running.items()
            ]
        for process, label, tree in processes:
            if label not in self.killed:
                self.killed.append(label)
            _kill_tree(process, tree)

    def wait(
        self,
        *,
        poll_seconds: float = POLL_SECONDS,
        sleep: Callable[[float], object] = clock_time.sleep,
    ) -> None:
        """Sleep until no job runs: processes end within their own timeouts, then a job has
        :data:`JOB_GRACE_SECONDS` to log and alert. Ctrl+C here kills the processes, and once
        more stops waiting."""
        idle_since = None
        while True:
            with self._lock:
                jobs, processes = self._jobs, len(self._running)
            if not jobs and not processes:
                return
            if processes:
                idle_since = None
            else:
                idle_since = self._clock() if idle_since is None else idle_since
                if self._clock() - idle_since >= JOB_GRACE_SECONDS:
                    LOGGER.warning("stopped without waiting longer for %s job(s)", jobs)
                    return
            try:
                sleep(poll_seconds)
            except KeyboardInterrupt:
                if self.killed:
                    return
                LOGGER.warning("second Ctrl+C: killing %s", ", ".join(self.running()) or "nothing")
                self.kill()


def _run_workflow(runner: Callable[..., subprocess.CompletedProcess], command, timeout: int):
    """Run one workflow process; its output is UTF-8 on every OS (GBK pipes on Windows)."""
    return runner(
        command,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=timeout,
    )


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
    summary = ""
    try:
        completed = _run_workflow(runner, command, RUN_TIMEOUT_SECONDS)
        code, tail = completed.returncode, (completed.stderr or "").strip()[-500:]
        summary = _report_summary(completed.stdout)
    except WorkflowStopped as exc:
        return _stopped(job, trade_date, trade_date.isoformat(), final, exc, write, runs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        code, tail = None, f"{type(exc).__name__}: {exc}"
    if code in KNOWN_EXIT_CODES:
        return Attempt(job.strategy_id, trade_date.isoformat(), final, "ran", code, summary)
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


def _stopped(job, trade_date: date, label: str, final: bool, exc, write: bool, runs) -> Attempt:
    """The attempt of a run ``serve`` did not start while stopping, or killed by force."""
    if not exc.killed:
        return Attempt(job.strategy_id, label, final, "stopped", detail=str(exc))
    LOGGER.error("%s %s killed by a forced stop (exit %s)", job.strategy_id, label, exc.returncode)
    if write and runs.claim_alert(trade_date, "forced_stop"):
        send_alert(
            job.strategy_id,
            trade_date,
            "forced_stop",
            f"运行：{label}\n{exc}。如果它正在下单，请在客户端核对委托和持仓。",
        )
    return Attempt(job.strategy_id, label, final, "killed", exc.returncode, str(exc))


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
        summary = ""
        try:
            completed = _run_workflow(runner, command, bar_timeout(state.frequency))
            code, tail = completed.returncode, (completed.stderr or "").strip()[-500:]
            summary = _report_summary(completed.stdout)
        except WorkflowStopped as exc:
            attempts.append(_stopped(job, bar.trading_date, label, False, exc, write, runs))
            break
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, tail = None, f"{type(exc).__name__}: {exc}"
        if code in KNOWN_EXIT_CODES:
            if code == 0:
                seen.add(label)
            attempts.append(Attempt(job.strategy_id, label, False, "ran", code, summary))
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


@contextmanager
def _no_job() -> Iterator[None]:
    yield


def build_scheduler(
    config: ScheduleConfig,
    *,
    write: bool = True,
    data_root: str | Path | None = None,
    scheduler_class=None,
    workflows: Workflows | None = None,
):
    """An APScheduler scheduler with one cron trigger per job and run time; it runs its
    triggers in a background thread once started, their processes through ``workflows``."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    zone = ZoneInfo(config.timezone)
    scheduler = (scheduler_class or BackgroundScheduler)(timezone=zone)

    runner = workflows or subprocess.run
    active = workflows.job if workflows else _no_job

    def fire(job: JobConfig, final: bool) -> None:
        with active():
            attempt = run_job(
                job,
                datetime.now(zone).date(),
                final=final,
                write=write,
                data_root=data_root,
                runner=runner,
            )
            LOGGER.info("%s", attempt)

    seen: dict[str, set[str]] = {}

    def fire_tick(job: JobConfig) -> None:
        with active():
            for attempt in tick(
                job,
                datetime.now(zone).replace(tzinfo=None),
                write=write,
                data_root=data_root,
                runner=runner,
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


def run_until_stopped(
    scheduler,
    *,
    workflows: Workflows | None = None,
    poll_seconds: float = POLL_SECONDS,
    sleep: Callable[[float], object] = clock_time.sleep,
) -> None:
    """Start a background ``scheduler`` and sleep in this thread until it stops or Ctrl+C.

    A ``BlockingScheduler`` would wait on an event until the next trigger, and on Windows
    Ctrl+C is only handled when that wait ends, which can be hours away. On Ctrl+C the
    scheduler stops triggering, ``workflows`` starts nothing new and is waited for
    (:meth:`Workflows.wait`), then the ``KeyboardInterrupt`` goes on.
    """
    scheduler.start()
    try:
        while scheduler.running:
            sleep(poll_seconds)
    except KeyboardInterrupt:
        if workflows is not None:
            workflows.stop()
            if scheduler.running:
                scheduler.shutdown(wait=False)
            running = workflows.running()
            if running:
                LOGGER.warning(
                    "stopping: waiting for %s to finish; press Ctrl+C again to kill",
                    ", ".join(running),
                )
            workflows.wait(poll_seconds=poll_seconds, sleep=sleep)
        raise
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


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
    workflows = Workflows()
    try:
        now = datetime.now(zone)
        for attempt in catch_up(config, now, write=write, data_root=data_root, runner=workflows):
            LOGGER.info("catch-up %s", attempt)
        if workflows.stopping.is_set():
            # Ctrl+C during the catch-up, whose run was let finish.
            raise KeyboardInterrupt
        scheduler = build_scheduler(config, write=write, data_root=data_root, workflows=workflows)
        run_until_stopped(scheduler, workflows=workflows)
    finally:
        if announce:
            body = f"任务：{names}。停止期间不会生成信号。"
            if workflows.killed:
                body += (
                    f"\n强制停止：终止了正在运行的策略进程（{'；'.join(workflows.killed)}），"
                    "如果它们正在下单，请在客户端核对委托和持仓。"
                )
            announce("QuantSpace 实盘调度已停止", body)


def load_schedule(path: str | Path) -> ScheduleConfig:
    return ScheduleConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "Attempt",
    "JobConfig",
    "ScheduleConfig",
    "WorkflowStopped",
    "Workflows",
    "build_scheduler",
    "catch_up",
    "load_schedule",
    "next_runs",
    "run_job",
    "run_until_stopped",
    "serve",
    "tick",
]
