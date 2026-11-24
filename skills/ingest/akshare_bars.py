"""Today's intraday bars from Sina through AKShare, in PandaData codes.

PandaData publishes minute bars once a day after the close, so during the session the
bars of the current day come from Sina's minute-bar pages through AKShare. Callers pass
and receive PandaData codes (``000001.SZ``, ``RB2701.SHF``, ``CF2701.CZC``); the Sina codes
(``sz000001``, ``RB2701``, ``CF2701``) never leave this module.

Sina returns the most recent bars only (1970 stock bars, 1023 futures bars per request),
unadjusted, labelled by the bar's end time like PandaData. It also returns bars that have
not finished yet: the bar still forming and, after a night session, a placeholder bar
stamped with the next session's first minute. Every bar that ends after the current
minute is dropped here, so callers only ever see finished bars.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

SOURCE = "akshare_sina"
TIMEZONE = ZoneInfo("Asia/Shanghai")
# Bar interval -> AKShare ``period`` argument.
FREQUENCIES = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60"}
STOCK_PREFIXES = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
FUTURES_SUFFIXES = frozenset({"SHF", "DCE", "CZC", "CFE", "INE", "GFE"})
COLUMNS = [
    "symbol",
    "eob",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "open_interest",
    "source",
]
INSTALL_HINT = "uv sync --extra akshare"
_FUTURE_CODE = re.compile(r"([A-Za-z]{1,2})(\d{3,4})")


class IntradayDependencyError(ImportError):
    """AKShare is not installed."""


def _czc_year(digit: str, today: date) -> str:
    """Two-digit year of a Zhengzhou contract whose code carries only the last year digit."""
    decade = today.year - today.year % 10
    for year in (decade - 10 + int(digit), decade + int(digit), decade + 10 + int(digit)):
        if today.year - 5 <= year <= today.year + 4:
            return f"{year % 100:02d}"
    raise AssertionError("unreachable: one candidate always falls in the ten-year window")


def sina_code(symbol: str, *, today: date | None = None) -> tuple[str, str]:
    """``(kind, sina_code)`` for a PandaData symbol; ``kind`` is ``stock`` or ``future``.

    Stocks, listed funds and indexes share Sina's ``sh``/``sz``/``bj`` form. Futures use the
    upper-case product and a four-digit year-month, as PandaData does for every exchange
    (``CF2701.CZC`` becomes ``CF2701``); Zhengzhou's own three-digit form ``CF701.CZC`` is
    accepted too and gets the nearest decade. Continuous contracts such as
    ``RB_DOMINANT.SHF`` are refused: resolve them to the actual contract first.
    """
    code, _, suffix = str(symbol).strip().rpartition(".")
    suffix = suffix.upper()
    if not code or not suffix:
        raise ValueError(f"{symbol!r} is not a PandaData code such as 000001.SZ or RB2701.SHF")
    if suffix in STOCK_PREFIXES:
        if not (code.isdigit() and len(code) == 6):
            raise ValueError(f"{symbol!r} needs a six-digit code")
        return "stock", STOCK_PREFIXES[suffix] + code
    if suffix in FUTURES_SUFFIXES:
        if "_" in code:
            raise ValueError(
                f"{symbol} is a continuous contract; resolve it to the actual contract first"
            )
        match = _FUTURE_CODE.fullmatch(code)
        if not match:
            raise ValueError(f"{symbol!r} is not a futures contract code such as RB2701.SHF")
        product, digits = match.group(1).upper(), match.group(2)
        if len(digits) == 3:
            if suffix != "CZC":
                raise ValueError(f"{symbol!r}: only Zhengzhou contracts use three digits")
            digits = _czc_year(digits[0], today or datetime.now(TIMEZONE).date()) + digits[1:]
        return "future", product + digits
    raise ValueError(f"{symbol!r}: AKShare intraday bars cover A-shares, funds and futures")


def _load_akshare():
    try:
        import akshare
    except ImportError as exc:  # pragma: no cover - exercised through the CLI message
        raise IntradayDependencyError(
            f"AKShare is not installed ({exc}); run `{INSTALL_HINT}`"
        ) from exc
    return akshare


def _normalize(raw: pd.DataFrame, kind: str, symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=COLUMNS)
    time_column = "day" if kind == "stock" else "datetime"
    missing = {time_column, "open", "high", "low", "close", "volume"} - set(raw.columns)
    if missing:
        raise ValueError(f"AKShare returned no {sorted(missing)} columns for {symbol}")
    frame = pd.DataFrame(
        {
            "eob": pd.to_datetime(raw[time_column]),
            # Sina's stock pages return numbers as strings.
            **{
                name: pd.to_numeric(raw[name], errors="coerce").astype(float)
                for name in ("open", "high", "low", "close", "volume")
            },
        }
    )
    frame["amount"] = (
        pd.to_numeric(raw["amount"], errors="coerce") if "amount" in raw else float("nan")
    )
    frame["open_interest"] = (
        pd.to_numeric(raw["hold"], errors="coerce") if "hold" in raw else float("nan")
    )
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame.insert(0, "symbol", symbol)
    frame["source"] = SOURCE
    return frame.drop_duplicates("eob", keep="last").sort_values("eob").reset_index(drop=True)


@dataclass(frozen=True)
class IntradayBars:
    """Finished bars of the requested symbols plus what went wrong per symbol.

    ``unfinished`` counts the bars dropped per symbol because they end after ``as_of``.
    """

    bars: pd.DataFrame
    frequency: str
    as_of: datetime
    codes: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    unfinished: dict[str, int] = field(default_factory=dict)


def fetch_intraday_bars(
    symbols: Iterable[str],
    frequency: str = "5m",
    *,
    now: datetime | None = None,
    pause: float = 0.0,
    akshare: Any = None,
    sleep: Callable[[float], None] = time.sleep,
) -> IntradayBars:
    """Fetch recent finished bars for each symbol; one failing symbol never stops the others.

    ``now`` (default: the current Asia/Shanghai time) decides which bars have finished: a
    bar labelled after the start of the current minute is dropped. ``pause`` waits between
    requests. Errors are reported per symbol in ``errors`` instead of being raised.
    """
    if frequency not in FREQUENCIES:
        raise ValueError(f"frequency must be one of {sorted(FREQUENCIES)}")
    now = now or datetime.now(TIMEZONE)
    as_of = (now.astimezone(TIMEZONE).replace(tzinfo=None) if now.tzinfo else now).replace(
        second=0, microsecond=0
    )
    module = akshare or _load_akshare()
    period = FREQUENCIES[frequency]
    frames, codes, errors, unfinished = [], {}, {}, {}
    for position, symbol in enumerate(dict.fromkeys(symbols)):
        if position and pause:
            sleep(pause)
        try:
            kind, code = sina_code(symbol, today=as_of.date())
            codes[symbol] = code
            if kind == "stock":
                raw = module.stock_zh_a_hist_min_sina(symbol=code, period=period, adjust="")
            else:
                raw = module.futures_zh_min_sina(symbol=code, period=period)
            frame = _normalize(raw, kind, symbol)
        except IntradayDependencyError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported per symbol
            errors[symbol] = f"{type(exc).__name__}: {str(exc)[:300]}"
            continue
        late = frame["eob"] > pd.Timestamp(as_of)
        unfinished[symbol] = int(late.sum())
        frame = frame.loc[~late]
        if frame.empty:
            errors[symbol] = "AKShare returned no finished bars"
            continue
        frames.append(frame)
    bars = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    return IntradayBars(
        bars=bars[COLUMNS],
        frequency=frequency,
        as_of=as_of,
        codes=codes,
        errors=errors,
        unfinished=unfinished,
    )


@dataclass(frozen=True)
class SinaQuote:
    """Sina's real-time quote of a stock or fund: the exchange's previous close and today."""

    symbol: str
    pre_close: float
    open: float
    last: float
    date: str  # YYYY-MM-DD of the quote
    time: str  # HH:MM:SS


SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}


def fetch_sina_quotes(
    symbols: Iterable[str], *, get: Callable[..., Any] | None = None, timeout: float = 10
) -> tuple[dict[str, SinaQuote], dict[str, str]]:
    """Real-time quotes of stocks and funds in one request; ``(quotes, errors)`` by symbol.

    On an ex-date the exchange's previous close (``pre_close``) is the ex-dividend
    reference price, not yesterday's close, so it tells today's adjustment before PandaData
    publishes it.
    """
    import requests

    wanted = {}
    errors: dict[str, str] = {}
    for symbol in dict.fromkeys(symbols):
        try:
            kind, code = sina_code(symbol)
        except ValueError as exc:
            errors[symbol] = str(exc)
            continue
        if kind != "stock":
            errors[symbol] = "Sina quotes here cover stocks and funds only"
            continue
        wanted[code] = symbol
    if not wanted:
        return {}, errors
    try:
        response = (get or requests.get)(
            SINA_QUOTE_URL + ",".join(wanted), headers=SINA_HEADERS, timeout=timeout
        )
        response.raise_for_status()
        text = response.content.decode("gb18030")
    except Exception as exc:  # noqa: BLE001 - reported per symbol
        message = f"{type(exc).__name__}: {str(exc)[:300]}"
        return {}, {**errors, **dict.fromkeys(wanted.values(), message)}
    quotes = {}
    for line in text.splitlines():
        name, _, body = line.partition("=")
        code = name.strip().removeprefix("var hq_str_")
        fields = body.strip().strip(";").strip('"').split(",")
        if code not in wanted:
            continue
        symbol = wanted[code]
        try:
            quotes[symbol] = SinaQuote(
                symbol=symbol,
                pre_close=float(fields[2]),
                open=float(fields[1]),
                last=float(fields[3]),
                date=fields[30],
                time=fields[31],
            )
        except (IndexError, ValueError):
            errors[symbol] = f"Sina returned no quote for {code}"
    for symbol in wanted.values():
        if symbol not in quotes and symbol not in errors:
            errors[symbol] = "Sina returned no quote"
    return quotes, errors


__all__ = [
    "COLUMNS",
    "FREQUENCIES",
    "INSTALL_HINT",
    "SOURCE",
    "IntradayBars",
    "IntradayDependencyError",
    "SinaQuote",
    "fetch_intraday_bars",
    "fetch_sina_quotes",
    "sina_code",
]
