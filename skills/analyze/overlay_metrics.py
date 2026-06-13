"""Overlay performance metrics for base-position T strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _annualized_return(daily_ret: pd.Series, annual_days: int = 252) -> float:
    if daily_ret.empty:
        return 0.0
    nav = (1.0 + daily_ret.fillna(0.0)).cumprod()
    years = max(len(nav) / annual_days, 1 / annual_days)
    return float(nav.iloc[-1] ** (1 / years) - 1.0)


def _to_daily_returns(series: pd.Series) -> pd.Series:
    if series.empty:
        return series.astype(float)
    s = series.astype(float).copy()
    if not isinstance(s.index, pd.DatetimeIndex):
        raise ValueError("series index must be DatetimeIndex")
    s.index = s.index.normalize()
    # Treat large-magnitude values as per-trade bp PnL and aggregate to daily overlay returns.
    if float(s.abs().max()) > 1.0:
        return (s.groupby(level=0).sum() / 10000.0).sort_index()
    return s.groupby(level=0).apply(lambda x: (1.0 + x).prod() - 1.0).sort_index()


def overlay_alpha(trade_pnls: pd.Series, bh_daily_ret: pd.Series, annual_days: int = 252) -> float:
    """
    Annual alpha of base-position T overlay versus pure buy-and-hold.

    `trade_pnls` is interpreted as overlay incremental return stream:
    - trade-level net bp indexed by trade date, or
    - daily overlay returns indexed by date.
    """
    overlay_daily_ret = _to_daily_returns(trade_pnls)
    bh_daily = _to_daily_returns(bh_daily_ret)
    aligned = pd.concat([overlay_daily_ret, bh_daily], axis=1).fillna(0.0)
    aligned.columns = ["overlay", "bh"]
    # Overlay is incremental return on the same base capital; total return is additive.
    total_daily_ret = aligned["bh"] + aligned["overlay"]
    return _annualized_return(total_daily_ret, annual_days) - _annualized_return(
        aligned["bh"], annual_days
    )


def overlay_winrate(trades: pd.DataFrame, pnl_col: str = "net_bp") -> float:
    if trades.empty:
        return 0.0
    return float((trades[pnl_col] > 0).mean())


def max_drawdown(nav: pd.Series) -> float:
    if nav.empty:
        return 0.0
    running_max = nav.cummax()
    dd = nav / running_max - 1.0
    return float(abs(dd.min()))


def overlay_maxdd(overlay_daily_ret: pd.Series) -> tuple[float, int]:
    r = overlay_daily_ret.fillna(0.0)
    nav = pd.concat([pd.Series([1.0]), (1.0 + r).cumprod()], ignore_index=True)
    running_max = nav.cummax()
    dd = nav / running_max - 1.0
    max_dd = float(abs(dd.min())) if not dd.empty else 0.0
    under = dd < 0
    cur = 0
    max_dur = 0
    for flag in under.to_numpy():
        cur = cur + 1 if flag else 0
        max_dur = max(max_dur, cur)
    return max_dd, int(max_dur)


def overlay_sharpe(overlay_returns: pd.Series, annual_days: int = 252) -> float:
    if overlay_returns.empty:
        return 0.0
    r = overlay_returns.fillna(0.0).astype(float)
    std = float(r.std(ddof=1))
    mean = float(r.mean())
    if std == 0.0:
        if mean > 0:
            return float("inf")
        if mean < 0:
            return float("-inf")
        return 0.0
    return float(mean / std * np.sqrt(annual_days))


def trades_per_year(trades: pd.DataFrame, date_col: str = "trigger_date") -> float:
    if trades.empty:
        return 0.0
    dates = pd.to_datetime(trades[date_col]).sort_values()
    n_days = max((dates.iloc[-1] - dates.iloc[0]).days, 1)
    return float(len(trades) / (n_days / 365.25))


def regime_alpha_table(
    overlay_daily_ret: pd.Series,
    bh_daily_ret: pd.Series,
    regime_slices: dict[str, tuple[pd.Timestamp, pd.Timestamp]],
) -> pd.DataFrame:
    rows = []
    for regime, (start, end) in regime_slices.items():
        o = overlay_daily_ret.loc[start:end]
        b = bh_daily_ret.loc[start:end]
        rows.append(
            {
                "regime": regime,
                "annual_alpha": overlay_alpha(o, b),
                "overlay_ann": _annualized_return(o),
                "bh_ann": _annualized_return(b),
                "maxdd_overlay": overlay_maxdd(o)[0],
                "n_days": int(len(o)),
            }
        )
    return pd.DataFrame(rows).set_index("regime")


def summarize_overlay_metrics(
    trades: pd.DataFrame,
    overlay_daily_ret: pd.Series,
    bh_daily_ret: pd.Series,
) -> dict[str, float]:
    return {
        "annual_alpha_vs_bh": overlay_alpha(overlay_daily_ret, bh_daily_ret),
        "winrate_net": overlay_winrate(trades),
        "trades_per_year": trades_per_year(trades),
        "max_dd_overlay": overlay_maxdd(overlay_daily_ret)[0],
    }
