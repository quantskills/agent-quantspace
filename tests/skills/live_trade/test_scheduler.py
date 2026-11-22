"""Scheduler configuration, catch-up after downtime, and workflow process handling."""

from __future__ import annotations

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
    def __init__(self, code: int = 0):
        self.code, self.calls = code, []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, self.code, "", "Traceback: boom")


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
    assert (attempt.status, attempt.exit_code) == ("ran", 0)


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
    assert tick(job, datetime(2026, 11, 20, 21, 5, 25), data_root=tmp_path, runner=runner) == []
    assert len(runner.calls) == 1


def test_tick_runs_the_oldest_ready_bar(tmp_path):
    from skills.live_trade.scheduler import tick

    job, runner = _minute_job(tmp_path), FakeRunner()

    early = tick(job, datetime(2026, 11, 20, 21, 5, 10), data_root=tmp_path, runner=runner)
    first = tick(job, datetime(2026, 11, 20, 21, 5, 25), data_root=tmp_path, runner=runner)
    RunLog("rb_demo", tmp_path).record(datetime(2026, 11, 20, 21, 5), "sent")
    second = tick(job, datetime(2026, 11, 20, 21, 10, 25), data_root=tmp_path, runner=runner)

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


def test_tick_logs_bars_past_their_deadline_and_alerts_once(tmp_path, http, monkeypatch):
    from skills.live_trade.scheduler import tick

    from .conftest import FEISHU

    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    job, runner = _minute_job(tmp_path), FakeRunner()

    attempts = tick(job, datetime(2026, 11, 20, 21, 20, 25), data_root=tmp_path, runner=runner)
    again = tick(job, datetime(2026, 11, 20, 21, 20, 35), data_root=tmp_path, runner=runner)

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

    for second in (25, 35):
        (attempt,) = tick(
            job, datetime(2026, 11, 20, 21, 5, second), data_root=tmp_path, runner=runner
        )

    assert attempt.status == "crashed" and len(runner.calls) == 2
    assert len(http.sent) == 1 and "boom" in http.sent[0]["body"]


def test_preview_ticks_remember_what_they_finished(tmp_path, http):
    from skills.live_trade.scheduler import tick

    job, runner, seen = _minute_job(tmp_path), FakeRunner(), set()
    now = datetime(2026, 11, 20, 21, 10, 25)

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
