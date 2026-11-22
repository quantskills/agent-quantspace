"""run_live: trading-day and freshness checks, run log, alerts, and retries."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from skills.live_trade.runner import LiveInputs, RunLog, run_live

from .conftest import FEISHU, WECOM

FRIDAY = date(2026, 11, 20)


def _weights(*rows: tuple[str, dict[str, float]]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(day) for day, _ in rows], name="eob")
    return pd.DataFrame([values for _, values in rows], index=index).fillna(0.0)


def _loader(frame: pd.DataFrame, calls: list | None = None):
    def load() -> LiveInputs:
        if calls is not None:
            calls.append(1)
        return LiveInputs(weights=frame)

    return load


def _run(tmp_path, load, day=FRIDAY, **options):
    options.setdefault("urls", [FEISHU])
    return run_live(
        "demo",
        load,
        trade_date=day,
        is_trading_day=options.pop("trading", True),
        data_root=tmp_path,
        **options,
    )


def test_non_trading_day_finishes_without_loading(tmp_path, http):
    calls = []
    outcome = _run(
        tmp_path, _loader(_weights(), calls), day=date(2026, 11, 21), trading=False, write=True
    )

    assert (outcome.status, outcome.exit_code, calls, http.sent) == ("not_trading_day", 0, [], [])
    assert RunLog("demo", tmp_path).is_done(date(2026, 11, 21))


def test_stale_data_retries_and_alerts_once_on_the_final_attempt(tmp_path, http):
    stale = _weights(("2026-11-19", {"510300.SH": 1.0}))

    first = _run(tmp_path, _loader(stale), write=True)
    assert (first.status, first.exit_code, http.sent) == ("stale", 3, [])
    assert not RunLog("demo", tmp_path).is_done(FRIDAY)

    final = _run(tmp_path, _loader(stale), write=True, final=True)
    again = _run(tmp_path, _loader(stale), write=True, final=True)
    assert final.status == again.status == "stale"
    text = json.loads(http.sent[0]["body"])["content"]["text"]
    assert len(http.sent) == 1 and text.startswith("QuantSpace 告警 | demo")
    assert "最新权重日期 2026-11-19" in text
    assert [item.ok for item in final.alerts] == [True] and again.alerts == []


def test_sent_day_is_not_loaded_again(tmp_path, http):
    calls = []
    frame = _weights(("2026-11-19", {"510300.SH": 1.0}), ("2026-11-20", {"518880.SH": 1.0}))

    sent = _run(tmp_path, _loader(frame, calls), write=True)
    repeat = _run(tmp_path, _loader(frame, calls), write=True)

    assert sent.status == "sent" and len(http.sent) == 1
    assert (repeat.status, repeat.detail, len(calls)) == ("done", "sent", 1)
    runs = json.loads(RunLog("demo", tmp_path).path.read_text(encoding="utf-8"))
    assert runs["runs"]["2026-11-20"]["signal_id"] == sent.delivery.signal.signal_id


def test_unchanged_target_finishes_the_day_silently(tmp_path, http):
    _run(
        tmp_path,
        _loader(_weights(("2026-11-19", {"510300.SH": 1.0}))),
        day=date(2026, 11, 19),
        write=True,
    )
    outcome = _run(
        tmp_path,
        _loader(_weights(("2026-11-19", {"510300.SH": 1.0}), ("2026-11-20", {"510300.SH": 1.0}))),
        write=True,
        final=True,
    )

    assert outcome.status == "unchanged" and len(http.sent) == 1
    assert RunLog("demo", tmp_path).is_done(FRIDAY)


def test_load_error_is_logged_and_alerted_once(tmp_path, http):
    def broken() -> LiveInputs:
        raise RuntimeError("PandaData timeout")

    first = _run(tmp_path, broken, write=True)
    second = _run(tmp_path, broken, write=True)

    assert (first.status, first.exit_code) == ("error", 1)
    assert "PandaData timeout" in first.detail and second.status == "error"
    assert len(http.sent) == 1 and "PandaData timeout" in http.sent[0]["body"]
    assert RunLog("demo", tmp_path).get(FRIDAY)["attempts"] == 2


def test_weights_after_the_trade_date_are_an_error(tmp_path, http):
    outcome = _run(tmp_path, _loader(_weights(("2026-11-23", {"510300.SH": 1.0}))))

    assert outcome.status == "error" and "after the trade date" in outcome.detail


def test_partial_delivery_retries_only_the_failed_channel(tmp_path, http):
    frame = _weights(("2026-11-20", {"510300.SH": 1.0}))
    http.failing.add("qyapi.weixin.qq.com")

    partial = _run(tmp_path, _loader(frame), write=True, urls=[FEISHU, WECOM])
    assert (partial.status, partial.exit_code) == ("partial", 4)
    assert not RunLog("demo", tmp_path).is_done(FRIDAY)

    http.failing.clear()
    retry = _run(tmp_path, _loader(frame), write=True, urls=[FEISHU, WECOM])
    assert retry.status == "sent"
    assert [item["host"] for item in http.sent] == [
        "open.feishu.cn",
        "qyapi.weixin.qq.com",
        "qyapi.weixin.qq.com",
    ]


def test_preview_writes_no_state(tmp_path, http):
    outcome = _run(tmp_path, _loader(_weights(("2026-11-20", {"510300.SH": 1.0}))))

    assert outcome.status == "preview" and http.sent == []
    assert not RunLog("demo", tmp_path).path.exists()


def test_write_without_channels_is_an_error(tmp_path):
    outcome = _run(
        tmp_path, _loader(_weights(("2026-11-20", {"510300.SH": 1.0}))), write=True, urls=[]
    )

    assert outcome.status == "error" and "No IM webhook" in outcome.detail


@pytest.mark.parametrize("status", ["sent", "unchanged", "already_sent", "not_trading_day"])
def test_done_statuses(tmp_path, status):
    log = RunLog("demo", tmp_path)
    log.record(FRIDAY, status)
    assert log.is_done(FRIDAY)


def _text(item) -> str:
    return json.loads(item["body"])["content"]["text"]


def test_test_mode_sends_a_marked_full_target_on_a_closed_day(tmp_path, http):
    frame = _weights(("2026-11-19", {"510300.SH": 1.0}), ("2026-11-20", {"518880.SH": 1.0}))
    saturday = date(2026, 11, 21)

    first = _run(tmp_path, _loader(frame), day=saturday, trading=False, write=True, test=True)
    second = _run(tmp_path, _loader(frame), day=saturday, trading=False, write=True, test=True)

    assert first.status == second.status == "test_sent" and first.exit_code == 0
    assert len(http.sent) == 2
    text = _text(http.sent[0])
    assert text.startswith("QuantSpace 调仓信号（测试） | demo")
    assert "测试消息：按 2026-11-20 的数据生成的完整目标" in text
    assert "518880.SH：0.00% → 100.00%" in text
    # Live state is untouched: the next real run still diffs against an empty ledger.
    assert not (tmp_path / "live").exists()


def test_test_mode_uses_the_row_at_or_before_the_date(tmp_path, http):
    frame = _weights(("2026-11-19", {"510300.SH": 1.0}), ("2026-11-20", {"518880.SH": 1.0}))

    outcome = _run(tmp_path, _loader(frame), day=date(2026, 11, 19), write=True, test=True)

    assert outcome.delivery.signal.target == {"510300.SH": 1.0}


def test_test_mode_previews_without_write_and_reports_failures(tmp_path, http):
    frame = _weights(("2026-11-20", {"510300.SH": 1.0}))

    preview = _run(tmp_path, _loader(frame), test=True)
    assert (preview.status, http.sent) == ("preview", [])

    http.rejecting.add("open.feishu.cn")
    failed = _run(tmp_path, _loader(frame), write=True, test=True)
    assert (failed.status, failed.exit_code, failed.alerts) == ("test_failed", 4, [])


def test_run_log_keys_bars_by_end_time_and_groups_them_by_trade_date(tmp_path):
    from datetime import datetime

    log = RunLog("demo", tmp_path)
    night, day = datetime(2026, 11, 20, 21, 5), datetime(2026, 11, 23, 9, 5)
    log.record(night, "sent", target={"RB.SHF": 1.0}, trade_date=date(2026, 11, 23))
    log.record(day, "stale", trade_date=date(2026, 11, 23))
    log.record(FRIDAY, "sent")

    assert log.is_done(night) and not log.is_done(day) and log.is_done(FRIDAY)
    assert sorted(log.bars(date(2026, 11, 23))) == ["2026-11-20T21:05:00", "2026-11-23T09:05:00"]
    assert log.get(night)["target"] == {"RB.SHF": 1.0}
    assert log.claim_alert(date(2026, 11, 23), "missed")
    assert not log.claim_alert(date(2026, 11, 23), "missed")
    assert log.bars(FRIDAY) == {}


def test_run_log_keeps_only_the_most_recent_days(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    from skills.live_trade import runner

    monkeypatch.setattr(runner, "MAX_RUN_DAYS", 2)
    log = RunLog("demo", tmp_path)
    for offset in range(3):
        moment = datetime(2026, 11, 18, 9, 35) + timedelta(days=offset)
        log.record(moment, "sent", trade_date=moment.date())
        log.record(moment + timedelta(minutes=5), "sent", trade_date=moment.date())

    kept = json.loads(log.path.read_text())["runs"]
    assert sorted(key[:10] for key in kept) == ["2026-11-19"] * 2 + ["2026-11-20"] * 2
