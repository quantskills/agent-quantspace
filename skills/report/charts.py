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


def plot_factor_diagnostics(
    ic_series: pd.Series,
    ic_stats: dict[str, float],
    group_returns: pd.DataFrame,
    turnover: pd.DataFrame,
    title: str = "Factor Diagnostics",
    rolling_ir_window: int = 60,
) -> bytes:
    """Plot IC, rolling IC IR, grouped NAV, and group turnover in one figure."""
    if rolling_ir_window < 2:
        raise ValueError("rolling_ir_window must be at least 2.")

    ic = ic_series.astype(float).dropna().sort_index()
    groups = group_returns.astype(float).sort_index()
    group_turnover = turnover.astype(float).sort_index()

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(title, fontsize=15, fontweight="bold")

    ic_ax = axes[0, 0]
    if ic.empty:
        ic_ax.text(0.5, 0.5, "No valid IC observations", ha="center", va="center")
    else:
        colors = np.where(ic.ge(0.0), "#4f81bd", "#c0504d")
        ic_ax.bar(ic.index, ic, width=1.0, color=colors, alpha=0.35, label="Daily Rank IC")
        cumulative_ax = ic_ax.twinx()
        cumulative_ax.plot(
            ic.index,
            ic.cumsum(),
            color="#1f4e79",
            linewidth=1.4,
            label="Cumulative IC",
        )
        cumulative_ax.set_ylabel("Cumulative IC")
        lines, labels = ic_ax.get_legend_handles_labels()
        lines2, labels2 = cumulative_ax.get_legend_handles_labels()
        ic_ax.legend(lines + lines2, labels + labels2, loc="upper left", fontsize=8)
    ic_ax.axhline(0.0, color="#777777", linewidth=0.8)
    ic_ax.set_title("IC")
    ic_ax.set_ylabel("Rank IC")
    ic_ax.grid(True, alpha=0.2)

    ir_ax = axes[0, 1]
    if ic.empty:
        ir_ax.text(0.5, 0.5, "No valid IC observations", ha="center", va="center")
    else:
        min_periods = min(max(10, rolling_ir_window // 3), rolling_ir_window)
        rolling_mean = ic.rolling(rolling_ir_window, min_periods=min_periods).mean()
        rolling_std = ic.rolling(rolling_ir_window, min_periods=min_periods).std()
        rolling_ir = rolling_mean.div(rolling_std.replace(0.0, np.nan))
        ir_ax.plot(rolling_ir.index, rolling_ir, color="#8064a2", linewidth=1.3)
        overall_ir = float(ic_stats.get("IC_IR", np.nan))
        if np.isfinite(overall_ir):
            ir_ax.axhline(
                overall_ir,
                color="#f79646",
                linestyle="--",
                linewidth=1.1,
                label=f"Full-period IR {overall_ir:.3f}",
            )
            ir_ax.legend(loc="upper left", fontsize=8)
        summary = (
            f"Mean IC  {float(ic_stats.get('IC_mean', np.nan)):.3f}\n"
            f"Positive {float(ic_stats.get('IC_>0', np.nan)):.1%}\n"
            f"p-value  {float(ic_stats.get('p_value', np.nan)):.3f}"
        )
        ir_ax.text(
            0.98,
            0.97,
            summary,
            transform=ir_ax.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
        )
    ir_ax.axhline(0.0, color="#777777", linewidth=0.8)
    ir_ax.set_title(f"Rolling IC IR ({rolling_ir_window} observations)")
    ir_ax.set_ylabel("Mean IC / IC Std")
    ir_ax.grid(True, alpha=0.2)

    group_ax = axes[1, 0]
    if groups.empty:
        group_ax.text(0.5, 0.5, "No grouped-return observations", ha="center", va="center")
    else:
        group_nav = (1.0 + groups.fillna(0.0)).cumprod()
        group_nav.plot(ax=group_ax, linewidth=1.25, colormap="viridis")
        group_ax.axhline(1.0, color="#777777", linestyle="--", linewidth=0.8)
        group_ax.legend(loc="best", ncol=2, fontsize=8)
    group_ax.set_title("Layered Portfolio NAV (low factor → high factor)")
    group_ax.set_ylabel("NAV")
    group_ax.grid(True, alpha=0.2)

    turnover_ax = axes[1, 1]
    if group_turnover.empty:
        turnover_ax.text(0.5, 0.5, "No turnover observations", ha="center", va="center")
    else:
        active_turnover = group_turnover.loc[group_turnover.abs().sum(axis=1).gt(0.0)]
        if active_turnover.empty:
            active_turnover = group_turnover
        active_turnover.plot(
            ax=turnover_ax,
            linewidth=0.8,
            alpha=0.45,
            colormap="viridis",
            legend=False,
        )
        mean_turnover = active_turnover.mean(axis=1)
        turnover_ax.plot(
            mean_turnover.index,
            mean_turnover,
            color="#c0504d",
            linewidth=1.6,
            label="Cross-group mean",
        )
        turnover_ax.legend(loc="upper right", fontsize=8)
        turnover_ax.text(
            0.02,
            0.97,
            f"Mean turnover {mean_turnover.mean():.1%}",
            transform=turnover_ax.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
        )
    turnover_ax.set_title("Group Turnover")
    turnover_ax.set_ylabel("Turnover ratio")
    turnover_ax.grid(True, alpha=0.2)

    for ax in axes.flat:
        ax.set_xlabel("Date")
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    return _fig_to_png(fig)


def plot_ic_heatmap(ic_df: pd.DataFrame, title: str = "IC Heatmap") -> bytes:
    """Heatmap of an IC matrix (rows = factors, columns = namespaces or holding periods)."""
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
