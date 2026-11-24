"""Quantity bookkeeping for ``VectorBacktester(unit="lots")``.

The target table holds lots per symbol (see :mod:`skills.backtest.units`). Row t, after
``signal_lag``, is the position held from bar t, traded at bar t's ``trade_at`` price:

- profit of bar t = lots x units per lot x (price at t+1 - price at t), on the contract
  actually held: a continuous futures symbol such as ``RB_DOMINANT.SHF`` holds the
  contract the ``contracts`` table names for the bar's trading day. On a roll the old
  contract is closed and the new one opened at their own prices on the roll bar, so the
  roll gap never enters equity and both legs pay costs. Stocks and funds earn the
  adjusted price's return on the unadjusted value (``adjusted``), so dividends count and
  splits do not show as losses;
- costs = traded value x (``commission`` + ``slippage_bp``);
- equity starts at ``capital``; the return of bar t is its net profit over the equity
  before it. Margin is not modelled; with ``margin_rates`` the margin in use is reported.

Stocks and funds also follow T+1 on intraday bars: lots bought on a trading day cannot be
sold that day, so the part of a sale beyond what was held at the day's start waits for the
next day. Daily bars trade once a day and never hit it.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from .units import check_lots_table, is_continuous_future, is_futures_symbol, units_per_lot

# Weight differences at or below this are no change (the live signal tolerance).
WEIGHT_TOLERANCE = 1e-6


def percent_to_lots(
    weights: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    capital: float,
    multipliers: Mapping[str, float] | None = None,
    tolerance: float = WEIGHT_TOLERANCE,
) -> pd.DataFrame:
    """Lots a percent strategy holds when sized only as its weights change (D11).

    A symbol is sized as ``weight x capital / (price x units per lot)``, rounded toward zero
    (a stock lot is 100 shares, a futures lot one contract), on its first row and on each
    row where its weight differs from the row before; otherwise it keeps its last lots,
    whatever the price does. This is how the live signal sizes: only changed symbols. ``prices`` are unadjusted, eob by symbol. Running the
    result through ``VectorBacktester(unit="lots")`` gives the curve of a live account that
    rebalances only on new targets, to compare with the percent backtest that returns to
    its weights on every bar.
    """
    if not np.isfinite(capital) or capital <= 0:
        raise ValueError("capital must be a positive finite number")
    frame = weights.sort_index().astype(float).fillna(0.0)
    price = prices.reindex(index=frame.index, columns=frame.columns).astype(float)
    per_lot = pd.Series({symbol: units_per_lot(symbol, multipliers) for symbol in frame.columns})
    changed = frame.diff().abs() > tolerance
    if len(changed):
        changed.iloc[0] = True
    needed = (changed & (frame.abs() > tolerance)).to_numpy()
    bad = needed & ~(np.isfinite(price.to_numpy()) & (price.to_numpy() > 0))
    if bad.any():
        row, column = (int(axis[0]) for axis in np.nonzero(bad))
        raise ValueError(
            f"Missing or invalid price for {frame.columns[column]} at {frame.index[row]}"
        )
    with np.errstate(divide="ignore", invalid="ignore"):
        sized = np.trunc(frame * capital / price.mul(per_lot, axis=1))
    lots = sized.where(frame.abs() > tolerance, 0.0).where(changed)
    return lots.ffill().fillna(0.0) + 0.0  # + 0.0 turns -0.0 into 0.0


def trading_days(eob: pd.DatetimeIndex, calendar: pd.DatetimeIndex | None = None):
    """The trading day of each bar.

    Daily bars (all at midnight) are their own day. Intraday bars from 17:00 to 06:00 are
    the night session, which belongs to the next trading day after the evening it opened
    (``calendar``, or the days that have day-session bars).
    """
    eob = pd.DatetimeIndex(eob)
    days = eob.normalize()
    if (eob == days).all():
        return days
    hours = eob.hour
    night = (hours >= 17) | (hours < 6)
    known = days[(hours >= 8) & (hours < 17)]
    if calendar is not None:
        known = known.union(pd.DatetimeIndex(calendar).normalize())
    known = known.unique().sort_values()
    opened = days.where(hours >= 17, days - pd.Timedelta(days=1))
    position = known.searchsorted(opened[night], side="right")
    if (position >= len(known)).any():
        late = opened[night][position >= len(known)][0]
        raise ValueError(f"No trading day after {late.date()} for its night session bars")
    result = days.to_numpy().copy()
    result[np.asarray(night)] = known[position].to_numpy()
    return pd.DatetimeIndex(result)


def apply_tplus(executed: pd.DataFrame, days: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.Series]:
    """Positions of stocks and funds after T+1 on intraday bars, and the lots held back.

    A sale beyond the lots held at the trading day's start is cut to them; the rest stays
    held and the target is tried again on later bars. Futures are not touched.
    """
    result = executed.copy()
    blocked = pd.Series(0.0, index=executed.index)
    day_values = np.asarray(days)
    for symbol in executed.columns:
        if is_futures_symbol(symbol):
            continue
        wanted = executed[symbol].to_numpy(dtype=float)
        held = np.zeros_like(wanted)
        position, sellable, current_day = 0.0, 0.0, None
        for index, target in enumerate(wanted):
            if day_values[index] != current_day:
                current_day, sellable = day_values[index], position
            if target < position:
                sale = min(position - target, sellable)
                blocked.iloc[index] += position - target - sale
                position -= sale
                sellable -= sale
            else:
                position = target
            held[index] = position
        result[symbol] = held
    return result, blocked


def _missing(kind: str, symbol: str, stamps) -> ValueError:
    sample = ", ".join(str(pd.Timestamp(stamp)) for stamp in list(stamps)[:3])
    return ValueError(f"Missing {kind} for {symbol} at {sample}")


def lots_frame(
    targets: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    signal_lag: int,
    capital: float,
    commission: float,
    slippage_bp: float,
    multipliers: Mapping[str, float] | None = None,
    contracts: pd.DataFrame | None = None,
    adjusted: pd.DataFrame | None = None,
    margin_rates: Mapping[str, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Per-bar results, held lots, and the implied weights of a lots target table.

    ``prices`` is the eob by symbol table of ``trade_at`` prices, unadjusted, with a column
    for every actual contract held; ``adjusted`` the matching eob by symbol table of
    adjusted prices of stocks and funds. Returns ``(result, lots, weights)``: result columns ``raw_return``,
    ``transaction_cost``, ``return``, ``turnover`` (as the percent engine) plus ``pnl``,
    ``cost``, ``equity_value``, ``gross_exposure``, ``rolls``, ``blocked_sell_lots`` and,
    with ``margin_rates``, ``margin_ratio``.
    """
    lots = check_lots_table(targets.sort_index())
    executed = lots.shift(signal_lag).fillna(0.0)
    bars = executed.index
    calendar = None if contracts is None else pd.DatetimeIndex(contracts.index)
    days = trading_days(bars, calendar)
    blocked = pd.Series(0.0, index=bars)
    if (bars != bars.normalize()).any():
        executed, blocked = apply_tplus(executed, days)
    rate = commission + slippage_bp / 10_000.0

    held_by_symbol = {}
    for symbol in executed.columns:
        if is_continuous_future(symbol):
            if contracts is None or symbol not in contracts.columns:
                raise ValueError(
                    f"{symbol} is a continuous future: pass contracts= (trading day by symbol "
                    "table of actual contracts, DataManager.read_dominant)"
                )
            table = contracts[symbol].copy()
            table.index = pd.DatetimeIndex(table.index).normalize()
            held_by_symbol[symbol] = table.reindex(days).to_numpy(dtype=object)
        else:
            held_by_symbol[symbol] = np.full(len(bars), symbol, dtype=object)
    codes = sorted(
        {str(code) for held in held_by_symbol.values() for code in held if pd.notna(code)}
    )
    price = prices.reindex(index=bars, columns=codes).astype(float).to_numpy()
    following = np.vstack([price[1:], np.full((1, len(codes)), np.nan)])
    column_of = {code: index for index, code in enumerate(codes)}
    adjusted_now = adjusted_next = None
    if adjusted is not None:
        frame = adjusted.reindex(index=bars, columns=codes).astype(float)
        adjusted_now = frame.to_numpy()
        adjusted_next = np.vstack([adjusted_now[1:], np.full((1, len(codes)), np.nan)])

    n = len(bars)
    rows = np.arange(n)
    last = rows == n - 1
    pnl = np.zeros(n)
    boundary = np.zeros(n, dtype=bool)
    traded = np.zeros(n)
    exposure = np.zeros(n)
    margin = np.zeros(n)
    rolls = np.zeros(n)
    weights = {}
    for symbol in executed.columns:
        q = executed[symbol].to_numpy(dtype=float)
        q_before = np.concatenate([[0.0], q[:-1]])
        held = held_by_symbol[symbol]
        column = np.array([column_of.get(str(code), -1) if pd.notna(code) else -1 for code in held])
        column_before = np.concatenate([[-1], column[:-1]])
        if (np.abs(q) > 0).any() or (np.abs(q_before) > 0).any():
            per_lot = units_per_lot(symbol, multipliers)
        else:
            weights[symbol] = np.zeros(n)
            continue
        active = q != 0
        if (active & (column < 0)).any():
            raise _missing("an actual contract", symbol, bars[active & (column < 0)])

        def at(table, which):
            values = np.full(n, np.nan)
            ok = which >= 0
            values[ok] = table[rows[ok], which[ok]]
            return values

        now = at(price, column)
        later = at(following, column)
        if (active & ~np.isfinite(now)).any():
            raise _missing("prices", symbol, bars[active & ~np.isfinite(now)])
        gap = active & ~np.isfinite(later) & ~last
        if gap.any():
            raise _missing("next-bar prices", symbol, bars[gap])
        boundary |= active & last
        if is_futures_symbol(symbol):
            move = later - now
        else:
            if adjusted_now is None:
                raise ValueError(
                    f"{symbol}: stock and fund lots need adjusted= (post-adjusted panel) so "
                    "dividends count"
                )
            ratio = at(adjusted_next, column) / at(adjusted_now, column)
            gap = active & ~np.isfinite(ratio) & ~last
            if gap.any():
                raise _missing("adjusted prices", symbol, bars[gap])
            move = now * (ratio - 1.0)
        pnl += np.where(active & ~last, q * per_lot * move, 0.0)

        old_now = at(price, column_before)
        same = column == column_before
        closing = ~same & (q_before != 0)
        if (closing & ~np.isfinite(old_now)).any():
            raise _missing("prices on the roll bar", symbol, bars[closing & ~np.isfinite(old_now)])
        changed = same & (q != q_before)
        if (changed & ~np.isfinite(now)).any():
            raise _missing("prices", symbol, bars[changed & ~np.isfinite(now)])
        value = np.where(changed, np.abs(q - q_before) * np.nan_to_num(now), 0.0)
        value += np.where(closing, np.abs(q_before) * np.nan_to_num(old_now), 0.0)
        value += np.where(~same & active, np.abs(q) * np.nan_to_num(now), 0.0)
        traded += value * per_lot
        rolls += (~same & (q_before != 0) & active).astype(float)
        exposure += np.abs(q) * per_lot * np.nan_to_num(now)
        if margin_rates is not None and is_futures_symbol(symbol):
            margin += (
                np.abs(q) * per_lot * np.nan_to_num(now) * float(margin_rates.get(symbol, 0.0))
            )
        weights[symbol] = q * per_lot * np.nan_to_num(now)

    cost = traded * rate
    after = capital + np.cumsum(pnl - cost)
    before = np.concatenate([[capital], after[:-1]])
    if (before <= 0).any():
        first = bars[int(np.flatnonzero(before <= 0)[0])]
        raise ValueError(f"Equity fell to zero or below before {first}; raise capital")
    profit = pd.Series(np.where(boundary, np.nan, pnl), index=bars)
    result = pd.DataFrame(
        {
            "raw_return": profit / before,
            "transaction_cost": cost / before,
            "turnover": traded / before,
            "pnl": profit,
            "cost": cost,
            "equity_value": after,
            "gross_exposure": exposure / before,
            "rolls": rolls,
            "blocked_sell_lots": blocked.to_numpy(),
        },
        index=bars,
    )
    result["return"] = result["raw_return"] - result["transaction_cost"]
    if margin_rates is not None:
        result["margin_ratio"] = margin / before
    relevant = (executed.abs().sum(axis=1) > 0).to_numpy() | (traded > 0)
    if relevant.any():
        first = bars[int(np.flatnonzero(relevant)[0])]
        result.loc[result.index < first, ["raw_return", "return"]] = np.nan
    columns = ["raw_return", "transaction_cost", "return", "turnover"]
    result = result[columns + [name for name in result.columns if name not in columns]]
    implied = pd.DataFrame(weights, index=bars).div(before, axis=0)
    return result, executed, implied.reindex(columns=executed.columns)


def lots_metrics(result: pd.DataFrame) -> dict[str, float]:
    """Money and position figures of a lots backtest, next to the return metrics."""
    if result.empty:
        return {}
    metrics = {
        "total_pnl": float(result["pnl"].sum()),
        "total_cost": float(result["cost"].sum()),
        "final_equity_value": float(result["equity_value"].iloc[-1]),
        "max_gross_exposure": float(result["gross_exposure"].max()),
        "roll_count": float(result["rolls"].sum()),
        "blocked_sell_lots": float(result["blocked_sell_lots"].sum()),
    }
    if "margin_ratio" in result.columns:
        metrics["max_margin_ratio"] = float(result["margin_ratio"].max())
        metrics["margin_over_equity_bars"] = float(result["margin_ratio"].gt(1.0).sum())
    return metrics


__all__ = ["apply_tplus", "lots_frame", "lots_metrics", "percent_to_lots", "trading_days"]
