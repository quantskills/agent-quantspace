"""Today's intraday bars of futures from TqSdk (Shinny Tech), in PandaData codes.

TqSdk streams every tick of a futures contract, and the bars are built here from those
ticks with PandaData's boundaries: the 1-minute bar ending at E holds the ticks from
E - 1 minute up to, but not including, E. The tick stamped exactly E:00.000 belongs to
the next bar, and a trading day's first bar also holds the opening auction before its
session starts. On 2026-11-24 (RB2701, 74 bars) such bars matched PandaData's close and
volume exactly. TqSdk's own K lines put the E:00.000 tick in the earlier bar and differ
in about a third of the closes and in most volumes, so they only fill the minutes older
than the ticks TqSdk keeps (:data:`TICK_LENGTH`, about 75 minutes of an active contract).

A bar ending at E is finished once a tick at or after E has arrived, or
:data:`GRACE_SECONDS` after E when none does (a quiet market or the last bar of a
session). Each call logs in with ``TQ_USERNAME`` and ``TQ_PASSWORD`` (environment or the
project's ``.env``), fetches, and logs out. TqSdk here covers futures only.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .akshare_bars import COLUMNS, FREQUENCIES, IntradayBars, IntradayDependencyError

SOURCE_TICK = "tqsdk_tick"
SOURCE_KLINE = "tqsdk_kline"
TIMEZONE = ZoneInfo("Asia/Shanghai")
INSTALL_HINT = "uv sync --extra tqsdk"
EXCHANGES = {
    "SHF": "SHFE",
    "DCE": "DCE",
    "CZC": "CZCE",
    "CFE": "CFFEX",
    "INE": "INE",
    "GFE": "GFEX",
}
UPPER_CASE = frozenset({"CZCE", "CFFEX"})
# The most ticks TqSdk serves in one request.
TICK_LENGTH = 8964
# One-minute K lines: a whole trading day with the longest night session, and spare.
KLINE_LENGTH = 720
GRACE_SECONDS = 3
# How far before a trading day's first bar its opening auction may lie.
FIRST_BAR_LOOKBACK = timedelta(minutes=30)
_FUTURE_CODE = re.compile(r"([A-Za-z]{1,2})(\d{3,4})")
_PIECE_COLUMNS = ["eob", "open", "high", "low", "close", "volume", "amount", "open_interest"]


class TqCredentialsMissing(RuntimeError):
    """``TQ_USERNAME`` or ``TQ_PASSWORD`` is not set."""


def tq_code(symbol: str) -> str:
    """TqSdk's code of a PandaData futures code: ``RB2701.SHF`` becomes ``SHFE.rb2701``.

    Zhengzhou contracts take TqSdk's three digits (``CF2701.CZC`` becomes ``CZCE.CF701``).
    Continuous contracts such as ``RB_DOMINANT.SHF`` are refused: resolve them first.
    """
    code, _, suffix = str(symbol).strip().rpartition(".")
    suffix = suffix.upper()
    if suffix not in EXCHANGES:
        raise ValueError(f"{symbol!r} is not a futures code such as RB2701.SHF")
    if "_" in code:
        raise ValueError(f"{symbol!r} is a continuous contract; resolve it to the actual one")
    match = _FUTURE_CODE.fullmatch(code)
    if not match:
        raise ValueError(f"{symbol!r} needs a product and a year-month such as RB2701")
    product, digits = match.groups()
    exchange = EXCHANGES[suffix]
    if exchange == "CZCE" and len(digits) == 4:
        digits = digits[1:]
    product = product.upper() if exchange in UPPER_CASE else product.lower()
    return f"{exchange}.{product}{digits}"


def connect():
    """Log in to TqSdk with ``TQ_USERNAME`` and ``TQ_PASSWORD``; the caller closes the API."""
    from .panda_data import _load_dotenv_if_present

    try:
        from tqsdk import TqApi, TqAuth
    except ImportError as exc:  # pragma: no cover - exercised through the CLI message
        raise IntradayDependencyError(
            f"TqSdk is not installed ({exc}); run `{INSTALL_HINT}`"
        ) from exc
    _load_dotenv_if_present()
    user, password = os.environ.get("TQ_USERNAME"), os.environ.get("TQ_PASSWORD")
    if not user or not password:
        raise TqCredentialsMissing(
            "TQ_USERNAME and TQ_PASSWORD are not set; put the Shinny account in .env"
        )
    # TqSdk prints notices on stdout, where the workflows print their JSON report.
    return TqApi(auth=TqAuth(user, password), disable_print=True)


def _local(values: pd.Series) -> pd.Series:
    """TqSdk's nanosecond epoch stamps as naive Asia/Shanghai times."""
    stamps = pd.to_datetime(pd.to_numeric(values, errors="coerce"), unit="ns", utc=True)
    return stamps.dt.tz_convert(TIMEZONE).dt.tz_localize(None)


def _column(raw: pd.DataFrame, name: str) -> pd.Series:
    if name in raw:
        return pd.to_numeric(raw[name], errors="coerce").astype(float)
    return pd.Series(float("nan"), index=raw.index)


