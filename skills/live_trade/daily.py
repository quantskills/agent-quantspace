"""Daily strategies go live at 14:50 of the trading day, with the 14:50 price as the close.

A daily strategy does not wait for the close and trade the next morning: the night session
moves prices before then. Its live run signals and trades at 14:50, and the day's bar is
the 1-minute bars of the trading day up to 14:50: the first bar's open, the highest high,
the lowest low, the 14:50 close, the summed volume. The history is PandaData's daily bars
up to the previous trading day. Stocks and funds are backward-adjusted with today's factor;
a futures continuous symbol takes the bars of the contract PandaData names dominant for the
day and is never adjusted. The backtest that matches trades at the close of the signal day
(``trade_at="close", signal_lag=0``).

A workflow loads its bars with :func:`load_daily_bars` and hands
``bars.inputs(target_weights(bars.close))`` (or ``target_weights(bars.panel)``) to
``daily_main``. Until every symbol's cut-off bar is there, :func:`load_daily_bars` raises
:class:`DailyNotReady`, which the run reports as ``stale`` so the next time tries again.

Measured on 2026-11-20 against PandaData's daily bars: the 1-minute bars of 510300.SH and
000001.SZ add up to the day's open, high, low, close and volume exactly; rebar's RB2701
matches the high and close, but Sina's bars leave out the night session's opening auction
(open 2988 against 2990, low 2988 against 2986) and 15% of the volume.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from .history import (
    BAR_FIELDS,
    adjustment_factors,
    close_table,
    contract_multipliers,
    daily_bars,
    dominant_contracts,
    today_factors,
)
from .runner import DataNotReady, LiveInputs
from .spec import INTRADAY_SOURCES, Instrument

# The bar whose close stands in for the day's close, and the scheduled run times after it.
CUTOFF = time(14, 50)
# Futures orders of a daily run go out between the cut-off and the end of the day session.
DAY_CLOSE = time(15, 0)
RUN_TIMES = ("14:51", "14:53", "14:55")
ZONE = ZoneInfo("Asia/Shanghai")
# A trading day's bars end after the previous trading day's day session, which ends by then.
SESSION_GAP = time(15, 30)
# The run's intraday source when a workflow does not pass one: daily_main sets it from
# --intraday-source (``akshare`` when absent).
INTRADAY_SOURCE: ContextVar[str] = ContextVar("intraday_source", default="akshare")
SOURCE_NAMES = {"akshare": "新浪", "tqsdk": "天勤"}
BAR_ORIGINS = {
    "akshare": "新浪 1 分钟线",
    "tqsdk": "天勤 1 分钟线",
    "tqsdk+akshare": "1 分钟线（期货来自天勤，股票和基金来自新浪）",
}


def _now() -> datetime:
    """The current Shanghai time, naive; tests replace it."""
    return datetime.now(ZONE).replace(tzinfo=None)


class DailyNotReady(DataNotReady):
    """Today's cut-off price is not available yet; the run is ``stale`` and retried."""


@dataclass(frozen=True)
class DailyBars:
    """Daily bars whose last day is the trading day at the cut-off.

    ``panel`` is the signal panel, ``(symbol, eob)`` by open, high, low, close, volume, the
    research store's layout (backward-adjusted for stocks and funds unless the loader was
    asked for ``adjust="none"``); ``raw_panel`` the same unadjusted, of the traded contract
    for futures. ``close`` and ``raw_close`` are their closes as eob by symbol tables, the
    requested symbols in order.
    """

    panel: pd.DataFrame
    raw_panel: pd.DataFrame
    symbols: tuple[str, ...]
    cutoff: datetime
    contracts: dict[str, str] = field(default_factory=dict)
    multipliers: dict[str, float] = field(default_factory=dict)
    factors: dict[str, float] = field(default_factory=dict)
    suspended: tuple[str, ...] = ()
    # Where today's 1-minute bars came from: a key of :data:`BAR_ORIGINS`.
    source: str = "akshare"

    @property
    def close(self) -> pd.DataFrame:
        return close_table(self.panel, self.symbols)

    @property
    def raw_close(self) -> pd.DataFrame:
        return close_table(self.raw_panel, self.symbols)

    @property
    def notes(self) -> list[str]:
        """Message lines: where today's close came from, contracts, suspended symbols."""
        origin = BAR_ORIGINS[self.source]
        lines = [f"- 当日收盘价取 {self.cutoff:%H:%M} 的价格，当天 K 线由{origin}聚合"]
        lines += [
            f"- {symbol} 当前对应 {contract}"
            for symbol, contract in self.contracts.items()
            if symbol != contract
        ]
        if self.suspended:
            lines.append("- 截至收盘价时刻没有成交（按前收盘价）：" + "、".join(self.suspended))
        return ["说明：", *lines]

    def inputs(self, weights: pd.DataFrame) -> LiveInputs:
        """What ``daily_main`` needs: the weights, today's sizing prices and the notes."""
        return LiveInputs(
            weights=weights,
            prices=self.raw_close,
            multipliers=self.multipliers,
            contracts=self.contracts,
            notes=tuple(self.notes),
        )


