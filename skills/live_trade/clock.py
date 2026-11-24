"""Trading sessions and bar end times for minute-level live runs.

A trading day's bars are labelled by their end time, like PandaData and Sina. A futures
night session belongs to the next trading day: the session that opens at 21:00 on Friday
is the first part of Monday's trading day. Night sessions are dropped before a holiday
(any gap between trading days other than a plain weekday or a weekend), as exchanges do.

Sessions come from PandaData's ``get_future_detail`` ``trading_hours`` for futures, written
with bar end times (``21:01-23:00,09:01-10:15,10:31-11:30,13:31-15:00``); A-shares and
listed funds trade 09:30-11:30 and 13:00-15:00.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

INTRADAY_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}
# Sessions that start at or after this hour, or before NIGHT_END_HOUR, are night sessions.
NIGHT_START_HOUR = 18
NIGHT_END_HOUR = 6


@dataclass(frozen=True)
class Session:
    """One continuous trading session; ``end`` before ``start`` crosses midnight."""

    start: time
    end: time

    @property
    def night(self) -> bool:
        return self.start.hour >= NIGHT_START_HOUR or self.start.hour < NIGHT_END_HOUR

    @property
    def minutes(self) -> int:
        start = self.start.hour * 60 + self.start.minute
        end = self.end.hour * 60 + self.end.minute
        return (end - start) % (24 * 60)

    def label(self) -> str:
        return f"{self.start:%H:%M}-{self.end:%H:%M}"


EQUITY_SESSIONS = (Session(time(9, 30), time(11, 30)), Session(time(13, 0), time(15, 0)))


def _clock(text: str) -> time:
    hour, minute = (int(part) for part in text.strip().split(":"))
    if hour == 24 and minute == 0:
        return time(0, 0)
    return time(hour, minute)


def parse_trading_hours(text: str) -> tuple[Session, ...]:
    """Sessions from PandaData's ``trading_hours``, whose ranges start at the first bar's end.

    ``21:01-23:00`` is the session 21:00-23:00. Ranges that cross midnight, such as
    ``21:01-02:30``, become one session whose end is before its start.
    """
    sessions = []
    for part in str(text).split(","):
        if not part.strip():
            continue
        first, _, last = part.partition("-")
        if not last:
            raise ValueError(f"trading_hours entry {part!r} is not HH:MM-HH:MM")
        first_end = datetime.combine(date(2000, 1, 2), _clock(first))
        start = (first_end - timedelta(minutes=1)).time()
        sessions.append(Session(start, _clock(last)))
    if not sessions:
        raise ValueError("trading_hours is empty")
    return tuple(sessions)


@dataclass(frozen=True)
class TradingCalendar:
    """Sorted trading days; lookups outside the covered range raise instead of guessing."""

    days: tuple[date, ...]

    @classmethod
    def from_days(cls, days: Iterable[date]) -> TradingCalendar:
        ordered = tuple(sorted(set(days)))
        if not ordered:
            raise ValueError("the trading calendar is empty")
        return cls(ordered)

    def _check(self, day: date) -> None:
        if not self.days[0] <= day <= self.days[-1]:
            raise ValueError(
                f"{day} is outside the trading calendar {self.days[0]}..{self.days[-1]}"
            )

    def is_trading_day(self, day: date) -> bool:
        self._check(day)
        index = bisect.bisect_left(self.days, day)
        return index < len(self.days) and self.days[index] == day

    def previous(self, day: date) -> date:
        """The last trading day strictly before ``day``."""
        self._check(day)
        index = bisect.bisect_left(self.days, day)
        if index == 0:
            raise ValueError(f"no trading day before {day} in the calendar")
        return self.days[index - 1]

    def next(self, day: date) -> date:
        """The first trading day strictly after ``day``."""
        self._check(day)
        index = bisect.bisect_right(self.days, day)
        if index >= len(self.days):
            raise ValueError(f"no trading day after {day} in the calendar")
        return self.days[index]

    def shift(self, day: date, count: int) -> date:
        """The trading day ``count`` trading days before (negative) or after ``day``."""
        current = day
        for _ in range(abs(count)):
            current = self.next(current) if count > 0 else self.previous(current)
        return current


def has_night_session(trading_date: date, calendar: TradingCalendar) -> bool:
    """Whether the night before ``trading_date`` trades: only after a weekday or a weekend."""
    previous = calendar.previous(trading_date)
    gap = (trading_date - previous).days
    return gap == 1 or (gap == 3 and previous.weekday() == 4)


def bar_ends(
    trading_date: date,
    frequency: str,
    sessions: Sequence[Session],
    calendar: TradingCalendar,
) -> list[datetime]:
    """End times of every bar of ``trading_date``, oldest first, as naive Shanghai times.

    Bars are counted from each session's start, so a 5-minute bar after a 10:15-10:30 break
    ends at 10:35. A session whose length is not a whole number of bars is refused instead
    of guessing how the provider splits it.
    """
    if frequency not in INTRADAY_MINUTES:
        raise ValueError(f"frequency must be one of {sorted(INTRADAY_MINUTES)}")
    if not calendar.is_trading_day(trading_date):
        return []
    step = INTRADAY_MINUTES[frequency]
    night = has_night_session(trading_date, calendar)
    evening = calendar.previous(trading_date) if night else None
    ends = []
    for session in sessions:
        if session.minutes % step:
            raise ValueError(
                f"session {session.label()} is {session.minutes} minutes, not a whole number "
                f"of {frequency} bars"
            )
        if session.night:
            if not night:
                continue
            day = evening if session.start.hour >= NIGHT_START_HOUR else evening + timedelta(1)
        else:
            day = trading_date
        start = datetime.combine(day, session.start)
        ends.extend(
            start + timedelta(minutes=step * k) for k in range(1, session.minutes // step + 1)
        )
    return sorted(ends)


def bars_per_day(frequency: str, sessions: Sequence[Session]) -> int:
    """Bars of a full trading day, night session included."""
    step = INTRADAY_MINUTES[frequency]
    return sum(session.minutes // step for session in sessions)


def trading_windows(ends: Sequence[datetime], frequency: str) -> list[tuple[datetime, datetime]]:
    """The continuous-trading windows ``(start, end)`` that a day's bar ends cover.

    Bars one interval apart share a window; a break or the gap between sessions starts
    a new one (rebar's day: 21:00-23:00, 09:00-10:15, 10:30-11:30, 13:30-15:00).
    """
    step = timedelta(minutes=INTRADAY_MINUTES[frequency])
    windows: list[tuple[datetime, datetime]] = []
    for end in sorted(ends):
        if windows and end - windows[-1][1] == step:
            windows[-1] = (windows[-1][0], end)
        else:
            windows.append((end - step, end))
    return windows


def in_session(moment: datetime, ends: Sequence[datetime], frequency: str) -> bool:
    """Whether ``moment`` is inside one of the day's continuous-trading windows."""
    return any(start <= moment < end for start, end in trading_windows(ends, frequency))


@dataclass(frozen=True)
class DueBar:
    """The newest bar whose results should be available at ``now``."""

    eob: datetime
    trading_date: date
    ready_at: datetime
    deadline: datetime

    def missed(self, now: datetime) -> bool:
        return now >= self.deadline


def due_bars(
    now: datetime,
    schedule: Sequence[tuple[date, datetime]],
    *,
    delay_seconds: int,
    deadline_seconds: int,
) -> list[DueBar]:
    """Bars of ``schedule`` (``(trading_date, eob)`` pairs) that are ready at ``now``.

    A bar is ready ``delay_seconds`` after it ends and stays usable until
    ``deadline_seconds`` after it ends; both kinds are returned, oldest first.
    """
    if deadline_seconds <= delay_seconds:
        raise ValueError("deadline_seconds must be greater than delay_seconds")
    ready = []
    for trading_date, eob in schedule:
        ready_at = eob + timedelta(seconds=delay_seconds)
        if ready_at <= now:
            ready.append(
                DueBar(eob, trading_date, ready_at, eob + timedelta(seconds=deadline_seconds))
            )
    return ready


__all__ = [
    "EQUITY_SESSIONS",
    "INTRADAY_MINUTES",
    "DueBar",
    "Session",
    "TradingCalendar",
    "bar_ends",
    "bars_per_day",
    "due_bars",
    "has_night_session",
    "in_session",
    "parse_trading_hours",
    "trading_windows",
]