def _ticks(raw: pd.DataFrame) -> pd.DataFrame:
    """Trades in time order; TqSdk pads with empty rows and settlement updates carry no price."""
    frame = pd.DataFrame(
        {
            "t": _local(raw["datetime"]),
            "price": _column(raw, "last_price"),
            "volume": _column(raw, "volume"),
            "amount": _column(raw, "amount"),
            "open_interest": _column(raw, "open_interest"),
        }
    )
    frame = frame.dropna(subset=["t", "price", "volume"])
    frame = frame[frame["t"] > pd.Timestamp("2000-01-01")]
    return frame.sort_values("t", kind="stable").reset_index(drop=True)


def tick_minutes(
    raw_ticks: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Timestamp | None, pd.Timestamp | None]:
    """1-minute bars from ticks, the first tick's time and the last tick's time.

    The bar ending at E holds the ticks in [E - 1 minute, E). Volume and amount are the
    change in the day's running totals, which restart with each trading day; the first
    minute of a trading day that begins inside the ticks counts from zero, so it includes
    the opening auction. Minutes that start before the first tick are left out (their
    trades are only partly there), unless their trading day begins inside the ticks.
    """
    ticks = _ticks(raw_ticks)
    if ticks.empty:
        return pd.DataFrame(columns=_PIECE_COLUMNS), None, None
    first, last = pd.Timestamp(ticks["t"].iloc[0]), pd.Timestamp(ticks["t"].iloc[-1])
    day = (ticks["volume"].diff() < 0).cumsum().rename("day")
    end = (ticks["t"].dt.floor("min") + pd.Timedelta(minutes=1)).rename("eob")
    grouped = ticks.groupby([day, end], sort=True)
    bars = grouped.agg(
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        total_volume=("volume", "last"),
        total_amount=("amount", "last"),
        open_interest=("open_interest", "last"),
    ).reset_index()
    by_day = bars.groupby("day")
    bars["volume"] = bars["total_volume"] - by_day["total_volume"].shift(1).fillna(0.0)
    bars["amount"] = bars["total_amount"] - by_day["total_amount"].shift(1).fillna(0.0)
    whole = (bars["day"] > 0) | (bars["eob"] - pd.Timedelta(minutes=1) > first)
    return bars.loc[whole, _PIECE_COLUMNS].reset_index(drop=True), first, last


def kline_minutes(raw_klines: pd.DataFrame) -> pd.DataFrame:
    """TqSdk's own 1-minute K lines, labelled by their end like PandaData."""
    frame = pd.DataFrame(
        {
            "eob": _local(raw_klines["datetime"]) + pd.Timedelta(minutes=1),
            **{name: _column(raw_klines, name) for name in ("open", "high", "low", "close")},
            "volume": _column(raw_klines, "volume"),
            "amount": float("nan"),
            "open_interest": _column(raw_klines, "close_oi"),
        }
    )
    frame = frame.dropna(subset=["eob", "open", "high", "low", "close"])
    frame = frame[frame["eob"] > pd.Timestamp("2000-01-01")]
    return frame.sort_values("eob").reset_index(drop=True)[_PIECE_COLUMNS]