def _instruments(items: Sequence[Instrument | str], asset: str | None) -> list[Instrument]:
    out = []
    for item in items:
        if isinstance(item, Instrument):
            out.append(item)
        elif asset is None:
            raise ValueError(f"pass asset= or an Instrument for {item}")
        else:
            out.append(Instrument(symbol=item, asset=asset))
    return out


def _pre_closes(client, names, kind, trade_date, quotes) -> dict[str, float]:
    """The exchange's previous close for ``trade_date``: PandaData's once the day is
    published, else today's Sina quote. Raises :class:`DailyNotReady` without one."""
    from skills.ingest.akshare_bars import fetch_sina_quotes

    stamp = trade_date.strftime("%Y%m%d")
    if kind == "fund":
        table = client.get_fund_daily(stamp, stamp, symbol=list(names))
    else:
        table = client.fetch_market_data(list(names), stamp, stamp, type="stock")
    found = {}
    if table is not None and not table.empty and "pre_close" in table:
        for row in table.itertuples():
            if str(row.date).replace("-", "")[:8] == stamp and row.pre_close:
                found[str(row.symbol)] = float(row.pre_close)
    missing = [name for name in names if name not in found]
    if not missing:
        return found
    got, errors = (quotes or fetch_sina_quotes)(missing)
    waiting = []
    for name in missing:
        quote = got.get(name)
        if quote is not None and quote.date == trade_date.isoformat() and quote.pre_close > 0:
            found[name] = quote.pre_close
        else:
            waiting.append(f"{name}：{errors.get(name) or (quote and quote.date) or '无报价'}")
    if waiting:
        raise DailyNotReady("新浪没有今天的前收盘价：" + "；".join(waiting[:3]))
    return found


# Sina has no bar for a minute without trades. When the cut-off bar is missing, the bars
# before it stand for the day once a later bar is out or this long has passed.
SETTLE = {
    "future": timedelta(minutes=5),
    "stock": timedelta(minutes=2),
    "fund": timedelta(minutes=2),
}


def _today_bar(
    bars: pd.DataFrame, since: datetime, at: datetime, settled: bool
) -> dict[str, float] | None:
    """The trading day's bar from its 1-minute bars ending after ``since`` up to ``at``.

    None while the minute ending at ``at`` may still come: it is not there, no later bar
    is, and the minute has not ``settled``. Otherwise the close is the last trade at or
    before the cut-off.
    """
    day = bars[(bars["eob"] > pd.Timestamp(since)) & (bars["eob"] <= pd.Timestamp(at))]
    day = day.sort_values("eob")
    if day.empty:
        return None
    done = pd.Timestamp(day["eob"].iloc[-1]) == pd.Timestamp(at)
    later = bool((bars["eob"] > pd.Timestamp(at)).any())
    if not (done or later or settled):
        return None
    return {
        "open": float(day["open"].iloc[0]),
        "high": float(day["high"].max()),
        "low": float(day["low"].min()),
        "close": float(day["close"].iloc[-1]),
        "volume": float(day["volume"].sum()),
    }


def _used(items: Sequence[Instrument], source: str) -> str:
    """The key of :data:`BAR_ORIGINS` for what ``source`` fetched for ``items``."""
    futures = any(item.asset == "future" for item in items)
    if source != "tqsdk" or not futures:
        return "akshare"
    return "tqsdk" if all(item.asset == "future" for item in items) else "tqsdk+akshare"


