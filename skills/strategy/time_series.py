"""Reusable time-series strategy types and signal-to-weight helpers."""

from __future__ import annotations

from typing import Any, TypedDict

import numpy as np
import pandas as pd

from skills.backtest import BacktestResult, VectorBacktester


class TimeSeriesConfig(TypedDict, total=False):
    """Configuration for the research-only time-series adapter."""

    symbol: str
    commission: float
    slippage: float
    delay: int
    position_mapping: dict[Any, Any]


DEFAULT_TS_COMMISSION = 0.0003
DEFAULT_TS_SLIPPAGE = 0.0002
DEFAULT_TS_DELAY = 1
DEFAULT_POSITION_MAPPING = {1: 1, 0: -1}


def signal_to_single_asset_weights(
    signal: pd.Series,
    *,
    symbol: str,
    exposure: float = 1.0,
) -> pd.DataFrame:
    """Convert a signed signal into a date x symbol target-weight frame."""
    clean_signal = signal.fillna(0.0).clip(lower=-1.0, upper=1.0)
    return pd.DataFrame({symbol: clean_signal * exposure}, index=signal.index)


class TimeSeriesBacktester:
    """Research-only prediction-frame adapter backed by ``VectorBacktester``.

    It maps prediction labels to single-asset target weights. Return execution,
    costs, drawdown, and metrics always use the shared vector engine.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        *,
        symbol: str,
        test_start_date: pd.Timestamp | None = None,
        commission: float | None = None,
        slippage: float | None = None,
        position_mapping: dict[Any, Any] | None = None,
        delay: int | None = None,
    ) -> None:
        self.df = df.copy()
        self.symbol = symbol
        self.result_df: pd.DataFrame | None = None
        self.executed_weights: pd.DataFrame | None = None
        self.test_start_date = test_start_date
        self.commission = DEFAULT_TS_COMMISSION if commission is None else float(commission)
        self.slippage = DEFAULT_TS_SLIPPAGE if slippage is None else float(slippage)
        self.metrics: dict[str, float] = {}
        self.delay = DEFAULT_TS_DELAY if delay is None else delay
        self.position_mapping = position_mapping
        self.set_position_by_preds()

    def set_position_by_preds(
        self,
        reverse: list[tuple[float, float]] | None = None,
        deprecate: list[tuple[float, float]] | None = None,
    ) -> pd.DataFrame:
        """Map prediction labels to delayed positions for exploratory analysis."""
        reverse = reverse or []
        deprecate = deprecate or []
        required = {"prediction_label", "prediction_score"}
        missing = sorted(required.difference(self.df.columns))
        if missing:
            raise ValueError(f"DataFrame is missing prediction columns: {missing}")
        if self.position_mapping:
            self.df["position"] = self.df["prediction_label"].map(self.position_mapping).copy()
        else:
            self.df["position"] = self.df["prediction_label"].copy()
        self.df["position"] = self.df["position"].fillna(0)
        for min_score, max_score in reverse:
            mask = (self.df["prediction_score"] >= min_score) & (
                self.df["prediction_score"] < max_score
            )
            self.df.loc[mask, "position"] = -1 * self.df.loc[mask, "position"]
        for min_score, max_score in deprecate:
            mask = (self.df["prediction_score"] >= min_score) & (
                self.df["prediction_score"] < max_score
            )
            self.df.loc[mask, "position"] = np.nan
        self.df["position"] = self.df["position"].ffill().shift(self.delay).fillna(0)
        return self.df

    def run_backtest(
        self,
        trade_col: str = "close",
        reverse: list[tuple[float, float]] | None = None,
        deprecate: list[tuple[float, float]] | None = None,
    ) -> BacktestResult:
        """Map predictions to weights and execute them with ``VectorBacktester``."""
        if not isinstance(self.df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame index must be DatetimeIndex")
        if len(self.df.index) < 2:
            raise ValueError("DataFrame must contain at least two rows")
        if trade_col not in self.df.columns:
            raise ValueError(f"DataFrame must contain trade column {trade_col!r}")
        self.set_position_by_preds(reverse=reverse, deprecate=deprecate)

        market_columns = [
            column
            for column in ("open", "high", "low", "close", "volume")
            if column in self.df.columns
        ]
        market = self.df[market_columns].copy()
        market.index = pd.DatetimeIndex(market.index, name="eob")
        market["symbol"] = self.symbol
        panel = market.reset_index().set_index(["symbol", "eob"]).sort_index()

        position = self.df["position"].copy()
        position.index = market.index
        target_weights = signal_to_single_asset_weights(position, symbol=self.symbol)
        result = VectorBacktester(
            data=panel,
            trade_at=trade_col,
            signal_lag=0,
            commission=self.commission,
            slippage_bp=self.slippage * 10_000.0,
        ).run(target_weights)
        self.executed_weights = result.executed_weights
        self.result_df = result.result_df
        self.metrics = result.metrics
        return result

    def plot_results(self, show_plt: bool = True, save_path: str | None = None) -> None:
        """Plot research cumulative return and drawdown."""
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt

        if self.result_df is None:
            raise ValueError("run_backtest() must be called before plot_results()")
        md_end_date = self.result_df["drawdown"].idxmin()
        temp_df = self.result_df.loc[:md_end_date]
        md_start_date = temp_df["cum_return_max"].idxmax()
        md_start_return = self.result_df.loc[md_start_date, "cum_return"]
        md_end_return = self.result_df.loc[md_end_date, "cum_return"]
        fig = plt.figure(figsize=(24, 12))
        plt.plot(self.result_df.index, self.result_df["cum_return"])
        plt.plot(
            [md_start_date, md_end_date],
            [md_start_return, md_end_return],
            linestyle="--",
            color="r",
        )
        data_size = self.result_df.shape[0]
        ax = plt.gca()
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(1, round(data_size / 2000))))
        if self.test_start_date:
            ax.axvline(self.test_start_date, color="red", linestyle="--", linewidth=1.5)
        plt.legend(
            [
                f"All: {round(self.metrics['total_return'] * 100, 2)}% "
                f"Month: {round(self.metrics['month_num'], 2)} "
                f"Year: {round(self.metrics['ann_return'] * 100, 2)}% "
                f"Calmar: {round(self.metrics['calmar_ratio'], 2)} "
                f"MD: {round(self.metrics['max_drawdown'] * 100, 2)}%",
                f"Sortino: {round(self.metrics['sortino_ratio'], 2)} "
                f"Sharpe: {round(self.metrics['sharpe_ratio'], 2)} "
                f"Turnover: {round(self.result_df['turnover'].sum(), 2)} "
                f"MD: {md_start_date} - {md_end_date}",
            ],
            loc="upper left",
            fontsize=11,
        )
        plt.plot(self.result_df.index, self.result_df["drawdown"], color="#ec700a")
        plt.fill_between(
            self.result_df.index,
            self.result_df["drawdown"],
            0,
            facecolor="#FF0000",
            alpha=0.1,
        )
        fig.autofmt_xdate()
        plt.grid(True)
        if save_path:
            plt.savefig(save_path, format="jpg", bbox_inches="tight", dpi=100)
        if show_plt:
            plt.show()

    def plot_score_perfs(self, gap: float = 0.01, num: int = 10) -> None:
        """Plot cumulative raw return by prediction-score bucket."""
        import matplotlib.pyplot as plt

        if self.result_df is None:
            raise ValueError("run_backtest() must be called before plot_score_perfs()")
        perf_df = pd.concat(
            [self.df[["prediction_score"]], self.result_df["raw_return"]], axis=1
        ).copy()
        plt.figure(figsize=(12, 8))
        for i in range(num):
            min_threshold = 1 - num * gap + i * gap
            max_threshold = min_threshold + gap
            self._plot_score_perf(perf_df, min_threshold, max_threshold)
        plt.title("Performance by Score Threshold")
        plt.xlabel("Date")
        plt.ylabel("Cum Return")
        plt.legend()
        plt.tight_layout()
        plt.show()

    @staticmethod
    def _plot_score_perf(
        perf_df: pd.DataFrame,
        min_threshold: float,
        max_threshold: float,
    ) -> None:
        import matplotlib.pyplot as plt

        mask = (perf_df["prediction_score"] >= min_threshold) & (
            perf_df["prediction_score"] < max_threshold
        )
        masked_returns = pd.Series(
            np.where(mask, perf_df["raw_return"], 0.0),
            index=perf_df.index,
        )
        cumsum_series = (1.0 + masked_returns).cumprod() - 1.0
        label_text = f"{min_threshold:.2f}-{max_threshold:.2f}"
        (line,) = plt.plot(perf_df.index, cumsum_series, label=label_text)
        last_x = perf_df.index[-1]
        last_y = cumsum_series[-1]
        plt.text(
            last_x,
            last_y,
            f"  {label_text}",
            color=line.get_color(),
            fontsize=8,
            verticalalignment="center",
        )


__all__ = [
    "DEFAULT_POSITION_MAPPING",
    "DEFAULT_TS_COMMISSION",
    "DEFAULT_TS_DELAY",
    "DEFAULT_TS_SLIPPAGE",
    "TimeSeriesBacktester",
    "TimeSeriesConfig",
    "signal_to_single_asset_weights",
]
