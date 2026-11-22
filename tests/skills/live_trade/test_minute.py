"""run_bar and refresh_day: one bar per run, the pre-open refresh, and reconciliation."""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd

from skills.live_trade.feeds import MinuteFeed
from skills.live_trade.minute import refresh_day, run_bar
from skills.live_trade.runner import RunLog

from .conftest import FEISHU
from .fakes import EQUITY_SPEC, FRIDAY, MONDAY, RB_SPEC, FakePandaData, FakeSina

BAR = datetime(2026, 11, 20, 21, 5)  # first bar of Monday's trading day
READY = datetime(2026, 11, 20, 21, 5, 25)


def _above_3000(panel: pd.DataFrame) -> pd.DataFrame:
    """Long while the close is above 3000; PandaData's fake bars sit at exactly 3000."""
    close = panel["close"].unstack("symbol").sort_index()
    return (close > 3000).astype(float)


def _equal(panel: pd.DataFrame) -> pd.DataFrame:
    close = panel["close"].unstack("symbol").sort_index()
    return close.notna().astype(float) / close.shape[1]


def _feed(tmp_path, spec=RB_SPEC, client=None, sina=None, refresh_at=None) -> MinuteFeed:
    feed = MinuteFeed(
        spec, client or FakePandaData(), data_root=tmp_path, akshare=sina or FakeSina(), pause=0
    )
    if refresh_at is not None:
        refresh_day(spec, feed, _above_3000, now=refresh_at, data_root=tmp_path)
    return feed


def _run(feed, tmp_path, *, bar=BAR, now=READY, compute=_above_3000, **options):
    return run_bar(
        feed.spec, feed, compute, bar=bar, now=now, data_root=tmp_path, urls=[FEISHU], **options
    )


def test_no_refresh_means_not_ready_and_one_alert_a_day(tmp_path, http):
    feed = _feed(tmp_path)

    first = _run(feed, tmp_path, write=True)
    second = _run(feed, tmp_path, bar=datetime(2026, 11, 20, 21, 10), write=True)

    assert (first.status, first.exit_code, second.status) == ("not_ready", 3, "not_ready")
    assert len(http.sent) == 1 and "not_ready" in http.sent[0]["body"]


def test_a_time_that_is_not_a_bar_end_is_an_error(tmp_path):
    feed = _feed(tmp_path, refresh_at=datetime(2026, 11, 20, 18, 0))
    outcome = _run(feed, tmp_path, bar=datetime(2026, 11, 20, 21, 7))
    assert outcome.status == "error" and "不是 2026-11-23 的 K 线结束时刻" in outcome.detail


def test_stale_until_sina_has_the_bar(tmp_path):
    sina = FakeSina()
    sina.add("RB2701", (BAR, 3010.0))
    feed = _feed(tmp_path, sina=sina, refresh_at=datetime(2026, 11, 20, 18, 0))

    outcome = _run(
        feed, tmp_path, bar=datetime(2026, 11, 20, 21, 10), now=datetime(2026, 11, 20, 21, 10, 25)
    )

    assert (outcome.status, outcome.exit_code) == ("stale", 3)
    assert "最新 K 线 2026-11-20T21:05:00" in outcome.detail


def test_sina_failure_is_a_source_error_with_an_alert(tmp_path, http):
    sina = FakeSina()
    sina.failing.add("RB2701")
    feed = _feed(tmp_path, sina=sina, refresh_at=datetime(2026, 11, 20, 18, 0))

    outcome = _run(feed, tmp_path, write=True)

    assert (outcome.status, outcome.exit_code) == ("source_error", 3)
    assert "Sina closed the connection" in outcome.detail
    assert len(http.sent) == 1 and "source_error" in http.sent[0]["body"]


def test_a_sent_bar_logs_its_target_and_is_then_done(tmp_path, http):
    sina = FakeSina()
    sina.add("RB2701", (BAR, 3010.0))
    feed = _feed(tmp_path, sina=sina, refresh_at=datetime(2026, 11, 20, 18, 0))

    outcome = _run(feed, tmp_path, write=True)

    assert (outcome.status, outcome.exit_code) == ("sent", 0)
    assert "RB_DOMINANT.SHF 当前对应 RB2701.SHF" in outcome.delivery.body
    assert outcome.delivery.signal.target == {"RB_DOMINANT.SHF": 1.0}
    entry = RunLog("rb_demo", tmp_path).get(BAR)
    assert entry["target"] == {"RB_DOMINANT.SHF": 1.0} and entry["trade_date"] == "2026-11-23"
    assert list(RunLog("rb_demo", tmp_path).bars(MONDAY)) == ["2026-11-20T21:05:00"]
    assert len(http.sent) == 1

    again = _run(feed, tmp_path, write=True)
    assert (again.status, again.detail, len(http.sent)) == ("done", "sent", 1)


def test_previews_neither_log_nor_send(tmp_path, http):
    sina = FakeSina()
    sina.add("RB2701", (BAR, 3010.0))
    feed = _feed(tmp_path, sina=sina, refresh_at=datetime(2026, 11, 20, 18, 0))

    outcome = _run(feed, tmp_path)

    assert outcome.status == "preview" and http.sent == []
    assert RunLog("rb_demo", tmp_path).get(BAR) is None


