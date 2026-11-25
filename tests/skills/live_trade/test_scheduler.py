"""Scheduler configuration, catch-up after downtime, and workflow process handling."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

pytest.importorskip("apscheduler")

from skills.live_trade.runner import RunLog
from skills.live_trade.scheduler import (
    REPOSITORY_ROOT,
    ScheduleConfig,
    build_scheduler,
    catch_up,
    next_runs,
    run_job,
    run_until_stopped,
)

ZONE = ZoneInfo("Asia/Shanghai")
FRIDAY = date(2026, 11, 20)
CONFIG = {
    "jobs": [
        {
            "strategy_id": "demo",
            "module": "strategies.demo.live",
            "times": ["21:00", "17:30"],
            "args": ["--capital", "100000"],
        }
    ]
}


class FakeRunner:
    def __init__(self, code: int = 0, stdout: str = ""):
        self.code, self.stdout, self.calls = code, stdout, []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, self.code, self.stdout, "Traceback: boom")


def _config(**changes) -> ScheduleConfig:
    job = {**CONFIG["jobs"][0], **changes}
    return ScheduleConfig.model_validate({"jobs": [job]})


def test_config_sorts_times_and_defaults_to_weekdays_in_shanghai():
    config = _config()
    assert config.timezone == "Asia/Shanghai"
    assert config.jobs[0].times == ["17:30", "21:00"] and config.jobs[0].days == "mon-fri"


@pytest.mark.parametrize(
    "changes",
    [
        {"times": ["25:00"]},
        {"times": []},
        {"module": "strategies/demo.py"},
        {"strategy_id": "../x"},
    ],
)
def test_config_rejects_bad_jobs(changes):
    with pytest.raises(ValidationError):
        _config(**changes)


def test_config_rejects_duplicate_strategies_and_unknown_zones():
    job = CONFIG["jobs"][0]
    with pytest.raises(ValidationError):
        ScheduleConfig.model_validate({"jobs": [job, job]})
    with pytest.raises(ValidationError):
        ScheduleConfig.model_validate({"timezone": "Mars/Base", "jobs": [job]})


def test_run_job_builds_the_workflow_command(tmp_path):
    runner = FakeRunner()
    attempt = run_job(_config().jobs[0], FRIDAY, final=True, data_root=tmp_path, runner=runner)

    command, kwargs = runner.calls[0]
    assert command == [
        sys.executable,
        "-m",
        "strategies.demo.live",
        "--date",
        "2026-11-20",
        "--write",
        "--final",
        "--data-root",
        str(tmp_path),
        "--capital",
        "100000",
    ]
    assert kwargs["cwd"] == REPOSITORY_ROOT
    # Workflow output is UTF-8 on every OS; a Windows pipe would otherwise be GBK.
    assert (kwargs["encoding"], kwargs["errors"]) == ("utf-8", "replace")
    assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
    assert (attempt.status, attempt.exit_code) == ("ran", 0)


def test_a_crashed_workflow_keeps_its_message_whatever_the_code_page(tmp_path):
    job = _config(module="tests.skills.live_trade.stub_workflow").jobs[0]

    attempt = run_job(job, FRIDAY, final=False, write=False, data_root=tmp_path)

    assert (attempt.status, attempt.exit_code) == ("crashed", 2)
    assert attempt.detail == "策略进程失败 ✗ --date 2026-11-20"


def test_run_job_skips_a_finished_day(tmp_path):
    RunLog("demo", tmp_path).record(FRIDAY, "sent")
    runner = FakeRunner()

    attempt = run_job(_config().jobs[0], FRIDAY, final=False, data_root=tmp_path, runner=runner)

    assert (attempt.status, attempt.detail, runner.calls) == ("skipped", "sent", [])


def test_crashed_workflow_is_alerted_once(tmp_path, http, monkeypatch):
    from .conftest import FEISHU

    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    runner = FakeRunner(code=2)
    job = _config().jobs[0]

    first = run_job(job, FRIDAY, final=False, data_root=tmp_path, runner=runner)
    second = run_job(job, FRIDAY, final=False, data_root=tmp_path, runner=runner)

    assert first.status == second.status == "crashed" and len(runner.calls) == 2
    assert len(http.sent) == 1 and "boom" in http.sent[0]["body"]


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 11, 20, 9, 0, tzinfo=ZONE), []),
        (datetime(2026, 11, 20, 18, 0, tzinfo=ZONE), [False]),
        (datetime(2026, 11, 20, 23, 0, tzinfo=ZONE), [True]),
        (datetime(2026, 11, 21, 23, 0, tzinfo=ZONE), []),
    ],
    ids=["before-first-time", "between-times", "after-last-time", "saturday"],
)
def test_catch_up_runs_a_missed_day_once(tmp_path, now, expected):
    runner = FakeRunner()
    attempts = catch_up(_config(), now, data_root=tmp_path, runner=runner)
    assert [attempt.final for attempt in attempts] == expected


def test_catch_up_converts_other_time_zones(tmp_path):
    runner = FakeRunner()
    # 10:30 UTC is 18:30 in Shanghai: past the first run time.
    attempts = catch_up(
        _config(),
        datetime(2026, 11, 20, 10, 30, tzinfo=ZoneInfo("UTC")),
        data_root=tmp_path,
        runner=runner,
    )
    assert [attempt.final for attempt in attempts] == [False]


def test_next_runs_skip_the_weekend():
    plan = next_runs(_config(), datetime(2026, 11, 20, 20, 0, tzinfo=ZONE), count=3)
    assert plan == {
        "demo": ["2026-11-20T21:00+08:00", "2026-11-23T17:30+08:00", "2026-11-23T21:00+08:00"]
    }


def test_build_scheduler_adds_one_coalesced_job_per_time(tmp_path):
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = build_scheduler(_config(), data_root=tmp_path, scheduler_class=BackgroundScheduler)
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert sorted(jobs) == ["demo@1730", "demo@2100"]
    assert [jobs[name].args[1] for name in sorted(jobs)] == [False, True]
    assert all(job.coalesce and job.max_instances == 1 for job in jobs.values())
    assert all(job.misfire_grace_time == 6 * 3600 for job in jobs.values())


def test_preview_runs_omit_write_and_never_alert(tmp_path, http, monkeypatch):
    from .conftest import FEISHU

    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    runner = FakeRunner(code=2)

    attempt = run_job(
        _config().jobs[0], FRIDAY, final=False, write=False, data_root=tmp_path, runner=runner
    )

    assert "--write" not in runner.calls[0][0]
    assert attempt.status == "crashed" and http.sent == []


# --------------------------------------------------------------------------- minute jobs


def _minute_job(tmp_path, refresh: bool = True):
    from skills.live_trade.feeds import MinuteFeed

    from .fakes import MONDAY, RB_SPEC, FakePandaData, FakeSina

    if refresh:
        feed = MinuteFeed(RB_SPEC, FakePandaData(), data_root=tmp_path, akshare=FakeSina())
        feed.refresh(MONDAY, now=datetime(2026, 11, 20, 18, 0))
    return _config(strategy_id="rb_demo", frequency="5m", times=["18:00"]).jobs[0]


def test_minute_jobs_refresh_at_their_times_even_after_a_finished_day(tmp_path):
    from skills.live_trade.scheduler import tick

    job = _minute_job(tmp_path, refresh=False)
    RunLog("rb_demo", tmp_path).record(FRIDAY, "sent")
    runner = FakeRunner()

    attempt = run_job(job, FRIDAY, final=True, data_root=tmp_path, runner=runner)

    command = runner.calls[0][0]
    assert job.intraday and attempt.status == "ran"
    assert "--refresh" in command and "--final" not in command
    assert tick(job, datetime(2026, 11, 20, 21, 5, 45), data_root=tmp_path, runner=runner) == []
    assert len(runner.calls) == 1


def test_tick_runs_the_oldest_ready_bar(tmp_path):
    from skills.live_trade.scheduler import tick

    job, runner = _minute_job(tmp_path), FakeRunner()

    early = tick(job, datetime(2026, 11, 20, 21, 5, 30), data_root=tmp_path, runner=runner)
    first = tick(job, datetime(2026, 11, 20, 21, 5, 45), data_root=tmp_path, runner=runner)
    RunLog("rb_demo", tmp_path).record(datetime(2026, 11, 20, 21, 5), "sent")
    second = tick(job, datetime(2026, 11, 20, 21, 10, 45), data_root=tmp_path, runner=runner)

    assert early == []
    assert [(item.trade_date, item.status) for item in first + second] == [
        ("2026-11-20T21:05:00", "ran"),
        ("2026-11-20T21:10:00", "ran"),
    ]
    command, kwargs = runner.calls[0]
    assert command[1:] == [
        "-m",
        "strategies.demo.live",
        "--bar",
        "2026-11-20T21:05:00",
        "--write",
        "--data-root",
        str(tmp_path),
        "--capital",
        "100000",
    ]
    assert kwargs["timeout"] == 300


def test_attempts_carry_the_workflow_status_and_detail(tmp_path):
    from skills.live_trade.scheduler import tick

    report = {"status": "stale", "detail": "新浪 21:05 K 线还没出来", "alerts": []}
    stale = FakeRunner(3, json.dumps(report, ensure_ascii=False, indent=2))
    job = _minute_job(tmp_path)

    (attempt,) = tick(job, datetime(2026, 11, 20, 21, 5, 45), data_root=tmp_path, runner=stale)
    daily = run_job(_config().jobs[0], FRIDAY, final=False, data_root=tmp_path, runner=stale)
    quiet = run_job(
        _config().jobs[0], FRIDAY, final=False, data_root=tmp_path, runner=FakeRunner(0, "x")
    )

    assert (attempt.exit_code, attempt.detail) == (3, "stale: 新浪 21:05 K 线还没出来")
    assert daily.detail == "stale: 新浪 21:05 K 线还没出来"
    assert (quiet.status, quiet.detail) == ("ran", "")


def test_a_bar_process_may_run_one_bar_at_most():
    from skills.live_trade.scheduler import bar_timeout

    assert [bar_timeout(freq) for freq in ("1m", "5m", "15m")] == [60, 300, 300]


def test_tick_logs_bars_past_their_deadline_and_alerts_once(tmp_path, http, monkeypatch):
    from skills.live_trade.scheduler import tick

    from .conftest import FEISHU

    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    job, runner = _minute_job(tmp_path), FakeRunner()

    attempts = tick(job, datetime(2026, 11, 20, 21, 20, 45), data_root=tmp_path, runner=runner)
    again = tick(job, datetime(2026, 11, 20, 21, 20, 55), data_root=tmp_path, runner=runner)

    assert [item.status for item in attempts] == ["missed", "missed", "missed", "ran"]
    assert [item.status for item in again] == ["ran"]
    assert all(call[0][4] == "2026-11-20T21:20:00" for call in runner.calls)
    log = RunLog("rb_demo", tmp_path)
    assert log.is_done(datetime(2026, 11, 20, 21, 15))
    assert log.get(datetime(2026, 11, 20, 21, 5))["trade_date"] == "2026-11-23"
    assert len(http.sent) == 1 and "missed" in http.sent[0]["body"]


def test_tick_alerts_a_crashed_bar_once(tmp_path, http, monkeypatch):
    from skills.live_trade.scheduler import tick

    from .conftest import FEISHU

    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    job, runner = _minute_job(tmp_path), FakeRunner(code=2)

    for second in (45, 55):
        (attempt,) = tick(
            job, datetime(2026, 11, 20, 21, 5, second), data_root=tmp_path, runner=runner
        )

    assert attempt.status == "crashed" and len(runner.calls) == 2
    assert len(http.sent) == 1 and "boom" in http.sent[0]["body"]


def test_preview_ticks_remember_what_they_finished(tmp_path, http):
    from skills.live_trade.scheduler import tick

    job, runner, seen = _minute_job(tmp_path), FakeRunner(), set()
    now = datetime(2026, 11, 20, 21, 10, 45)

    first = tick(job, now, write=False, data_root=tmp_path, runner=runner, seen=seen)
    second = tick(job, now, write=False, data_root=tmp_path, runner=runner, seen=seen)

    assert [item.status for item in first] == ["missed", "ran"] and second == []
    assert "--write" not in runner.calls[0][0] and len(runner.calls) == 1
    assert RunLog("rb_demo", tmp_path).get(datetime(2026, 11, 20, 21, 5)) is None
    assert http.sent == []


def test_minute_jobs_get_a_tick_and_always_refresh_on_start(tmp_path):
    from apscheduler.schedulers.background import BackgroundScheduler

    config = _config(strategy_id="rb_demo", frequency="5m", times=["18:00"])
    scheduler = build_scheduler(config, data_root=tmp_path, scheduler_class=BackgroundScheduler)
    jobs = {job.id: job for job in scheduler.get_jobs()}
    runner = FakeRunner()

    attempts = catch_up(
        config, datetime(2026, 11, 22, 9, 0, tzinfo=ZONE), data_root=tmp_path, runner=runner
    )

    assert sorted(jobs) == ["rb_demo@1800", "rb_demo@bars"]
    assert str(jobs["rb_demo@bars"].trigger.fields[-1]) == "*/10"
    assert jobs["rb_demo@bars"].max_instances == 1
    assert [item.status for item in attempts] == ["ran"] and "--refresh" in runner.calls[0][0]


class FakeScheduler:
    def __init__(self):
        self.running, self.events = False, []

    def start(self):
        self.running = True
        self.events.append("start")

    def shutdown(self, wait=True):
        self.running = False
        self.events.append(f"shutdown(wait={wait})")


def test_ctrl_c_reaches_serve_through_a_sleeping_main_thread():
    """Windows handles Ctrl+C in time.sleep but not in the event wait of BlockingScheduler."""
    scheduler, naps = FakeScheduler(), []

    def sleep(seconds):
        naps.append(seconds)
        if len(naps) == 3:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_until_stopped(scheduler, sleep=sleep)
    assert naps == [1.0, 1.0, 1.0]
    assert scheduler.events == ["start", "shutdown(wait=False)"]


def test_the_main_thread_returns_when_the_scheduler_stops_by_itself():
    scheduler = FakeScheduler()
    run_until_stopped(scheduler, sleep=lambda seconds: scheduler.shutdown())
    assert scheduler.events == ["start", "shutdown(wait=True)"]


def test_build_scheduler_runs_in_the_background_by_default(tmp_path):
    from apscheduler.schedulers.background import BackgroundScheduler

    assert isinstance(build_scheduler(_config(), data_root=tmp_path), BackgroundScheduler)


def test_serve_announces_the_stop_after_ctrl_c(tmp_path, monkeypatch):
    import skills.live_trade.scheduler as module

    def interrupted(scheduler, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "catch_up", lambda *args, **kwargs: [])
    monkeypatch.setattr(module, "run_until_stopped", interrupted)
    said = []
    with pytest.raises(KeyboardInterrupt):
        module.serve(_config(), data_root=tmp_path, announce=lambda title, body: said.append(title))
    assert said == ["QuantSpace 实盘调度已启动", "QuantSpace 实盘调度已停止"]


# --------------------------------------------------------------------------- stopping serve

STUB = "tests.skills.live_trade.stub_workflow"


class FakeProcess:
    """A Popen stand-in: ``communicate`` raises each queued exception once, then answers."""

    def __init__(self, raises=()):
        self.raises, self.returncode, self.kills = list(raises), None, 0

    def communicate(self, timeout=None):
        if self.raises:
            raise self.raises.pop(0)
        self.returncode = -9 if self.kills else 0
        return '{"status": "sent"}', ""

    def kill(self):
        self.kills += 1


def test_workflow_processes_do_not_share_the_console_ctrl_c():
    """Ctrl+C in serve's console must not reach a bar that may be placing orders."""
    import os

    from skills.live_trade.scheduler import Workflows

    seen = []

    def popen(command, **kwargs):
        seen.append(kwargs)
        return FakeProcess()

    Workflows(popen=popen)(["python", "-m", STUB], timeout=60, capture_output=True, cwd=".")
    (kwargs,) = seen
    if os.name == "nt":
        assert kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert kwargs["start_new_session"] is True
    assert "capture_output" not in kwargs and kwargs["stdout"] is subprocess.PIPE