def _today_minutes(items, contracts, source, now, *, pause, akshare, tqsdk):
    """Today's 1-minute bars: futures from ``source``, stocks and funds from Sina.

    TqSdk's bars before the ticks it keeps are its own K lines; where they meet the ticks
    one tick's volume may count twice, a few contracts in a day.
    """
    from skills.ingest.akshare_bars import IntradayBars, fetch_intraday_bars

    futures = sorted({contracts[item.symbol] for item in items if item.asset == "future"})
    others = sorted({contracts[item.symbol] for item in items if item.asset != "future"})
    if source != "tqsdk" or not futures:
        wanted = sorted(set(contracts.values()))
        return fetch_intraday_bars(wanted, "1m", now=now, pause=pause, akshare=akshare)
    from skills.ingest.tqsdk_bars import connect, fetch_tq_bars

    parts = [fetch_tq_bars(futures, "1m", now=now, connector=tqsdk or connect)]
    if others:
        parts.append(fetch_intraday_bars(others, "1m", now=now, pause=pause, akshare=akshare))
    return IntradayBars(
        bars=pd.concat([part.bars for part in parts], ignore_index=True),
        frequency="1m",
        as_of=parts[0].as_of,
        codes={key: value for part in parts for key, value in part.codes.items()},
        errors={key: value for part in parts for key, value in part.errors.items()},
    )


