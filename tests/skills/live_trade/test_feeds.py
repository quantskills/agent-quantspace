"""MinuteFeed: the pre-open refresh from PandaData and today's bars from AKShare (Sina)."""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import pytest

from skills.live_trade.feeds import (
    PANDADATA,
    FeedNotReady,
    MinuteFeed,
    read_feed_state,
    upcoming_trading_date,
)

from .fakes import (
    CALENDAR,
    EQUITY_SPEC,
    FRIDAY,
    MONDAY,
    RB_SPEC,
    TUESDAY,
    FakePandaData,
    FakeSina,
)


def _feed(tmp_path, spec=RB_SPEC, client=None, sina=None) -> MinuteFeed:
    return MinuteFeed(
        spec, client or FakePandaData(), data_root=tmp_path, akshare=sina or FakeSina(), pause=0
    )


def _stored(feed: MinuteFeed, symbol: str) -> pd.DataFrame:
    return pd.read_parquet(feed.root / "market" / feed.spec.frequency / f"{symbol}.parquet")


def test_upcoming_trading_date_switches_after_the_day_session():
    assert upcoming_trading_date(datetime(2026, 11, 20, 8, 30), CALENDAR) == FRIDAY
    assert upcoming_trading_date(datetime(2026, 11, 20, 18, 0), CALENDAR) == MONDAY
    assert upcoming_trading_date(datetime(2026, 11, 22, 12, 0), CALENDAR) == MONDAY


def test_futures_refresh_prepares_the_next_trading_day(tmp_path):
    feed = _feed(tmp_path)
    report = feed.refresh(MONDAY, now=datetime(2026, 11, 20, 18, 0))
    state = report.state

    assert state.contracts == {"RB_DOMINANT.SHF": "RB2701.SHF"}
    assert state.multipliers == {"RB_DOMINANT.SHF": 10.0}
    assert (state.trading_date, state.history_end) == ("2026-11-23", "2026-11-20")
    assert state.sessions == ["21:00-23:00", "09:00-10:15", "10:30-11:30", "13:30-15:00"]
    assert len(state.bar_ends) == 69 and state.bar_ends[0] == "2026-11-20T21:05:00"
    # 48 warm-up bars fit in one day; plus two spare days and the day the bars come from.
    assert report.rows == {"RB_DOMINANT.SHF": 4 * 69} and state.keep_bars == 5 * 69
    assert read_feed_state("rb_demo", tmp_path) == state
    stored = _stored(feed, "RB_DOMINANT.SHF")
    assert set(stored["source"]) == {PANDADATA} and set(stored["contract"]) == {"RB2701.SHF"}
    assert stored.index.max() == pd.Timestamp("2026-11-20 15:00")
    assert stored["trading_date"].iloc[-1] == "2026-11-20"


def test_refresh_needs_a_dominant_contract_and_a_trading_day(tmp_path):
    client = FakePandaData()
    client.dominant = {}
    with pytest.raises(ValueError, match="no dominant contract of RB"):
        _feed(tmp_path, client=client).refresh(MONDAY)
    with pytest.raises(ValueError, match="not a trading day"):
        _feed(tmp_path).refresh(datetime(2026, 11, 21).date())


def test_update_keeps_only_finished_bars_of_the_trading_day(tmp_path):
    sina = FakeSina()
    sina.add(
        "RB2701",
        (datetime(2026, 11, 20, 15, 0), 2999.0),  # Friday's own trading day, from PandaData
        (datetime(2026, 11, 20, 21, 5), 3001.0),
        (datetime(2026, 11, 20, 21, 10), 3002.0),
        (datetime(2026, 11, 20, 21, 15), 3003.0),
        (datetime(2026, 11, 20, 21, 20), 3003.0),  # still forming at 21:15:25
    )
    feed = _feed(tmp_path, sina=sina)
    feed.refresh(MONDAY, now=datetime(2026, 11, 20, 18, 0))

    update = feed.update(datetime(2026, 11, 20, 21, 15, 25))

    assert update.added == {"RB_DOMINANT.SHF": 3} and update.errors == {}
    assert update.latest == {"RB_DOMINANT.SHF": "2026-11-20T21:15:00"}
    stored = _stored(feed, "RB_DOMINANT.SHF")
    night = stored.loc["2026-11-20 21:05":]
    assert list(night["close"]) == [3001.0, 3002.0, 3003.0]
    assert set(night["source"]) == {"akshare_sina"} and set(night["trading_date"]) == {"2026-11-23"}
    assert stored.loc[pd.Timestamp("2026-11-20 15:00"), "source"] == PANDADATA
    assert sina.calls == ["RB2701"]