def _stub_job(seconds: float):
    return _config(module=STUB, args=["--exit", "0", "--sleep", str(seconds)]).jobs[0]


def _in_background(workflows, job, tmp_path, results):
    import threading

    def run():
        with workflows.job():
            results.append(run_job(job, FRIDAY, final=False, data_root=tmp_path, runner=workflows))

    thread = threading.Thread(target=run)
    thread.start()
    for _ in range(200):
        if workflows.running():
            return thread
        import time

        time.sleep(0.05)
    raise AssertionError("the workflow process did not start")


def test_ctrl_c_lets_a_running_workflow_finish_before_serve_stops(tmp_path):
    import time

    from skills.live_trade.scheduler import Workflows

    workflows, results = Workflows(), []
    thread = _in_background(workflows, _stub_job(1.5), tmp_path, results)
    started, presses = time.monotonic(), []

    def sleep(seconds):
        if not presses:
            presses.append("ctrl+c")
            raise KeyboardInterrupt
        time.sleep(min(seconds, 0.1))

    with pytest.raises(KeyboardInterrupt):
        run_until_stopped(FakeScheduler(), workflows=workflows, sleep=sleep)
    thread.join(5)
    # serve returned only after the process ended by itself: no crash, nothing killed.
    assert time.monotonic() - started >= 1.0
    assert [(item.status, item.exit_code) for item in results] == [("ran", 0)]
    assert workflows.killed == [] and workflows.running() == []
    # Nothing new starts once serve is stopping.
    stopped = run_job(_stub_job(0), FRIDAY, final=False, data_root=tmp_path, runner=workflows)
    assert stopped.status == "stopped"


