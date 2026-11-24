"""PandaData daily data shared by the daily and the minute live feeds.

Both feeds take history from PandaData up to the previous trading day and today's prices
from Sina. Stocks and funds signal on backward-adjusted prices: a day's factor is PandaData's
adjusted close over its raw close, and today's raw prices are multiplied by today's factor,
which is yesterday's unless today is an ex-date. Futures are never adjusted; a continuous
symbol (``RB_DOMINANT.SHF``) trades the contract PandaData names dominant for the day.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from typing import Any

import pandas as pd

from .spec import Instrument

# PandaData caps a stock or futures daily request at five years.
YEARS_PER_REQUEST = 4


def yyyymmdd(day: date) -> str:
    return day.strftime("%Y%m%d")


def as_day(value: Any) -> date:
    return pd.Timestamp(str(value)).date()


def _spans(start: date, end: date) -> list[tuple[str, str]]:
    spans, first = [], start
    while first <= end:
        last = min(end, date(first.year + YEARS_PER_REQUEST, first.month, 1) - timedelta(1))
        spans.append((yyyymmdd(first), yyyymmdd(last)))
        first = last + timedelta(1)
    return spans


BAR_FIELDS = ["open", "high", "low", "close", "volume"]


def daily_bars(
    client, symbols: Sequence[str], asset: str, start: date, end: date, *, adjust: str = "none"
) -> pd.DataFrame:
    """Daily bars from ``start`` to ``end``: a ``(symbol, eob)`` panel of :data:`BAR_FIELDS`.

    ``asset`` is ``stock``, ``fund`` or ``future``; ``adjust`` is ``none`` or ``post``
    (prices backward-adjusted, volume as traded); futures are never adjusted. The layout is
    the research store's (``DataManager.read_symbols``).
    """
    if adjust not in {"none", "post"}:
        raise ValueError("adjust must be 'none' or 'post'")
    symbols = list(symbols)
    if asset == "fund":
        method = client.get_fund_daily_post if adjust == "post" else client.get_fund_daily
        frames = [method(yyyymmdd(start), yyyymmdd(end), symbol=symbols)]
    elif asset in {"stock", "future"}:
        if asset == "future" and adjust != "none":
            raise ValueError("futures daily bars are never adjusted")
        extra = {"adjust": adjust} if asset == "stock" else {}
        frames = [
            client.fetch_market_data(symbols, first, last, type=asset, **extra)
            for first, last in _spans(start, end)
        ]
    else:
        raise ValueError(f"unknown asset {asset!r}")
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        raise ValueError(f"PandaData returned no daily bars for {symbols}")
    table = pd.concat(frames, ignore_index=True)
    table = table[table["symbol"].astype(str).isin(symbols)]
    panel = pd.DataFrame(
        {name: pd.to_numeric(table[name], errors="coerce") for name in BAR_FIELDS}
    ).assign(
        symbol=table["symbol"].astype(str).to_numpy(),
        eob=pd.to_datetime(table["date"].map(lambda v: as_day(v))).to_numpy(),
    )
    panel = panel.drop_duplicates(["symbol", "eob"], keep="last")
    return panel.set_index(["symbol", "eob"]).sort_index()[BAR_FIELDS].astype(float)


def close_table(panel: pd.DataFrame, symbols: Sequence[str] | None = None) -> pd.DataFrame:
    """The ``close`` column of a ``(symbol, eob)`` panel as an eob by symbol table."""
    close = panel["close"].unstack("symbol").sort_index()
    close.columns.name = "symbol"
    return close.reindex(columns=list(symbols)) if symbols is not None else close


def daily_closes(
    client, symbols: Sequence[str], asset: str, start: date, end: date, *, adjust: str = "none"
) -> pd.DataFrame:
    """Daily closes from ``start`` to ``end``: an eob by symbol table (see :func:`daily_bars`)."""
    return close_table(daily_bars(client, symbols, asset, start, end, adjust=adjust), symbols)


def adjustment_factors(raw: pd.Series, adjusted: pd.Series) -> dict[str, float]:
    """Backward-adjustment factor per ISO trading date: adjusted close over raw close."""
    ratio = (adjusted / raw).dropna()
    return {pd.Timestamp(day).date().isoformat(): round(float(v), 6) for day, v in ratio.items()}


def today_factors(
    client,
    items: Iterable[Instrument],
    last: dict[str, float],
    trading_date: date,
    *,
    last_closes: dict[str, float] | None = None,
    pre_closes: dict[str, float] | None = None,
) -> tuple[dict[str, float], dict[str, str]]:
    """Today's factor per stock or fund, and the symbols whose factor is not known yet.

    The factor carries over from ``last`` (the previous trading day's) unless today is an
    ex-date. A stock's new factor is PandaData's ``ex_cum_factor`` once published. Given
    the previous raw close (``last_closes``) and the exchange's previous close for today
    (``pre_closes``, the ex-dividend reference price on an ex-date), a difference between
    the two is an ex-date too, and the factor grows by their ratio, the way PandaData's
    backward adjustment moves: on all seven ex-dates of the 18 rotation ETFs since 2023
    (510300.SH, 511130.SH) the ratio gives PandaData's factor within 1.3e-5, where
    carrying yesterday's over is off by 0.5-2.5%. That covers funds, whose dividends
    PandaData does not publish (``get_fund_etf_dividend`` comes back empty), and stocks
    whose factor is not out yet. Without either, a stock with an announced ex-date today
    is halted.
    """
    items = list(items)
    factors = {item.symbol: last[item.symbol] for item in items}
    halted: dict[str, str] = {}
    stamp = yyyymmdd(trading_date)
    derived: dict[str, float] = {}
    for item in items:
        before = (last_closes or {}).get(item.symbol)
        reference = (pre_closes or {}).get(item.symbol)
        if before and reference and abs(before / reference - 1) > 1e-6:
            derived[item.symbol] = round(last[item.symbol] * before / reference, 6)
    for item in items:
        if item.asset != "stock":
            continue
        symbol = item.symbol
        plans = client.get_stock_dividend(
            yyyymmdd(trading_date - timedelta(365)), stamp, symbol=symbol
        )
        announced = (
            plans is not None and not plans.empty and (plans["ex_date"].astype(str) == stamp).any()
        )
        if not announced and symbol not in derived:
            continue
        events = client.get_adj_factor(symbol, stamp, stamp)
        rows = (
            events[events["ex_date"].astype(str) == stamp]
            if events is not None and not events.empty
            else pd.DataFrame()
        )
        if not rows.empty:
            factors[symbol] = round(float(rows["ex_cum_factor"].iloc[-1]), 6)
        elif symbol in derived:
            factors[symbol] = derived[symbol]
        else:
            halted[symbol] = f"{trading_date} 是除权除息日，PandaData 还没有发布当天的复权因子"
    for item in items:
        if item.asset == "fund" and item.symbol in derived:
            factors[item.symbol] = derived[item.symbol]
    return factors, halted


def dominant_contracts(client, items: Iterable[Instrument], trading_date: date) -> dict[str, str]:
    """The contract traded for each symbol: the dominant one for a continuous symbol."""
    items = list(items)
    contracts = {item.symbol: item.symbol for item in items}
    continuous = [item for item in items if item.continuous]
    if not continuous:
        return contracts
    underlyings = sorted({item.symbol.partition("_")[0].upper() for item in continuous})
    stamp = yyyymmdd(trading_date)
    table = client.get_future_dominant(stamp, stamp, underlying_symbol=underlyings)
    found = {}
    if table is not None and not table.empty:
        for _, row in table.iterrows():
            if str(row["date"]) == stamp:
                found[str(row["underlying_symbol"]).upper()] = str(row["symbol"])
    for item in continuous:
        underlying = item.symbol.partition("_")[0].upper()
        if underlying not in found:
            raise ValueError(
                f"PandaData has no dominant contract of {underlying} for {trading_date} yet"
            )
        contracts[item.symbol] = found[underlying]
    return contracts


def contract_multipliers(client, contracts: dict[str, str]) -> dict[str, float]:
    """Contract multiplier per symbol, read from the actual contract's details."""
    actual = sorted(set(contracts.values()))
    table = client.get_future_detail(actual, fields=["symbol", "contract_multiplier"])
    rows = {str(row["symbol"]): row for _, row in table.iterrows()}
    missing = [code for code in actual if code not in rows]
    if missing:
        raise ValueError(f"PandaData has no contract details for {missing}")
    return {
        symbol: float(rows[contract]["contract_multiplier"])
        for symbol, contract in contracts.items()
    }


__all__ = [
    "BAR_FIELDS",
    "adjustment_factors",
    "as_day",
    "close_table",
    "contract_multipliers",
    "daily_bars",
    "daily_closes",
    "dominant_contracts",
    "today_factors",
    "yyyymmdd",
]