def load_daily_bars(
    client,
    instruments: Sequence[Instrument | str],
    start: str | date,
    trade_date: date,
    *,
    asset: str | None = None,
    adjust: str = "post",
    cutoff: time = CUTOFF,
    now: datetime | None = None,
    akshare=None,
    pause: float = 0.2,
    quotes=None,
    source: str | None = None,
    tqsdk=None,
) -> DailyBars:
    """PandaData daily bars from ``start`` to the day before ``trade_date``, plus that day.

    ``instruments`` are :class:`Instrument` or symbols of one ``asset``. ``adjust`` is
    ``post`` (stocks and funds signal on backward-adjusted prices) or ``none``. Raises
    :class:`DailyNotReady` while a cut-off bar is missing, while today's previous close
    is unknown, or when a stock goes ex today with neither a published factor nor a
    changed previous close. Sina has no bar for a minute without trades, so the close is
    the last trade at or before the cut-off once a later bar is out or :data:`SETTLE`
    has passed; a stock or fund with no trade today keeps the previous close with no
    volume (``suspended``), as PandaData's bar of such a day does. Today's factor follows the exchange's previous close (see
    :func:`~skills.live_trade.history.today_factors`), from PandaData once the day is
    published and from Sina's quote (``quotes``, default
    :func:`~skills.ingest.akshare_bars.fetch_sina_quotes`) before.

    ``source`` picks where today's 1-minute bars of futures come from: ``akshare`` (Sina)
    or ``tqsdk`` (TqSdk, ``tqsdk`` is its login for tests); stocks and funds always come
    from Sina. None takes the run's ``--intraday-source`` (:data:`INTRADAY_SOURCE`).
    """
    from .feeds import load_calendar

    source = source or INTRADAY_SOURCE.get()
    if source not in INTRADAY_SOURCES:
        raise ValueError(f"source must be one of {list(INTRADAY_SOURCES)}, not {source!r}")

    items = _instruments(instruments, asset)
    symbols = [item.symbol for item in items]
    first = pd.Timestamp(start).date()
    calendar = load_calendar(client, trade_date)
    if not calendar.is_trading_day(trade_date):
        raise ValueError(f"{trade_date} is not a trading day")
    previous = calendar.previous(trade_date)

    raw_parts, adjusted_parts = [], []
    groups: dict[str, list[Instrument]] = {}
    for item in items:
        groups.setdefault(item.asset, []).append(item)
    factors: dict[str, float] = {}
    previous_close: dict[str, float] = {}
    for kind, members in groups.items():
        names = [item.symbol for item in members]
        raw = daily_bars(client, names, kind, first, previous)
        raw_parts.append(raw)
        if kind == "future" or adjust == "none":
            adjusted_parts.append(raw)
            factors.update(dict.fromkeys(names, 1.0))
            continue
        post = daily_bars(client, names, kind, first, previous, adjust="post")
        adjusted_parts.append(post)
        raw_close, post_close = close_table(raw, names), close_table(post, names)
        last, before = {}, {}
        for name in names:
            by_day = adjustment_factors(raw_close[name], post_close[name])
            if not by_day:
                raise ValueError(f"PandaData returned no daily bars to adjust {name}")
            last[name] = by_day[max(by_day)]
            before[name] = float(raw_close[name].dropna().iloc[-1])
        pre = _pre_closes(client, names, kind, trade_date, quotes)
        previous_close.update(pre)
        today, halted = today_factors(
            client, members, last, trade_date, last_closes=before, pre_closes=pre
        )
        if halted:
            raise DailyNotReady("；".join(f"{name}：{text}" for name, text in halted.items()))
        factors.update(today)
    raw = pd.concat(raw_parts).sort_index()
    adjusted = pd.concat(adjusted_parts).sort_index()
    reached = pd.Timestamp(raw.index.get_level_values("eob").max()).date()
    if reached != previous:
        raise ValueError(f"PandaData daily bars end at {reached}, not at {previous}")

    contracts = dominant_contracts(client, items, trade_date)
    futures = {item.symbol: contracts[item.symbol] for item in items if item.asset == "future"}
    multipliers = contract_multipliers(client, futures) if futures else {}
    at = datetime.combine(trade_date, cutoff)
    when = now or _now()
    fetched = _today_minutes(
        items, contracts, source, when, pause=pause, akshare=akshare, tqsdk=tqsdk
    )
    since = datetime.combine(previous, SESSION_GAP)
    today_rows, waiting, suspended = {}, [], []
    for item in items:
        contract = contracts[item.symbol]
        mine = fetched.bars[fetched.bars["symbol"] == contract]
        settled = when >= at + SETTLE[item.asset]
        bar = _today_bar(mine, since, at, settled)
        if bar is not None:
            today_rows[item.symbol] = bar
            continue
        session = mine[(mine["eob"] > pd.Timestamp(since)) & (mine["eob"] <= pd.Timestamp(at))]
        if contract in fetched.errors:
            waiting.append(f"{contract}：{fetched.errors[contract]}")
        elif session.empty and item.asset != "future" and settled:
            # No trade today: the day keeps the previous close, as PandaData's bar does.
            price = previous_close.get(item.symbol)
            if price is None:
                waiting.append(f"{contract}：今天没有成交，也没有前收盘价")
                continue
            suspended.append(item.symbol)
            today_rows[item.symbol] = dict.fromkeys(("open", "high", "low", "close"), price)
            today_rows[item.symbol]["volume"] = 0.0
        else:
            newest = pd.Timestamp(session["eob"].max()) if len(session) else None
            waiting.append(f"{contract}：最新 1 分钟 K 线 {newest or '无'}")
    if waiting:
        shown = "；".join(waiting[:3]) + ("……" if len(waiting) > 3 else "")
        raise DailyNotReady(
            f"{SOURCE_NAMES[source]}还没有 {at:%H:%M} 的 K 线（{len(waiting)}/{len(items)} 个）：{shown}"
        )
    day = pd.Timestamp(trade_date)
    raw_today = pd.DataFrame.from_dict(today_rows, orient="index")[BAR_FIELDS]
    adjusted_today = raw_today.copy()
    scale = pd.Series(factors).reindex(raw_today.index)
    for name in ("open", "high", "low", "close"):
        adjusted_today[name] = raw_today[name] * scale

    def appended(panel: pd.DataFrame, today: pd.DataFrame) -> pd.DataFrame:
        today = today.assign(eob=day).rename_axis("symbol").set_index("eob", append=True)
        return pd.concat([panel, today]).sort_index().astype(float)

    return DailyBars(
        panel=appended(adjusted, adjusted_today),
        raw_panel=appended(raw, raw_today),
        symbols=tuple(symbols),
        cutoff=at,
        contracts=contracts,
        multipliers=multipliers,
        factors=factors,
        suspended=tuple(suspended),
        source=_used(items, source),
    )


__all__ = [
    "CUTOFF",
    "DAY_CLOSE",
    "INTRADAY_SOURCE",
    "RUN_TIMES",
    "DailyBars",
    "DailyNotReady",
    "load_daily_bars",
]
