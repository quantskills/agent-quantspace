"""Trading sessions, bar end times, and when a bar is due."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import pytest
from pydantic import ValidationError

from skills.live_trade.clock import (
    EQUITY_SESSIONS,
    Session,
    TradingCalendar,
    bar_ends,
    bars_per_day,
    due_bars,
    has_night_session,
    parse_trading_hours,
)
from skills.live_trade.spec import Instrument, LiveSpec

RB_HOURS = "21:01-23:00,09:01-10:15,10:31-11:30,13:31-15:00"
# 2026-10-01..10-08 is the National Day holiday in this calendar.
HOLIDAY = {date(2026, 10, day) for day in range(1, 9)}
CALENDAR = TradingCalendar.from_days(
    day.date() for day in pd.bdate_range("2026-08-03", "2026-12-31") if day.date() not in HOLIDAY
)


def test_trading_hours_start_one_minute_before_the_first_bar_end():
    sessions = parse_trading_hours(RB_HOURS)
    assert [item.label() for item in sessions] == [
        "21:00-23:00",
        "09:00-10:15",
        "10:30-11:30",
        "13:30-15:00",
    ]
    assert [item.night for item in sessions] == [True, False, False, False]
    assert bars_per_day("5m", sessions) == 69


def test_sessions_that_cross_midnight_keep_their_length():
    night = parse_trading_hours("21:01-02:30,09:01-10:15")[0]
    assert (night.start, night.end, night.minutes) == (time(21, 0), time(2, 30), 330)
    assert parse_trading_hours("21:01-24:00")[0].end == time(0, 0)


@pytest.mark.parametrize("text", ["", "21:01", "9:01-10:15x"])
def test_bad_trading_hours_are_refused(text):
    with pytest.raises(ValueError):
        parse_trading_hours(text)


def test_calendar_lookups_refuse_days_outside_the_range():
    friday, monday = date(2026, 11, 20), date(2026, 11, 23)
    assert CALENDAR.next(friday) == monday and CALENDAR.previous(monday) == friday
    assert CALENDAR.shift(monday, -2) == date(2026, 11, 19)
    assert not CALENDAR.is_trading_day(date(2026, 11, 21))
    with pytest.raises(ValueError, match="outside"):
        CALENDAR.is_trading_day(date(2027, 1, 4))


def test_night_sessions_follow_weekdays_and_weekends_but_not_holidays():
    assert has_night_session(date(2026, 11, 23), CALENDAR)  # Friday night -> Monday
    assert has_night_session(date(2026, 11, 24), CALENDAR)
    assert not has_night_session(date(2026, 10, 9), CALENDAR)  # first day after the holiday


def test_rebar_five_minute_bars_start_on_the_previous_evening():
    ends = bar_ends(date(2026, 11, 23), "5m", parse_trading_hours(RB_HOURS), CALENDAR)
    assert len(ends) == 69
    assert ends[0] == datetime(2026, 11, 20, 21, 5) and ends[23] == datetime(2026, 11, 20, 23, 0)
    assert ends[24] == datetime(2026, 11, 23, 9, 5) and ends[-1] == datetime(2026, 11, 23, 15, 0)
    # Bars restart after the 10:15-10:30 break.
    assert datetime(2026, 11, 23, 10, 35) in ends and datetime(2026, 11, 23, 10, 20) not in ends


def test_no_night_bars_after_a_holiday_and_none_on_closed_days():
    ends = bar_ends(date(2026, 10, 9), "5m", parse_trading_hours(RB_HOURS), CALENDAR)
    assert len(ends) == 45 and ends[0] == datetime(2026, 10, 9, 9, 5)
    assert bar_ends(date(2026, 11, 21), "5m", EQUITY_SESSIONS, CALENDAR) == []


def test_after_midnight_bars_fall_on_the_next_calendar_day():
    sessions = parse_trading_hours("21:01-02:30,09:01-10:15,10:31-11:30,13:31-15:00")
    ends = bar_ends(date(2026, 11, 23), "15m", sessions, CALENDAR)
    night = [item for item in ends if item < datetime(2026, 11, 23)]
    assert night[0] == datetime(2026, 11, 20, 21, 15)
    assert night[-1] == datetime(2026, 11, 21, 2, 30)  # Saturday morning of Monday's day
    assert len(night) == 22


def test_equity_bars_and_sessions_that_do_not_split_evenly():
    ends = bar_ends(date(2026, 11, 23), "30m", EQUITY_SESSIONS, CALENDAR)
    assert ends[0] == datetime(2026, 11, 23, 10, 0) and ends[3] == datetime(2026, 11, 23, 11, 30)
    assert ends[4] == datetime(2026, 11, 23, 13, 30) and len(ends) == 8
    with pytest.raises(ValueError, match="whole number"):
        bar_ends(date(2026, 11, 23), "30m", parse_trading_hours(RB_HOURS), CALENDAR)
    with pytest.raises(ValueError, match="frequency"):
        bar_ends(date(2026, 11, 23), "1d", EQUITY_SESSIONS, CALENDAR)


def test_bars_are_due_after_the_delay_and_missed_at_the_deadline():
    day = date(2026, 11, 23)
    schedule = [(day, datetime(2026, 11, 23, 9, 35) + timedelta(minutes=5 * k)) for k in range(3)]
    now = datetime(2026, 11, 23, 9, 40, 25)
    due = due_bars(now, schedule, delay_seconds=20, deadline_seconds=300)
    assert [item.eob.minute for item in due] == [35, 40]
    assert [item.missed(now) for item in due] == [True, False]
    assert due[1].ready_at == datetime(2026, 11, 23, 9, 40, 20)
    with pytest.raises(ValueError):
        due_bars(now, schedule, delay_seconds=300, deadline_seconds=300)


def test_session_label_and_night_flag():
    assert Session(time(0, 0), time(2, 30)).night
    assert not Session(time(9, 30), time(11, 30)).night


def test_instruments_must_match_their_code_type():
    assert Instrument(symbol="RB_DOMINANT.SHF", asset="future").continuous
    assert not Instrument(symbol="RB2701.SHF", asset="future").continuous
    with pytest.raises(ValidationError):
        Instrument(symbol="RB2701.SHF", asset="stock")
    with pytest.raises(ValidationError):
        Instrument(symbol="510300.SH", asset="future")


def _spec(*instruments, **options) -> LiveSpec:
    return LiveSpec(
        strategy_id=options.pop("strategy_id", "demo"),
        frequency=options.pop("frequency", "5m"),
        instruments=instruments,
        warmup_bars=options.pop("warmup_bars", 10),
        **options,
    )


def test_spec_defaults_and_checks():
    spec = _spec(Instrument(symbol="510300.SH", asset="fund"))
    assert (spec.deadline, spec.adjust, spec.futures, spec.symbols) == (
        300,
        "post",
        False,
        ["510300.SH"],
    )
    assert (
        _spec(Instrument(symbol="RB2701.SHF", asset="future"), deadline_seconds=90).deadline == 90
    )
    with pytest.raises(ValidationError, match="either futures"):
        _spec(
            Instrument(symbol="510300.SH", asset="fund"),
            Instrument(symbol="RB2701.SHF", asset="future"),
        )
    with pytest.raises(ValidationError, match="once"):
        _spec(
            Instrument(symbol="510300.SH", asset="fund"),
            Instrument(symbol="510300.SH", asset="fund"),
        )
    with pytest.raises(ValidationError, match="greater"):
        _spec(Instrument(symbol="510300.SH", asset="fund"), frequency="1m", bar_delay_seconds=60)
    with pytest.raises(ValidationError):
        _spec(Instrument(symbol="510300.SH", asset="fund"), strategy_id="../x")