def minute_bars(
    raw_ticks: pd.DataFrame, raw_klines: pd.DataFrame | None, now: datetime
) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Finished 1-minute bars with a ``source`` column, and the time they are finished to.

    Bars come from the ticks where the ticks cover the whole minute and from TqSdk's K lines
    before that. A bar ending at E is finished when a tick at or after E is there or
    :data:`GRACE_SECONDS` have passed since E.
    """
    ticks, covered, latest = tick_minutes(raw_ticks)
    finished = pd.Timestamp(now) - pd.Timedelta(seconds=GRACE_SECONDS)
    if latest is not None and latest > finished:
        finished = latest
    ticks = ticks.assign(source=SOURCE_TICK)
    parts = [ticks]
    if raw_klines is not None:
        klines = kline_minutes(raw_klines)
        if covered is not None:
            klines = klines[klines["eob"] - pd.Timedelta(minutes=1) <= covered]
        parts.insert(0, klines.assign(source=SOURCE_KLINE))
    parts = [part for part in parts if not part.empty]
    if not parts:
        return pd.DataFrame(columns=[*_PIECE_COLUMNS, "source"]), finished
    bars = pd.concat(parts, ignore_index=True)
    bars = bars.drop_duplicates("eob", keep="last").sort_values("eob").reset_index(drop=True)
    return bars[bars["eob"] <= finished].reset_index(drop=True), finished


def _bar_ends(minutes: pd.Series, bar_minutes: int, bar_ends: Sequence[datetime] | None):
    """The bar end each 1-minute bar belongs to (NaT when it belongs to none)."""
    if bar_ends is None:
        if bar_minutes == 1:
            return minutes
        return minutes.dt.ceil(f"{bar_minutes}min")
    ends = pd.Series(sorted(pd.Timestamp(item) for item in bar_ends))
    if ends.empty:
        return pd.Series(pd.NaT, index=minutes.index)
    starts = ends.shift(1)
    starts.iloc[0] = ends.iloc[0] - pd.Timedelta(minutes=bar_minutes) - FIRST_BAR_LOOKBACK
    position = ends.searchsorted(minutes, side="left")
    labels = pd.Series(pd.NaT, index=minutes.index, dtype="datetime64[ns]")
    inside = position < len(ends)
    chosen = position[inside]
    keep = minutes[inside].to_numpy() > starts.iloc[chosen].to_numpy()
    labels.loc[minutes.index[inside][keep]] = ends.iloc[chosen[keep]].to_numpy()
    return labels


def aggregate(
    minutes: pd.DataFrame,
    frequency: str,
    finished: pd.Timestamp,
    bar_ends: Sequence[datetime] | None = None,
) -> pd.DataFrame:
    """Bars of ``frequency`` from 1-minute bars; only bars ending by ``finished``.

    With ``bar_ends`` (a trading day's schedule) the bar ending at E holds the minutes after
    the previous end up to E, and the first bar also the minutes up to
    :data:`FIRST_BAR_LOOKBACK` before it (the opening auction). Without it a bar ends on the
    clock's multiples of its length. A bar built from any K-line minute is marked
    :data:`SOURCE_KLINE`.
    """
    columns = [*_PIECE_COLUMNS, "source"]
    if minutes.empty:
        return pd.DataFrame(columns=columns)
    bar_minutes = int(FREQUENCIES[frequency])
    labels = _bar_ends(minutes["eob"], bar_minutes, bar_ends)
    frame = minutes.assign(label=labels).dropna(subset=["label"])
    frame = frame[frame["label"] <= finished]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    grouped = frame.groupby("label", sort=True)
    bars = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        amount=("amount", lambda values: values.sum(min_count=len(values))),
        open_interest=("open_interest", "last"),
    )
    kline = grouped["source"].agg(lambda values: (values == SOURCE_KLINE).any())
    bars["source"] = kline.map({True: SOURCE_KLINE, False: SOURCE_TICK})
    return bars.rename_axis("eob").reset_index()[columns]


def fetch_tq_bars(
    symbols: Iterable[str],
    frequency: str = "5m",
    *,
    now: datetime | None = None,
    bar_ends: Sequence[datetime] | None = None,
    connector: Callable[[], Any] = connect,
) -> IntradayBars:
    """Finished bars of each futures contract; one failing contract never stops the others.

    ``now`` (default: the current Asia/Shanghai time) decides which bars have finished.
    ``bar_ends`` is the trading day's bar schedule (see :func:`aggregate`); ``connector``
    returns a logged-in TqSdk API and defaults to :func:`connect`. A missing TqSdk or
    missing credentials raise; other errors are reported per symbol in ``errors``.
    """
    if frequency not in FREQUENCIES:
        raise ValueError(f"frequency must be one of {sorted(FREQUENCIES)}")
    now = now or datetime.now(TIMEZONE)
    as_of = now.astimezone(TIMEZONE).replace(tzinfo=None) if now.tzinfo else now
    wanted = list(dict.fromkeys(symbols))
    frames, codes, errors = [], {}, {}
    try:
        api = connector()
    except (IntradayDependencyError, TqCredentialsMissing):
        raise
    except Exception as exc:  # noqa: BLE001 - reported per symbol
        message = f"TqSdk login failed: {type(exc).__name__}: {str(exc)[:300]}"
        return IntradayBars(
            bars=pd.DataFrame(columns=COLUMNS),
            frequency=frequency,
            as_of=as_of,
            errors=dict.fromkeys(wanted, message),
        )
    try:
        for symbol in wanted:
            try:
                code = tq_code(symbol)
                codes[symbol] = code
                ticks = api.get_tick_serial(code, data_length=TICK_LENGTH).copy()
                klines = api.get_kline_serial(code, 60, data_length=KLINE_LENGTH).copy()
                minutes, finished = minute_bars(ticks, klines, as_of)
                frame = aggregate(minutes, frequency, finished, bar_ends)
            except Exception as exc:  # noqa: BLE001 - reported per symbol
                errors[symbol] = f"{type(exc).__name__}: {str(exc)[:300]}"
                continue
            if frame.empty:
                errors[symbol] = "TqSdk returned no finished bars"
                continue
            frame.insert(0, "symbol", symbol)
            frames.append(frame)
    finally:
        api.close()
    bars = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    return IntradayBars(
        bars=bars.reindex(columns=COLUMNS),
        frequency=frequency,
        as_of=as_of,
        codes=codes,
        errors=errors,
    )


__all__ = [
    "GRACE_SECONDS",
    "INSTALL_HINT",
    "SOURCE_KLINE",
    "SOURCE_TICK",
    "TqCredentialsMissing",
    "aggregate",
    "connect",
    "fetch_tq_bars",
    "minute_bars",
    "tick_minutes",
    "tq_code",
]