def test_next_refresh_compares_then_replaces_the_akshare_bars(tmp_path):
    client, sina = FakePandaData(), FakeSina()
    sina.add(
        "RB2701",
        (datetime(2026, 11, 20, 21, 5), 3000.0),
        (datetime(2026, 11, 20, 21, 10), 3004.0),  # PandaData later says 3000
    )
    feed = _feed(tmp_path, client=client, sina=sina)
    feed.refresh(MONDAY, now=datetime(2026, 11, 20, 18, 0))
    feed.update(datetime(2026, 11, 20, 21, 10, 30))

    report = feed.refresh(TUESDAY, now=datetime(2026, 11, 23, 18, 0))

    (comparison,) = report.comparisons
    assert (comparison.trading_date, comparison.akshare_bars, comparison.compared) == (
        "2026-11-23",
        2,
        2,
    )
    assert (comparison.pandadata_bars, comparison.missing_in_akshare) == (69, 67)
    assert (comparison.close_differs, comparison.max_close_diff) == (1, 4.0)
    saved = json.loads((feed.root / "reconcile" / "2026-11-23.bars.json").read_text())
    assert saved["bars"][0]["close_differs"] == 1
    assert set(_stored(feed, "RB_DOMINANT.SHF")["source"]) == {PANDADATA}
    assert report.state.bar_ends[0] == "2026-11-23T21:05:00"


def test_equity_refresh_uses_backward_adjusted_history(tmp_path):
    feed = _feed(tmp_path, spec=EQUITY_SPEC)
    report = feed.refresh(FRIDAY, now=datetime(2026, 11, 20, 8, 30))
    state = report.state

    assert state.factors == {"601998.SH": 2.1, "510300.SH": 1.5}
    assert state.halted == {} and state.multipliers == {}
    assert state.sessions == ["09:30-11:30", "13:00-15:00"] and len(state.bar_ends) == 48
    stored = _stored(feed, "601998.SH")
    assert stored.loc["2026-11-18", "close"].iloc[0] == pytest.approx(20.0)  # before the ex-date
    assert stored.loc["2026-11-19", "close"].iloc[0] == pytest.approx(21.0)
    raw = feed.raw_closes()
    assert raw["601998.SH"].dropna().eq(10.0).all() and raw["510300.SH"].dropna().eq(10.0).all()


def test_unadjusted_equity_specs_keep_raw_prices(tmp_path):
    spec = EQUITY_SPEC.model_copy(update={"adjust": "none"})
    report = _feed(tmp_path, spec=spec).refresh(FRIDAY)
    assert report.state.factors == {"601998.SH": 1.0, "510300.SH": 1.0}


def test_ex_date_today_uses_the_published_factor_or_halts(tmp_path):
    client = FakePandaData()
    client.ex_dates["601998.SH"] = ["20261120"]
    halted = _feed(tmp_path, spec=EQUITY_SPEC, client=client).refresh(FRIDAY).state
    assert list(halted.halted) == ["601998.SH"] and "除权除息日" in halted.halted["601998.SH"]

    client.published["601998.SH"] = {"20261120": 2.2}
    ready = _feed(tmp_path, spec=EQUITY_SPEC, client=client).refresh(FRIDAY).state
    assert ready.halted == {} and ready.factors["601998.SH"] == 2.2


def test_equity_update_adjusts_today_with_the_known_factor(tmp_path):
    sina = FakeSina()
    sina.add("sh601998", (datetime(2026, 11, 20, 9, 35), 9.5), (datetime(2026, 11, 20, 9, 40), 9.6))
    sina.add("sh510300", (datetime(2026, 11, 20, 9, 35), 4.0))
    feed = _feed(tmp_path, spec=EQUITY_SPEC, sina=sina)
    feed.refresh(FRIDAY, now=datetime(2026, 11, 20, 8, 30))

    update = feed.update(datetime(2026, 11, 20, 9, 40, 30))

    assert update.latest == {"601998.SH": "2026-11-20T09:40:00", "510300.SH": "2026-11-20T09:35:00"}
    closes, raw = feed.closes(), feed.raw_closes()
    assert closes.loc["2026-11-20 09:40", "601998.SH"] == pytest.approx(9.6 * 2.1)
    assert raw.loc["2026-11-20 09:40", "601998.SH"] == pytest.approx(9.6)
    assert closes.loc["2026-11-20 09:35", "510300.SH"] == pytest.approx(6.0)


def test_update_reports_failures_per_symbol(tmp_path):
    sina = FakeSina()
    sina.failing.add("sh601998")
    sina.add("sh510300", (datetime(2026, 11, 20, 9, 35), 4.0))
    feed = _feed(tmp_path, spec=EQUITY_SPEC, sina=sina)
    feed.refresh(FRIDAY)

    update = feed.update(datetime(2026, 11, 20, 9, 35, 30))

    assert "Sina closed the connection" in update.errors["601998.SH"]
    assert update.latest["601998.SH"] == "2026-11-19T15:00:00"
    assert update.latest["510300.SH"] == "2026-11-20T09:35:00"


def test_feed_is_not_ready_without_a_refresh_for_the_day(tmp_path):
    feed = _feed(tmp_path)
    with pytest.raises(FeedNotReady):
        feed.state()
    feed.refresh(MONDAY, now=datetime(2026, 11, 20, 18, 0))
    with pytest.raises(FeedNotReady, match="refresh again"):
        feed.update(datetime(2026, 11, 24, 9, 5, 30))
    with pytest.raises(FeedNotReady, match="not for"):
        feed.update(datetime(2026, 11, 20, 12, 0))
