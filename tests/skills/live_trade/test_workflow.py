"""daily_main, minute_main and replay_mismatches, run offline on fake PandaData and Sina."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from skills.live_trade.execution import ExecutionResult
from skills.live_trade.runner import DataNotReady, LiveInputs, RunLog
from skills.live_trade.workflow import (
    daily_main,
    is_trading_day,
    load_with_relogin,
    minute_main,
    replay_mismatches,
)

from .conftest import FEISHU
from .fakes import FRIDAY, RB_SPEC, FakePandaData, FakeSina
from .test_minute import BAR, READY, _above_3000

DAILY_FIELDS = [
    "strategy_id",
    "trade_date",
    "status",
    "detail",
    "execution",
    "signal_id",
    "target",
    "message",
    "deliveries",
    "alerts",
]
DELIVERY_FIELDS = ["signal_id", "target", "message", "deliveries"]


def _report(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


# --------------------------------------------------------------------------- daily


class Calendar:
    """A PandaData stand-in that only answers the calendar: weekdays trade."""

    def __init__(self, broken: bool = False):
        self.broken = broken
        self.calls = []

    def get_trade_cal(self, start, end):
        self.calls.append(start)
        if self.broken:
            raise ConnectionError("calendar unavailable")
        days = pd.date_range(start, end)
        return pd.DataFrame(
            {
                "nature_date": [int(day.strftime("%Y%m%d")) for day in days],
                "is_trade": [int(day.weekday() < 5) for day in days],
            }
        )


@pytest.fixture
def calendar(monkeypatch):
    client = Calendar()
    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: client)
    return client


def _daily_load(calls: list):
    def load(client, trade_date, market_dir):
        calls.append((trade_date, market_dir))
        index = pd.DatetimeIndex([pd.Timestamp(trade_date) - pd.Timedelta(days=1), trade_date])
        weights = pd.DataFrame({"510300.SH": [0.0, 0.5]}, index=index)
        return LiveInputs(weights=weights, prices=pd.DataFrame({"510300.SH": [4.0, 4.1]}, index))

    return load


def test_trading_day_comes_from_the_calendar():
    assert is_trading_day(Calendar(), date(2026, 11, 20))
    assert not is_trading_day(Calendar(), date(2026, 11, 21))


def test_load_retries_once_after_a_dropped_login():
    made, calls = [], []
    expired = RuntimeError("chunk failed")
    expired.__cause__ = RuntimeError(
        "未登录或登录已过期，请调用 panda_data.init_token() 进行登录！"
    )

    def load(client, trade_date, market_dir):
        calls.append(client)
        if len(calls) == 1:
            raise expired
        return "loaded"

    def make_client():
        made.append(object())
        return made[-1]

    assert load_with_relogin(load, make_client, FRIDAY, None) == "loaded"
    assert calls == made and len(made) == 2


def test_other_load_errors_are_not_retried():
    made = []

    def load(client, trade_date, market_dir):
        raise ValueError("bad request")

    with pytest.raises(ValueError, match="bad request"):
        load_with_relogin(load, lambda: made.append(1), FRIDAY, None)
    assert made == [1]


def test_daily_preview_reports_the_signal_and_keeps_nothing(tmp_path, calendar, capsys):
    calls = []

    code = daily_main(
        "demo", _daily_load(calls), ["--date", "2026-11-20", "--data-root", str(tmp_path)]
    )

    report = _report(capsys)
    assert code == 0 and list(report) == DAILY_FIELDS
    assert (report["status"], report["target"]) == ("preview", {"510300.SH": 0.5})
    assert calls == [(FRIDAY, None)] and calendar.calls == ["20261120"]
    assert not (tmp_path / "live").exists()


def test_daily_write_hands_the_live_market_folder_to_load(
    tmp_path, calendar, capsys, http, monkeypatch
):
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    calls = []
    argv = ["--date", "2026-11-20", "--data-root", str(tmp_path), "--write"]

    code = daily_main("demo", _daily_load(calls), argv)

    assert (code, _report(capsys)["status"]) == (0, "sent")
    assert calls == [(FRIDAY, tmp_path / "live" / "demo" / "market")]
    assert RunLog("demo", tmp_path).is_done(FRIDAY)


def test_a_closed_day_never_loads(tmp_path, calendar, capsys):
    calls = []

    code = daily_main(
        "demo", _daily_load(calls), ["--date", "2026-11-21", "--data-root", str(tmp_path)]
    )

    report = _report(capsys)
    assert (code, report["status"], calls) == (0, "not_trading_day", [])
    assert (report["signal_id"], report["deliveries"]) == (None, [])


def test_a_calendar_failure_is_the_run_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("skills.ingest.PandaDataClient", lambda: Calendar(broken=True))
    calls = []

    code = daily_main(
        "demo", _daily_load(calls), ["--date", "2026-11-20", "--data-root", str(tmp_path)]
    )

    report = _report(capsys)
    assert (code, report["status"], calls) == (1, "error", [])
    assert "calendar unavailable" in report["detail"]


def test_daily_test_mode_on_a_weekend_runs_the_last_trading_day(tmp_path, calendar, capsys):
    calls = []

    code = daily_main(
        "demo", _daily_load(calls), ["--date", "2026-11-21", "--test", "--data-root", str(tmp_path)]
    )

    assert (code, _report(capsys)["status"]) == (0, "preview")
    assert calls == [(date(2026, 11, 20), None)]


def test_daily_test_mode_before_the_cutoff_runs_the_day_before(tmp_path, calendar, capsys):
    calls = []
    ready = _daily_load(calls)

    def load(client, trade_date, market_dir):
        if trade_date == date(2026, 11, 23):
            calls.append((trade_date, "not ready"))
            raise DataNotReady("新浪还没有 14:50 的 K 线")
        return ready(client, trade_date, market_dir)

    code = daily_main(
        "demo", load, ["--date", "2026-11-23", "--test", "--data-root", str(tmp_path)]
    )

    assert (code, _report(capsys)["status"]) == (0, "preview")
    assert calls == [(date(2026, 11, 23), "not ready"), (date(2026, 11, 20), None)]


def test_daily_not_ready_is_stale_and_retried(tmp_path, calendar, capsys):
    def load(client, trade_date, market_dir):
        raise DataNotReady("新浪还没有 14:50 的 K 线")

    code = daily_main("demo", load, ["--date", "2026-11-23", "--data-root", str(tmp_path)])

    report = _report(capsys)
    assert (code, report["status"]) == (3, "stale") and "14:50" in report["detail"]


# --------------------------------------------------------------------------- minute


@pytest.fixture
def sina(monkeypatch):
    import skills.ingest
    import skills.ingest.akshare_bars

    fake = FakeSina()
    monkeypatch.setattr(skills.ingest, "PandaDataClient", FakePandaData)
    monkeypatch.setattr(skills.ingest.akshare_bars, "_load_akshare", lambda: fake)
    return fake


def _minute(capsys, tmp_path, *argv) -> tuple[int, dict]:
    code = minute_main(RB_SPEC, _above_3000, [*argv, "--data-root", str(tmp_path)])
    return code, _report(capsys)


def _refreshed(capsys, tmp_path) -> dict:
    code, report = _minute(capsys, tmp_path, "--refresh", "--now", "2026-11-20T18:00:00")
    assert code == 0
    return report


def test_minute_refresh_reports_the_day(tmp_path, sina, capsys):
    report = _refreshed(capsys, tmp_path)

    assert list(report) == [
        "strategy_id",
        "trade_date",
        "status",
        "detail",
        "contracts",
        "bars_today",
        "rows",
        "mismatches",
        "alerts",
    ]
    assert (report["strategy_id"], report["status"]) == ("rb_demo", "refreshed")
    assert report["contracts"] == {"RB_DOMINANT.SHF": "RB2701.SHF"}


def test_minute_bar_previews_the_row_of_the_bar(tmp_path, sina, capsys):
    _refreshed(capsys, tmp_path)
    sina.add("RB2701", (BAR, 3010.0))

    code, report = _minute(capsys, tmp_path, "--bar", BAR.isoformat(), "--now", READY.isoformat())

    assert code == 0
    assert list(report) == ["strategy_id", "bar", "execution", "status", "detail"] + [
        *DELIVERY_FIELDS,
        "alerts",
    ]
    assert (report["bar"], report["status"], report["execution"]) == (
        "2026-11-20T21:05",
        "preview",
        None,
    )
    assert report["target"] == {"RB_DOMINANT.SHF": 1.0}


def test_a_bar_that_is_not_ready_exits_for_a_retry(tmp_path, sina, capsys):
    code, report = _minute(capsys, tmp_path, "--bar", BAR.isoformat(), "--now", READY.isoformat())

    assert (code, report["status"]) == (3, "not_ready")
    assert "signal_id" not in report


def test_minute_test_mode_reports_without_alerts(tmp_path, sina, capsys):
    _refreshed(capsys, tmp_path)

    code, report = _minute(capsys, tmp_path, "--test", "--now", "2026-11-20T18:05:00")

    assert code == 0 and list(report)[:3] == ["strategy_id", "status", "detail"]
    assert "alerts" not in report and not (tmp_path / "live" / "rb_demo" / "ledger.json").exists()


def test_the_intraday_source_can_be_chosen_per_run(tmp_path, calendar, capsys):
    from skills.live_trade.daily import INTRADAY_SOURCE
    from skills.live_trade.workflow import workflow_arguments

    seen = []

    def load(client, trade_date, market_dir):
        seen.append(INTRADAY_SOURCE.get())
        return _daily_load([])(client, trade_date, market_dir)

    argv = ["--date", "2026-11-20", "--data-root", str(tmp_path)]
    assert daily_main("demo", load, [*argv, "--intraday-source", "tqsdk"]) == 0
    assert daily_main("demo", load, argv) == 0
    assert seen == ["tqsdk", "akshare"]
    capsys.readouterr()
    with pytest.raises(SystemExit):
        workflow_arguments(["--intraday-source", "wind"])


def test_tqsdk_is_refused_for_a_minute_strategy_of_funds(tmp_path, sina, capsys):
    from .fakes import EQUITY_SPEC

    argv = ["--refresh", "--intraday-source", "tqsdk", "--data-root", str(tmp_path)]
    assert minute_main(EQUITY_SPEC, _above_3000, argv) == 2
    assert "futures only" in capsys.readouterr().err


def test_a_minute_refresh_with_tqsdk_uses_its_shorter_delay(tmp_path, sina, capsys):
    code, report = _minute(
        capsys, tmp_path, "--refresh", "--now", "2026-11-20T18:00:00", "--intraday-source", "tqsdk"
    )
    assert code == 0, report
    state = json.loads((tmp_path / "live" / "rb_demo" / "feed.json").read_text())
    assert (state["delay_seconds"], state["deadline_seconds"]) == (3, 303)


def test_a_minute_run_needs_a_mode(tmp_path, sina, capsys):
    assert minute_main(RB_SPEC, _above_3000, ["--data-root", str(tmp_path)]) == 2
    assert "--bar, --refresh or --test is required" in capsys.readouterr().err


def test_account_trades_the_bar_through_the_client_cli(tmp_path, sina, capsys, http, monkeypatch):
    seen = []

    def execute_targets(trader, wanted, *, request_id):
        seen.append((trader.account, trader.env, dict(wanted), request_id))
        return ExecutionResult("filled", account=trader.account)

    monkeypatch.setattr("skills.live_trade.panda_cli.discover_cli", lambda: ["panda-live-trading"])
    monkeypatch.setattr("skills.live_trade.execution.execute_targets", execute_targets)
    monkeypatch.setenv("QS_NOTIFY_FEISHU", FEISHU)
    _refreshed(capsys, tmp_path)
    sina.add("RB2701", (BAR, 3010.0))

    code, report = _minute(
        capsys,
        tmp_path,
        *("--bar", BAR.isoformat(), "--now", READY.isoformat(), "--write"),
        *("--capital", "100000", "--account", "100001"),
    )

    assert (code, report["status"], report["execution"]["status"]) == (0, "sent", "filled")
    # 100000 / (3010 * 10) = 3.3 contracts, rounded toward zero
    assert seen == [
        (
            "100001",
            {"PANDA_LIVE_TRACE_ID": "rb_demo-20261120T2105"},
            {"RB2701.SHF": 3},
            "rb_demo:2026-11-20T21:05",
        )
    ]


def test_account_without_the_client_cli_stops(tmp_path, sina, monkeypatch):
    monkeypatch.setattr("skills.live_trade.panda_cli.discover_cli", lambda: None)

    with pytest.raises(SystemExit, match="PandaAI client CLI not found"):
        minute_main(
            RB_SPEC,
            _above_3000,
            ["--bar", BAR.isoformat(), "--account", "100001", "--data-root", str(tmp_path)],
        )


# --------------------------------------------------------------------------- replay


def _panel(rows: int = 120) -> pd.DataFrame:
    close = 100.0 * np.exp(np.cumsum(np.random.default_rng(1).normal(0.0, 0.01, (rows, 2)), axis=0))
    index = pd.date_range("2026-11-02 09:05", periods=rows, freq="5min", name="eob")
    frames = {
        symbol: pd.DataFrame({"close": close[:, column]}, index=index)
        for column, symbol in enumerate(["A.SH", "B.SH"])
    }
    return pd.concat(frames, names=["symbol"])


def _momentum(panel: pd.DataFrame) -> pd.DataFrame:
    """Long the symbols above their 10-bar mean: needs the last 10 bars only."""
    close = panel["close"].unstack("symbol").sort_index()
    return (close > close.rolling(10).mean()).astype(float) / 2


def test_a_causal_window_function_replays_exactly():
    panel = _panel()

    assert replay_mismatches(_momentum, panel, window=10) == []
    assert replay_mismatches(_momentum, panel) == []
    assert len(replay_mismatches(_momentum, panel, window=9, last=20)) > 0


def test_look_ahead_is_found():
    def peeks(panel):
        close = panel["close"].unstack("symbol").sort_index()
        return (close.shift(-1) > close).astype(float) / 2

    mismatches = replay_mismatches(peeks, _panel(), last=30)
    assert mismatches and all(isinstance(stamp, pd.Timestamp) for stamp in mismatches)


def test_history_beyond_the_window_is_found_but_a_fixed_start_is_fine():
    def since_start(close):
        """Long once the close is above its running maximum so far: depends on the start."""
        return (close >= close.cummax()).astype(float) / 2

    close = _panel()["close"].unstack("symbol")
    assert replay_mismatches(since_start, close) == []
    assert replay_mismatches(since_start, close, window=10)


def test_missing_and_zero_weights_are_equal():
    close = _panel()["close"].unstack("symbol")

    def sparse(frame):
        weights = (frame > frame.rolling(5).mean()).astype(float)
        return weights.where(weights > 0)

    assert replay_mismatches(sparse, close, window=5) == []


def test_weights_that_end_before_the_bar_are_a_mismatch():
    close = _panel(30)["close"].unstack("symbol")

    def lagging(frame):
        return (frame > 100).astype(float).iloc[:-1]

    assert len(replay_mismatches(lagging, close, last=5)) == 5


def test_the_report_is_utf8_even_on_a_gbk_pipe(monkeypatch):
    """A Windows pipe defaults to GBK, which cannot encode ✓ and garbles Chinese for agents."""
    import io
    import sys

    from skills.live_trade.workflow import _emit

    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="gbk"))
    assert _emit({"detail": "已撤单 ✓"}, 3) == 3
    sys.stdout.flush()
    assert json.loads(raw.getvalue().decode("utf-8")) == {"detail": "已撤单 ✓"}
