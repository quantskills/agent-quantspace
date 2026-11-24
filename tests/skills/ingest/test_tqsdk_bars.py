"""Intraday futures bars built from TqSdk ticks with PandaData's minute boundaries."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from skills.ingest.akshare_bars import COLUMNS
from skills.ingest.tqsdk_bars import (
    SOURCE_KLINE,
    SOURCE_TICK,
    TqCredentialsMissing,
    aggregate,
    fetch_tq_bars,
    minute_bars,
    tick_minutes,
    tq_code,
)


def _ns(moment: datetime) -> int:
    return pd.Timestamp(moment, tz="Asia/Shanghai").value


class FakeTq:
    """TqSdk's API: tick serials ``(time, price, day volume)`` and 1-minute K lines.

    Built with PandaData codes and asked with TqSdk's, as the real one is. Like TqSdk, the
    tick serial is padded with empty rows, volume and amount are running totals of the
    trading day, and a K line is stamped with its start.
    """

    def __init__(self, ticks=None, klines=None, failing=()):
        self.ticks = {tq_code(code): rows for code, rows in (ticks or {}).items()}
        self.klines = {tq_code(code): rows for code, rows in (klines or {}).items()}
        self.failing = {tq_code(code) for code in failing}
        self.calls, self.closed = [], False

    def get_tick_serial(self, code, data_length):
        self.calls.append(("ticks", code, data_length))
        if code in self.failing:
            raise RuntimeError(f"no such contract {code}")
        rows = self.ticks.get(code, [])
        frame = pd.DataFrame(
            {
                "datetime": [_ns(t) for t, _, _ in rows],
                "last_price": [price for _, price, _ in rows],
                "volume": [volume for _, _, volume in rows],
                "amount": [volume * 30000.0 for _, _, volume in rows],
                "open_interest": [1000.0 + i for i in range(len(rows))],
            }
        )
        padding = pd.DataFrame({"datetime": [float("nan")], "last_price": [float("nan")]})
        return pd.concat([padding, frame], ignore_index=True)

    def get_kline_serial(self, code, duration, data_length):
        self.calls.append(("klines", code, duration, data_length))
        rows = self.klines.get(code, [])
        return pd.DataFrame(
            {
                "datetime": [_ns(start) for start, *_ in rows],
                "open": [row[1] for row in rows],
                "high": [row[2] for row in rows],
                "low": [row[3] for row in rows],
                "close": [row[4] for row in rows],
                "volume": [row[5] for row in rows],
                "close_oi": [900.0] * len(rows),
            }
        )

    def close(self):
        self.closed = True


def at(hour, minute, second=0.0, day=24):
    whole = int(second)
    return datetime(2026, 11, day, hour, minute, whole, int(round((second - whole) * 1e6)))


# The afternoon of 2026-11-24 around 14:04, as TqSdk sent it.
AFTERNOON = [
    (at(14, 2, 58.0), 3019.0, 712000.0),
    (at(14, 3, 30.0), 3020.0, 713000.0),
    (at(14, 3, 59.5), 3021.0, 713757.0),
    (at(14, 4, 0.0), 3020.0, 714082.0),  # stamped exactly 14:04: the next bar's
    (at(14, 4, 0.5), 3021.0, 714090.0),
    (at(14, 4, 59.5), 3022.0, 715000.0),
    (at(14, 5, 0.5), 3023.0, 715010.0),
]


def _ticks(rows):
    return FakeTq({"RB2701.SHF": rows}).get_tick_serial(tq_code("RB2701.SHF"), 10)


def test_codes_follow_tqsdk_per_exchange():
    assert tq_code("RB2701.SHF") == "SHFE.rb2701"
    assert tq_code("m2701.DCE") == "DCE.m2701"
    assert tq_code("CF2701.CZC") == "CZCE.CF701"
    assert tq_code("CF701.CZC") == "CZCE.CF701"
    assert tq_code("IF2612.CFE") == "CFFEX.IF2612"
    assert tq_code("sc2701.INE") == "INE.sc2701"
    assert tq_code("si2701.GFE") == "GFEX.si2701"
    with pytest.raises(ValueError, match="continuous"):
        tq_code("RB_DOMINANT.SHF")
    with pytest.raises(ValueError, match="futures code"):
        tq_code("000001.SZ")


def test_the_tick_on_the_minute_belongs_to_the_next_bar():
    minutes, first, last = tick_minutes(_ticks(AFTERNOON))

    # 14:03 starts before the first tick, so only 14:04 and later are whole minutes.
    assert list(minutes["eob"]) == [at(14, 4), at(14, 5), at(14, 6)]
    bar = minutes.set_index("eob").loc[pd.Timestamp(at(14, 4))]
    assert (bar["open"], bar["high"], bar["low"], bar["close"]) == (3020.0, 3021.0, 3020.0, 3021.0)
    assert bar["volume"] == 713757.0 - 712000.0
    nxt = minutes.set_index("eob").loc[pd.Timestamp(at(14, 5))]
    assert (nxt["open"], nxt["close"], nxt["volume"]) == (3020.0, 3022.0, 715000.0 - 713757.0)
    assert (first, last) == (pd.Timestamp(at(14, 2, 58.0)), pd.Timestamp(at(14, 5, 0.5)))


def test_a_trading_day_starts_from_zero_with_its_opening_auction():
    rows = [
        (at(14, 59, 59.5, day=23), 3000.0, 890000.0),  # the day before
        (at(20, 59, 0.5, day=23), 3004.0, 2619.0),  # the night's opening auction
        (at(21, 0, 1.0, day=23), 3004.0, 2937.0),
        (at(21, 0, 59.5, day=23), 3009.0, 18625.0),
        (at(21, 1, 30.0, day=23), 3001.0, 20000.0),
        (at(21, 2, 0.5, day=23), 3001.0, 20100.0),
    ]
    minutes, finished = minute_bars(_ticks(rows), None, at(21, 2, 1.0, day=23))
    schedule = [at(21, 1, day=23), at(21, 2, day=23), at(21, 3, day=23)]

    bars = aggregate(minutes, "1m", finished, schedule).set_index("eob")

    # PandaData's 21:01 bar of 2026-11-24's trading day: 18625 contracts, auction included.
    assert list(bars.index) == [pd.Timestamp(t) for t in schedule[:2]]
    first = bars.loc[pd.Timestamp(at(21, 1, day=23))]
    assert (first["open"], first["close"], first["volume"]) == (3004.0, 3009.0, 18625.0)
    assert bars.loc[pd.Timestamp(at(21, 2, day=23)), "volume"] == 20000.0 - 18625.0
    assert set(bars["source"]) == {SOURCE_TICK}


def test_a_bar_is_finished_by_the_next_tick_or_a_few_seconds():
    rows = [(at(21, 3, 0.0), 3000.0, 100.0), (at(21, 4, 58.0), 3001.0, 200.0)]
    schedule = [at(21, 5), at(21, 10)]

    def bars(now, extra=()):
        minutes, finished = minute_bars(_ticks([*rows, *extra]), None, now)
        return list(aggregate(minutes, "5m", finished, schedule)["eob"])

    assert bars(at(21, 5, 1.0)) == []
    assert bars(at(21, 5, 3.0)) == [pd.Timestamp(at(21, 5))]
    assert bars(at(21, 5, 1.0), [(at(21, 5, 0.5), 3002.0, 210.0)]) == [pd.Timestamp(at(21, 5))]


def test_klines_fill_the_minutes_before_the_ticks():
    klines = [
        (at(14, 1), 3015.0, 3018.0, 3014.0, 3017.0, 400.0),  # ends 14:02
        (at(14, 2), 3017.0, 3019.0, 3016.0, 3018.0, 500.0),  # ends 14:03, ticks start inside
        (at(14, 3), 3018.0, 3021.0, 3018.0, 3020.0, 600.0),  # ticks cover it: not used
    ]
    raw = FakeTq(klines={"RB2701.SHF": klines}).get_kline_serial(tq_code("RB2701.SHF"), 60, 3)

    minutes, finished = minute_bars(_ticks(AFTERNOON), raw, at(14, 6, 5.0))

    by_end = minutes.set_index("eob")["source"].to_dict()
    assert by_end == {
        pd.Timestamp(at(14, 2)): SOURCE_KLINE,
        pd.Timestamp(at(14, 3)): SOURCE_KLINE,
        pd.Timestamp(at(14, 4)): SOURCE_TICK,
        pd.Timestamp(at(14, 5)): SOURCE_TICK,
        pd.Timestamp(at(14, 6)): SOURCE_TICK,
    }
    # A five-minute bar with any K-line minute is marked as such.
    five = aggregate(minutes, "5m", finished).set_index("eob")
    assert five.loc[pd.Timestamp(at(14, 5)), "source"] == SOURCE_KLINE
    assert five.loc[pd.Timestamp(at(14, 5)), "volume"] == 400 + 500 + 1757 + 1243


def test_a_schedule_bar_after_a_break_starts_after_the_previous_bar():
    rows = [
        (at(10, 14, 59.5), 3000.0, 100.0),
        (at(10, 30, 0.5), 3005.0, 150.0),
        (at(10, 34, 59.5), 3006.0, 180.0),
        (at(10, 35, 0.5), 3007.0, 190.0),
    ]
    minutes, finished = minute_bars(_ticks(rows), None, at(10, 35, 1.0))

    bars = aggregate(minutes, "5m", finished, [at(10, 15), at(10, 35), at(10, 40)])

    (bar,) = bars.itertuples()
    assert (bar.eob, bar.open, bar.close, bar.volume) == (
        pd.Timestamp(at(10, 35)),
        3005.0,
        3006.0,
        80.0,
    )


def test_fetch_reports_failures_per_contract_and_logs_out():
    tq = FakeTq({"RB2701.SHF": AFTERNOON}, failing={"HC2701.SHF"})

    result = fetch_tq_bars(
        ["RB2701.SHF", "HC2701.SHF", "RB_DOMINANT.SHF"],
        "1m",
        now=at(14, 6, 5.0),
        connector=lambda: tq,
    )

    assert list(result.bars.columns) == COLUMNS
    assert set(result.bars["symbol"]) == {"RB2701.SHF"} and len(result.bars) == 3
    assert set(result.errors) == {"HC2701.SHF", "RB_DOMINANT.SHF"}
    assert "no such contract" in result.errors["HC2701.SHF"]
    assert result.codes["RB2701.SHF"] == "SHFE.rb2701" and tq.closed
    assert result.as_of == at(14, 6, 5.0)


def test_a_failed_login_is_reported_for_every_contract_and_missing_setup_raises():
    def refuse():
        raise ConnectionError("auth failed")

    result = fetch_tq_bars(["RB2701.SHF", "HC2701.SHF"], "5m", now=at(14, 6), connector=refuse)
    assert result.bars.empty and set(result.errors) == {"RB2701.SHF", "HC2701.SHF"}
    assert "TqSdk login failed" in result.errors["RB2701.SHF"]

    def unset():
        raise TqCredentialsMissing("TQ_USERNAME and TQ_PASSWORD are not set")

    with pytest.raises(TqCredentialsMissing):
        fetch_tq_bars(["RB2701.SHF"], "5m", now=at(14, 6), connector=unset)
    with pytest.raises(ValueError, match="frequency"):
        fetch_tq_bars(["RB2701.SHF"], "2m", now=at(14, 6), connector=lambda: FakeTq())