def test_a_bar_past_its_deadline_is_missed(tmp_path, http):
    feed = _feed(tmp_path, refresh_at=datetime(2026, 11, 20, 18, 0))

    outcome = _run(feed, tmp_path, now=datetime(2026, 11, 20, 21, 10), write=True)

    assert (outcome.status, outcome.exit_code) == ("missed", 0)
    assert RunLog("rb_demo", tmp_path).is_done(BAR)
    assert len(http.sent) == 1 and "missed" in http.sent[0]["body"]


def test_weights_must_reach_the_bar(tmp_path):
    sina = FakeSina()
    sina.add("RB2701", (BAR, 3010.0))
    feed = _feed(tmp_path, sina=sina, refresh_at=datetime(2026, 11, 20, 18, 0))

    lagging = _run(feed, tmp_path, compute=lambda panel: _above_3000(panel).iloc[:-1])
    empty = _run(feed, tmp_path, compute=lambda panel: _above_3000(panel).iloc[:0])

    assert lagging.status == "stale" and "早于 K 线" in lagging.detail
    assert empty.status == "error" and "empty weights" in empty.detail


def test_halted_stocks_keep_their_last_delivered_weight(tmp_path):
    client, sina = FakePandaData(), FakeSina()
    client.ex_dates["601998.SH"] = ["20261120"]
    sina.add("sh601998", (datetime(2026, 11, 20, 9, 35), 9.5))
    sina.add("sh510300", (datetime(2026, 11, 20, 9, 35), 4.0))
    feed = MinuteFeed(EQUITY_SPEC, client, data_root=tmp_path, akshare=sina, pause=0)
    refresh_day(EQUITY_SPEC, feed, _equal, now=datetime(2026, 11, 20, 8, 30), data_root=tmp_path)

    outcome = _run(
        feed,
        tmp_path,
        bar=datetime(2026, 11, 20, 9, 35),
        now=datetime(2026, 11, 20, 9, 35, 30),
        compute=_equal,
    )

    assert outcome.status == "preview"
    assert outcome.delivery.signal.target == {"510300.SH": 0.5}
    assert "601998.SH 今天暂停调仓" in outcome.delivery.body
    assert outcome.delivery.signal.prices["510300.SH"] == 4.0


def test_refresh_day_reports_bars_whose_target_changes_on_pandadata(tmp_path, http):
    sina = FakeSina()
    sina.add("RB2701", (BAR, 3010.0))  # PandaData later says 3000, which is flat
    feed = _feed(tmp_path, sina=sina)
    first = refresh_day(
        RB_SPEC,
        feed,
        _above_3000,
        now=datetime(2026, 11, 20, 18, 0),
        write=True,
        data_root=tmp_path,
        urls=[FEISHU],
    )
    assert (first.status, first.trade_date, first.mismatches) == ("refreshed", "2026-11-23", {})
    assert _run(feed, tmp_path, write=True).status == "sent"

    outcome = refresh_day(
        RB_SPEC,
        feed,
        _above_3000,
        now=datetime(2026, 11, 23, 18, 0),
        write=True,
        data_root=tmp_path,
        urls=[FEISHU],
    )

    assert (outcome.status, outcome.trade_date, outcome.exit_code) == ("refreshed", "2026-11-24", 0)
    (mismatch,) = outcome.mismatches["2026-11-23"]
    assert mismatch.bar == "2026-11-20T21:05:00"
    assert (mismatch.sent, mismatch.recomputed, mismatch.symbols) == (
        {"RB_DOMINANT.SHF": 1.0},
        {},
        ["RB_DOMINANT.SHF"],
    )
    saved = json.loads((feed.root / "reconcile" / "2026-11-23.signals.json").read_text())
    assert saved["mismatches"][0]["bar"] == "2026-11-20T21:05:00"
    text = json.loads(http.sent[-1]["body"])["content"]["text"]
    assert "类型：reconcile" in text and "收盘价不同的 K 线 1/1" in text


def test_refresh_day_failure_alerts_once(tmp_path, http):
    client = FakePandaData()
    client.dominant = {}
    feed = _feed(tmp_path, client=client)

    for _ in range(2):
        outcome = refresh_day(
            RB_SPEC,
            feed,
            _above_3000,
            now=datetime(2026, 11, 20, 18, 0),
            write=True,
            data_root=tmp_path,
            urls=[FEISHU],
        )

    assert (outcome.status, outcome.exit_code, outcome.trade_date) == ("error", 1, "2026-11-23")
    assert "no dominant contract" in outcome.detail
    assert len(http.sent) == 1 and "refresh_error" in http.sent[0]["body"]


def test_refresh_day_alerts_halted_symbols(tmp_path, http):
    client = FakePandaData()
    client.ex_dates["601998.SH"] = ["20261120"]
    feed = MinuteFeed(EQUITY_SPEC, client, data_root=tmp_path, akshare=FakeSina(), pause=0)

    outcome = refresh_day(
        EQUITY_SPEC,
        feed,
        _equal,
        now=datetime(2026, 11, 20, 8, 30),
        write=True,
        data_root=tmp_path,
        urls=[FEISHU],
    )

    assert outcome.status == "refreshed" and outcome.trade_date == FRIDAY.isoformat()
    assert len(http.sent) == 1 and "601998.SH" in http.sent[0]["body"]