def test_a_second_ctrl_c_kills_the_workflow_and_alerts_a_forced_stop(tmp_path, http, monkeypatch):
    import time

    from skills.live_trade.scheduler import Workflows

    from .conftest import FEISHU

    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    workflows, results = Workflows(), []
    thread = _in_background(workflows, _stub_job(60), tmp_path, results)
    started, presses = time.monotonic(), []

    def sleep(seconds):
        if len(presses) < 2:
            presses.append("ctrl+c")
            raise KeyboardInterrupt
        time.sleep(min(seconds, 0.1))

    with pytest.raises(KeyboardInterrupt):
        run_until_stopped(FakeScheduler(), workflows=workflows, sleep=sleep)
    thread.join(10)
    assert time.monotonic() - started < 20
    (attempt,) = results
    assert attempt.status == "killed" and "强制停止" in attempt.detail
    assert len(workflows.killed) == 1 and "--date 2026-11-20" in workflows.killed[0]
    (alert,) = http.sent
    text = json.loads(alert["body"])["content"]["text"]
    assert "forced_stop" in text and "强制停止" in text and "核对委托和持仓" in text


def test_ctrl_c_during_the_catch_up_finishes_that_run_then_stops(tmp_path):
    from skills.live_trade.scheduler import Workflows

    once = FakeProcess(raises=[KeyboardInterrupt()])
    workflows = Workflows(popen=lambda command, **kwargs: once)
    result = workflows(["python", "-m", STUB, "--refresh"], timeout=60)
    assert (result.returncode, once.kills, workflows.stopping.is_set()) == (0, 0, True)

    twice = FakeProcess(raises=[KeyboardInterrupt(), KeyboardInterrupt()])
    workflows = Workflows(popen=lambda command, **kwargs: twice)
    workflows._running[twice] = "x"  # noqa: SLF001 - kill() needs it registered
    from skills.live_trade.scheduler import WorkflowStopped

    with pytest.raises(WorkflowStopped) as caught:
        workflows(["python", "-m", STUB, "--refresh"], timeout=60)
    assert caught.value.killed and twice.kills >= 1


