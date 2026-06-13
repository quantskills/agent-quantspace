"""Matplotlib chart helpers that return PNG bytes.

Every function here writes to an in-memory buffer and returns ``bytes`` so
callers can inline the image into HTML via base64 or save it to disk with a
single ``Path.write_bytes()``. The shared helper closes the figure
deterministically — stray figures leak memory in long-running cron jobs.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg", force=True)  # noqa: E402 — pin headless backend before pyplot

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def _fig_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def plot_equity_curve(returns: pd.Series, title: str = "Equity Curve") -> bytes:
    """Plot cumulative returns.

    ``returns`` is a daily-return Series indexed by date. Missing values are
    filled with zero to avoid breaking the cumulative product.
    """
    r = returns.fillna(0.0)
    equity = (1 + r).cumprod()
    fig, ax = plt.subplots(figsize=(10, 5))
    equity.plot(ax=ax, linewidth=1.5, color="steelblue")
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative Return")
    ax.grid(True, alpha=0.3)
    ax.axhline(y=1.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    return _fig_to_png(fig)


def plot_backtest_performance(
    result_df: pd.DataFrame,
    title: str = "Backtest Performance",
) -> bytes:
    """Plot strategy equity and drawdown from a backtest result frame."""
    if result_df.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.set_title(title)
        ax.text(0.5, 0.5, "No backtest results", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        return _fig_to_png(fig)

    returns = (
        result_df.get("return", pd.Series(0.0, index=result_df.index)).astype(float).fillna(0.0)
    )
    equity = result_df.get("equity", (1.0 + returns).cumprod()).astype(float)
    drawdown = result_df.get("drawdown", equity.div(equity.cummax()).sub(1.0)).astype(float)
    drawdown = drawdown.where(drawdown <= 0.0, -drawdown).fillna(0.0)

    fig, (equity_ax, drawdown_ax) = plt.subplots(
        2,
        1,
        figsize=(10, 6),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )

    equity_ax.plot(equity.index, equity, linewidth=1.6, color="#2f6f9f", label="Strategy")
    if "raw_equity" in result_df.columns:
        raw_equity = result_df["raw_equity"].astype(float)
        equity_ax.plot(
            raw_equity.index,
            raw_equity,
            linewidth=1.0,
            color="#9aa5b1",
            alpha=0.75,
            label="Before costs",
        )
    equity_ax.axhline(y=1.0, color="#7a7a7a", linestyle="--", linewidth=0.8, alpha=0.7)
    equity_ax.set_title(title)
    equity_ax.set_ylabel("Equity")
    equity_ax.grid(True, alpha=0.25)
    equity_ax.legend(loc="upper left", fontsize=8)

    drawdown_ax.fill_between(drawdown.index, drawdown, 0.0, color="#c0504d", alpha=0.28)
    drawdown_ax.plot(drawdown.index, drawdown, linewidth=0.8, color="#c0504d")
    drawdown_ax.set_ylabel("Drawdown")
    drawdown_ax.set_xlabel("Date")
    drawdown_ax.grid(True, alpha=0.25)

    return _fig_to_png(fig)


def plot_ic_heatmap(ic_df: pd.DataFrame, title: str = "IC Heatmap") -> bytes:
    """Heatmap of an IC matrix (rows = factors, columns = pools or holding periods)."""
    fig, ax = plt.subplots(figsize=(max(6, 0.6 * len(ic_df.columns)), max(4, 0.4 * len(ic_df))))
    data = ic_df.to_numpy()
    vmax = np.nanmax(np.abs(data)) if data.size else 0.1
    im = ax.imshow(data, aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(len(ic_df.columns)))
    ax.set_xticklabels(ic_df.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(ic_df.index)))
    ax.set_yticklabels(ic_df.index)
    ax.set_title(title)
    fig.colorbar(im, ax=ax, shrink=0.8)
    return _fig_to_png(fig)


def plot_factor_ranking(
    ranking_df: pd.DataFrame,
    value_col: str = "IC_IR",
    label_col: str = "indicator",
    title: str = "Factor Ranking",
    top_n: int = 20,
) -> bytes:
    """Horizontal bar chart of the top ``top_n`` factors by ``value_col``.

    Bars are colored by the sign of the value.
    """
    df = ranking_df.head(top_n).iloc[::-1]
    colors = ["#c0504d" if v < 0 else "#4f81bd" for v in df[value_col]]
    fig, ax = plt.subplots(figsize=(8, max(3, 0.3 * len(df))))
    ax.barh(df[label_col].astype(str), df[value_col], color=colors)
    ax.set_title(title)
    ax.set_xlabel(value_col)
    ax.axvline(x=0, color="black", linewidth=0.8)
    ax.grid(True, alpha=0.3, axis="x")
    return _fig_to_png(fig)


def plot_regime_states(
    prices: pd.Series,
    states: pd.Series,
    title: str = "Regime States",
) -> bytes:
    """Overlay regime labels on a price series.

    Each distinct state gets its own color; flat colored bands mark the regime
    at every point in time.
    """
    aligned = pd.concat([prices.rename("price"), states.rename("regime")], axis=1).dropna()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(aligned.index, aligned["price"], color="black", linewidth=0.9)
    unique = sorted(aligned["regime"].unique())
    colors = plt.cm.tab10(np.linspace(0, 1, max(len(unique), 1)))
    for regime, color in zip(unique, colors, strict=True):
        mask = aligned["regime"] == regime
        ax.fill_between(
            aligned.index,
            aligned["price"].min(),
            aligned["price"].max(),
            where=mask,
            color=color,
            alpha=0.15,
            label=f"Regime {regime}",
        )
    ax.set_title(title)
    ax.set_ylabel("Price")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    return _fig_to_png(fig)
