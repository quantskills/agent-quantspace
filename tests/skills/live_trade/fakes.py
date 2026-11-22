"""Offline stand-ins for PandaData and Sina (AKShare) used by the minute-level live tests.

The fake PandaData client answers the calls :class:`~skills.live_trade.feeds.MinuteFeed`
makes with tables shaped like the real ones; the fake AKShare module serves bars the test
puts in. Nothing reaches the network.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from skills.live_trade.clock import EQUITY_SESSIONS, TradingCalendar, bar_ends, parse_trading_hours
from skills.live_trade.spec import Instrument, LiveSpec

RB_HOURS = "21:01-23:00,09:01-10:15,10:31-11:30,13:31-15:00"
THURSDAY, FRIDAY = date(2026, 11, 19), date(2026, 11, 20)
MONDAY, TUESDAY = date(2026, 11, 23), date(2026, 11, 24)
DAYS = tuple(day.date() for day in pd.bdate_range("2025-09-01", "2026-12-31"))
CALENDAR = TradingCalendar.from_days(DAYS)

RB_SPEC = LiveSpec(
    strategy_id="rb_demo",
    frequency="5m",
    instruments=(Instrument(symbol="RB_DOMINANT.SHF", asset="future"),),
    warmup_bars=48,
    adjust="none",
)
EQUITY_SPEC = LiveSpec(
    strategy_id="eq_demo",
    frequency="5m",
    instruments=(
        Instrument(symbol="601998.SH", asset="stock"),
        Instrument(symbol="510300.SH", asset="fund"),
    ),
    warmup_bars=20,
)


def _stamp(day: date) -> str:
    return day.strftime("%Y%m%d")


def _days(start: str, end: str) -> list[date]:
    first, last = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    return [day for day in DAYS if first <= day <= last]


class FakePandaData:
    """Minute closes are ``base`` unless ``closes[(symbol, eob)]`` says otherwise.

    ``factors[symbol]`` maps a first day to the backward-adjustment factor from that day
    on; ``ex_dates`` lists announced ex-dates and ``published`` the cumulative factors
    PandaData has already released for them.
    """

    def __init__(self):
        self.dominant = {"RB": "RB2701.SHF"}
        self.closes: dict[tuple[str, datetime], float] = {}
        self.factors: dict[str, dict[date, float]] = {
            "601998.SH": {date(2025, 1, 1): 2.0, THURSDAY: 2.1},
            "510300.SH": {date(2025, 1, 1): 1.5},
        }
        self.ex_dates: dict[str, list[str]] = {}
        self.published: dict[str, dict[str, float]] = {}
        self.calls: list[tuple] = []

    # ---------------------------------------------------------------- reference data
    def get_trade_cal(self, start, end):
        self.calls.append(("calendar", start, end))
        days = pd.date_range(start, end)
        trading = set(DAYS)
        return pd.DataFrame(
            {
                "nature_date": [day.strftime("%Y%m%d") for day in days],
                "is_trade": [int(day.date() in trading) for day in days],
            }
        )

    def get_future_dominant(self, start, end, *, underlying_symbol=None):
        self.calls.append(("dominant", start, end, tuple(underlying_symbol or ())))
        rows = [
            {"underlying_symbol": product, "date": _stamp(day), "symbol": contract}
            for day in _days(start, end)
            for product, contract in self.dominant.items()
            if not underlying_symbol or product in underlying_symbol
        ]
        return pd.DataFrame(rows, columns=["underlying_symbol", "date", "symbol"])

    def get_future_detail(self, symbols, fields=None):
        return pd.DataFrame(
            {"symbol": list(symbols), "contract_multiplier": 10.0, "trading_hours": RB_HOURS}
        )

    # ---------------------------------------------------------------- prices
    def _factor(self, symbol: str, day: date) -> float:
        table = self.factors.get(symbol, {date(2000, 1, 1): 1.0})
        return table[max(start for start in table if start <= day)]

    def _base(self, symbol: str) -> float:
        return 3000.0 if symbol.endswith(".SHF") else 10.0

    def fetch_market_min_data(self, symbol, start, end, *, symbol_type, frequency):
        self.calls.append(("minute", symbol, start, end, symbol_type, frequency))
        sessions = parse_trading_hours(RB_HOURS) if symbol_type == "future" else EQUITY_SESSIONS
        rows = []
        for day in _days(start, end):
            for eob in bar_ends(day, frequency, sessions, CALENDAR):
                close = self.closes.get((symbol, eob), self._base(symbol))
                row = {
                    "symbol": symbol,
                    "date": _stamp(eob.date()),
                    "datetime": eob.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": close,
                    "high": close + 1,
                    "low": close - 1,
                    "close": close,
                    "volume": 100.0,
                }
                if symbol_type == "future":
                    contract = self.dominant["RB"].partition(".")[0]
                    row.update(
                        dominant_id=contract,
                        exchange="SHF",
                        trading_date=_stamp(day),
                        open_interest=1000.0,
                    )
                rows.append(row)
        return pd.DataFrame(rows[::-1])  # PandaData answers newest first

    def _daily(self, symbol, start, end, adjusted):
        days = _days(start, end)
        closes = [
            self._base(symbol) * (self._factor(symbol, day) if adjusted else 1.0) for day in days
        ]
        return pd.DataFrame(
            {"symbol": symbol, "date": [_stamp(day) for day in days], "close": closes}
        )

    def fetch_market_data(self, symbol, start, end, *, type, adjust=None):
        return self._daily(symbol, start, end, adjust == "post")

    def get_fund_daily(self, start, end, *, symbol):
        return self._daily(symbol, start, end, False)

    def get_fund_daily_post(self, start, end, *, symbol):
        return self._daily(symbol, start, end, True)

    def get_stock_dividend(self, start, end, *, symbol=None):
        rows = [
            {"symbol": symbol, "ex_date": day}
            for day in self.ex_dates.get(symbol, [])
            if start <= day <= end
        ]
        return pd.DataFrame(rows, columns=["symbol", "ex_date"])

    def get_adj_factor(self, symbol, start, end):
        rows = [
            {"symbol": symbol, "ex_date": day, "ex_cum_factor": value}
            for day, value in self.published.get(symbol, {}).items()
            if start <= day <= end
        ]
        return pd.DataFrame(rows, columns=["symbol", "ex_date", "ex_cum_factor"])


class FakeSina:
    """Serves ``bars[sina_code]`` as Sina pages; codes in ``failing`` raise."""

    def __init__(self):
        self.bars: dict[str, list[tuple[datetime, float]]] = {}
        self.failing: set[str] = set()
        self.calls: list[str] = []

    def add(self, code: str, *rows: tuple[datetime, float]) -> None:
        self.bars.setdefault(code, []).extend(rows)

    def _page(self, code: str, time_column: str) -> pd.DataFrame:
        self.calls.append(code)
        if code in self.failing:
            raise ConnectionError("Sina closed the connection")
        rows = sorted(self.bars.get(code, []))
        return pd.DataFrame(
            {
                time_column: [eob.strftime("%Y-%m-%d %H:%M:%S") for eob, _ in rows],
                "open": [close for _, close in rows],
                "high": [close + 1 for _, close in rows],
                "low": [close - 1 for _, close in rows],
                "close": [close for _, close in rows],
                "volume": [50.0] * len(rows),
                **({"hold": [900.0] * len(rows)} if time_column == "datetime" else {}),
                **({"amount": [1.0] * len(rows)} if time_column == "day" else {}),
            }
        )

    def futures_zh_min_sina(self, symbol, period):
        return self._page(symbol, "datetime")

    def stock_zh_a_hist_min_sina(self, symbol, period, adjust=""):
        return self._page(symbol, "day")