def test_serve_says_when_it_killed_workflows(tmp_path, monkeypatch):
    import skills.live_trade.scheduler as module

    def killed(scheduler, *, workflows):
        workflows.killed.append("strategies.demo.live --bar 2026-11-20T21:05:00")
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "catch_up", lambda *args, **kwargs: [])
    monkeypatch.setattr(module, "run_until_stopped", killed)
    said = []
    with pytest.raises(KeyboardInterrupt):
        module.serve(_config(), data_root=tmp_path, announce=lambda title, body: said.append(body))
    assert "强制停止" in said[-1] and "--bar 2026-11-20T21:05:00" in said[-1]


# serve's stand-in: one job thread runs a 2 s workflow while the main thread waits in
# run_until_stopped; {press} is where a console Ctrl+C arrives while the workflow runs.
SERVE_LIKE = """
import json, os, sys, threading, time
sys.path.insert(0, {root!r})
from skills.live_trade.scheduler import Workflows, run_until_stopped

class Scheduler:
    running = False
    def start(self): self.running = True
    def shutdown(self, wait=True): self.running = False

workflows, out = Workflows(), {{}}
command = [sys.executable, "-m", {stub!r}, "--exit", "0", "--sleep", "2"]

def job():
    with workflows.job():
        utf8 = {{**os.environ, "PYTHONIOENCODING": "utf-8"}}  # as serve runs it; GBK otherwise
        done = workflows(command, timeout=60, cwd={root!r}, env=utf8)
        out["code"] = done.returncode

threading.Thread(target=job).start()
{press}
try:
    run_until_stopped(Scheduler(), workflows=workflows)
except KeyboardInterrupt:
    out["stopped"] = True
print(json.dumps(out), flush=True)
"""


