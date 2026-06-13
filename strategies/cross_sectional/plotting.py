"""Plotting helpers for backtest results."""

from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


def plot_backtest_results(
    result_df: pd.DataFrame,
    metrics: dict[str, float],
    show_plot: bool = True,
    save_path: str | None = None,
):
    """Plot cumulative returns and drawdown for a backtest result."""
    if result_df is None or result_df.empty:
        raise ValueError("result_df must be a non-empty DataFrame.")

    drawdown_end = result_df["drawdown"].idxmin()
    drawdown_slice = result_df.loc[:drawdown_end]
    drawdown_start = drawdown_slice["cum_return_max"].idxmax()

    fig = plt.figure(figsize=(24, 12))
    plt.plot(result_df.index, result_df["cum_return"], linewidth=1.5, label="net")
    plt.plot(
        result_df.index,
        result_df["cum_raw_return"],
        linewidth=1.0,
        alpha=0.6,
        linestyle="--",
        label="gross",
    )
    plt.plot(
        [drawdown_start, drawdown_end],
        [result_df.loc[drawdown_start, "cum_return"], result_df.loc[drawdown_end, "cum_return"]],
        linestyle="--",
        color="r",
        linewidth=2,
    )
    plt.fill_between(result_df.index, result_df["drawdown"], 0, facecolor="#FF0000", alpha=0.1)
    plt.plot(result_df.index, result_df["drawdown"], color="#ec700a", linewidth=0.8)

    plt.legend(
        [
            (
                f"Total: {metrics.get('total_return', 0.0) * 100:.2f}%  "
                f"Ann: {metrics.get('ann_return', 0.0) * 100:.2f}%  "
                f"MD: {metrics.get('max_drawdown', 0.0) * 100:.2f}%  "
                f"Calmar: {metrics.get('calmar_ratio', 0.0):.2f}"
            ),
            (
                f"Sharpe: {metrics.get('sharpe_ratio', 0.0):.2f}  "
                f"Sortino: {metrics.get('sortino_ratio', 0.0):.2f}  "
                f"AvgTurnover: {metrics.get('avg_daily_turnover', 0.0) * 100:.2f}%"
            ),
            f"MaxDD: {drawdown_start.strftime('%Y-%m-%d')} ~ {drawdown_end.strftime('%Y-%m-%d')}",
        ],
        loc="upper left",
        fontsize=11,
    )

    axis = plt.gca()
    interval = max(1, round(len(result_df) / 500))
    axis.xaxis.set_major_locator(mdates.MonthLocator(interval=interval))
    fig.autofmt_xdate()
    plt.grid(True, alpha=0.3)
    plt.title("Cross-sectional backtest")
    plt.xlabel("Date")
    plt.ylabel("Cumulative return")

    if save_path:
        plt.savefig(save_path, bbox_inches="tight", dpi=100)
    if show_plot:
        plt.show()
    return fig


def plot_weight_heatmap(weights_df: pd.DataFrame, show_plot: bool = True):
    """Plot a monthly-sampled weight heatmap."""
    if weights_df is None or weights_df.empty:
        raise ValueError("weights_df must be a non-empty DataFrame.")

    monthly = weights_df.resample("M").last()
    monthly = monthly.loc[:, (monthly > 0).any(axis=0)]

    fig, ax = plt.subplots(figsize=(20, 8))
    image = ax.imshow(monthly.T.values, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax.set_yticks(range(len(monthly.columns)))
    ax.set_yticklabels(monthly.columns, fontsize=8)

    n_ticks = min(len(monthly), 20)
    step = max(1, len(monthly) // n_ticks) if len(monthly) > 0 else 1
    ax.set_xticks(range(0, len(monthly), step))
    ax.set_xticklabels(
        [date.strftime("%Y-%m") for date in monthly.index[::step]], rotation=45, fontsize=8
    )

    plt.colorbar(image, ax=ax, label="Weight")
    plt.title("Portfolio weights")
    plt.tight_layout()
    if show_plot:
        plt.show()
    return fig