def _serve_like(tmp_path, press: str):
    script = tmp_path / "serve_like.py"
    source = SERVE_LIKE.format(root=str(REPOSITORY_ROOT), stub=STUB, press=press)
    script.write_text(source, encoding="utf-8")
    return script


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_a_terminal_ctrl_c_reaches_serve_but_not_its_running_workflow(tmp_path):
    """SIGINT to serve's process group, as a terminal sends it, leaves the bar running."""
    import os
    import signal
    import time

    script = _serve_like(tmp_path, 'print("ready", flush=True)')
    serve = subprocess.Popen(
        [sys.executable, str(script)], stdout=subprocess.PIPE, text=True, start_new_session=True
    )
    assert serve.stdout.readline().strip() == "ready"
    time.sleep(0.5)
    os.killpg(serve.pid, signal.SIGINT)
    out, _ = serve.communicate(timeout=30)
    assert json.loads(out.strip().splitlines()[-1]) == {"code": 0, "stopped": True}


# Windows: once the workflow runs, Ctrl+C goes to every process on serve's console, as when
# someone presses it in the window. Ctrl+C is re-enabled first in case the test runner's
# parent turned it off; the workflow keeps it off through its own process group.
WINDOWS_CTRL_C = """
import ctypes
kernel32 = ctypes.windll.kernel32
kernel32.SetConsoleCtrlHandler(None, False)

def press():
    while not workflows.running():
        time.sleep(0.05)
    time.sleep(0.5)
    kernel32.GenerateConsoleCtrlEvent(0, 0)

threading.Thread(target=press, daemon=True).start()
"""


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console Ctrl+C")
def test_a_console_ctrl_c_reaches_serve_but_not_its_running_workflow(tmp_path):
    """Ctrl+C in serve's console window leaves the bar running (Windows)."""
    script = _serve_like(tmp_path, WINDOWS_CTRL_C)
    # Its own hidden console, so the Ctrl+C reaches only serve and its workflow, not pytest.
    hidden = subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW, wShowWindow=0)
    serve = subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        startupinfo=hidden,
    )
    out, _ = serve.communicate(timeout=30)
    assert json.loads(out.strip().splitlines()[-1]) == {"code": 0, "stopped": True}
