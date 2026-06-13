"""Time-series statistical analysis toolkit.

Combines KDE/QQ distribution analysis with stationarity tests (Hurst, ADF, KPSS).
All plotting dependencies are lazily imported.
"""

import logging
import os
import time
import warnings
from collections.abc import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _import_matplotlib():
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    return plt, mdates


def _import_seaborn():
    import seaborn as sns

    return sns


def _import_signal_stats():
    from scipy import signal, stats

    return signal, stats


def _import_statsmodels():
    from scipy.stats import linregress
    from statsmodels.tools.sm_exceptions import InterpolationWarning
    from statsmodels.tsa.stattools import adfuller, kpss

    return adfuller, kpss, linregress, InterpolationWarning


def _import_sm_api():
    import statsmodels.api as sm

    return sm


def _import_joblib():
    from joblib import Parallel, delayed

    return Parallel, delayed


def ensure_dir_and_get_path(base_path, suffix=""):
    full_path = f"{os.path.splitext(base_path)[0]}{suffix}"
    dir_path = os.path.dirname(full_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    return full_path


def kde_analysis(price, plot_title="", plot_path=None, ax=None, show=True):
    """KDE analysis of log-return distributions across lags."""
    plt, _ = _import_matplotlib()
    sns = _import_seaborn()
    signal, stats = _import_signal_stats()

    plot_lags = [1, 2, 3, 4, 5, 7, 9, 13, 21, 34]
    result_lags = range(1, 35)

    is_new_figure = ax is None
    if is_new_figure:
        plt.figure(figsize=(14, 6))
        ax = plt.gca()

    analysis_results = {}

    for lag in result_lags:
        returns = np.log(price).diff(lag).dropna()
        standard_returns = (returns - returns.mean()) / returns.std()

        kde = stats.gaussian_kde(standard_returns)
        x_grid = np.linspace(-5, 5, 1000)
        density = kde(x_grid)

        peak_index = np.argmax(density)
        peak_x = x_grid[peak_index]
        peak_height = density[peak_index]

        kurtosis = peak_height
        skewness = peak_x

        stat_kurtosis = stats.kurtosis(standard_returns)
        stat_skewness = stats.skew(standard_returns)

        if kurtosis > 0.5:
            tail_feature = "fat_tail"
        elif kurtosis < -0.5:
            tail_feature = "thin_tail"
        else:
            tail_feature = "near_normal"
        if skewness > 0.2:
            skew_feature = "right_skew"
        elif skewness < -0.2:
            skew_feature = "left_skew"
        else:
            skew_feature = "symmetric"

        peaks, _ = signal.find_peaks(density, height=0.01)
        num_peaks = len(peaks)

        analysis_results[lag] = {
            "peak_height": kurtosis,
            "peak_position": peak_x,
            "num_peaks": num_peaks,
            "tail_feature": tail_feature,
            "skew_feature": skew_feature,
            "statistical_kurtosis": stat_kurtosis,
            "statistical_skewness": stat_skewness,
        }

    for lag in plot_lags:
        result = analysis_results[lag]
        kurtosis = result["peak_height"]
        peak_x = result["peak_position"]
        num_peaks = result["num_peaks"]
        tail_feature = result["tail_feature"]
        skew_feature = result["skew_feature"]

        returns = np.log(price).diff(lag).dropna()
        standard_returns = (returns - returns.mean()) / returns.std()

        label = (
            f"lag={lag} (peak={kurtosis:.2f}, pos={peak_x:.2f}, peaks={num_peaks}, "
            f"{tail_feature}, {skew_feature})"
        )
        sns.kdeplot(standard_returns, label=label, alpha=0.7, ax=ax)

    normal_sample = np.random.normal(size=1000000)
    normal_kurtosis = stats.kurtosis(normal_sample)
    normal_skewness = stats.skew(normal_sample)

    sns.kdeplot(
        normal_sample,
        label=f"normal (kurtosis~{normal_kurtosis:.2f}, skew~{normal_skewness:.2f})",
        color="black",
        linestyle="--",
        ax=ax,
    )

    ax.set_title(f"{plot_title} return distribution (KDE)", fontsize=12)
    ax.set_xlim(-5, 5)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize="small")

    if plot_path and is_new_figure:
        save_path = ensure_dir_and_get_path(plot_path, "_kde_dist.png")
        plt.savefig(save_path)

    if show and is_new_figure:
        plt.show()

    return analysis_results, ax


def qq_analysis(price, plot_title="", plot_path=None, ax=None, show=True):
    """QQ plots of log returns vs normal for selected lags."""
    plt, _ = _import_matplotlib()
    _, stats = _import_signal_stats()

    plot_lags = [1, 2, 3, 4, 5, 7, 9, 13, 21, 34]
    result_lags = range(1, 35)

    is_new_figure = ax is None
    if is_new_figure:
        plt.figure(figsize=(10, 8))
        ax = plt.gca()

    colors = plt.cm.tab10.colors
    legend_info = []

    x = np.linspace(-3, 3, 100)
    ax.plot(x, x, "k-", linewidth=1.5, alpha=0.6, label="theoretical normal line")

    analysis_results = {}

    for lag in result_lags:
        returns = np.log(price).diff(lag).dropna()
        standard_returns = (returns - returns.mean()) / returns.std()

        kurtosis = stats.kurtosis(standard_returns)
        skewness = stats.skew(standard_returns)

        theoretical_quantiles = np.sort(np.random.normal(0, 1, len(standard_returns)))
        ordered_vals = np.sort(standard_returns)

        qq_deviation = np.sqrt(np.mean((theoretical_quantiles - ordered_vals) ** 2))

        analysis_results[lag] = {
            "kurtosis": kurtosis,
            "skewness": skewness,
            "qq_deviation": qq_deviation,
        }

    for i, lag in enumerate(plot_lags):
        kurtosis = analysis_results[lag]["kurtosis"]
        skewness = analysis_results[lag]["skewness"]

        returns = np.log(price).diff(lag).dropna()
        standard_returns = (returns - returns.mean()) / returns.std()

        theoretical_quantiles = np.sort(np.random.normal(0, 1, len(standard_returns)))
        ordered_vals = np.sort(standard_returns)

        color = colors[i % len(colors)]
        ax.scatter(theoretical_quantiles, ordered_vals, s=1, alpha=0.7, color=color, marker="o")

        legend_info.append(f"lag={lag} (kurtosis={kurtosis:.2f}, skew={skewness:.2f})")

    ax.grid(True, alpha=0.3)
    ax.set_title(f"{plot_title} QQ plot — log returns by lag", fontsize=12)
    ax.set_xlabel("theoretical quantiles (standard normal)", fontsize=10)
    ax.set_ylabel("sample quantiles", fontsize=10)

    ax.legend(["theoretical line"] + legend_info, fontsize="small", loc="upper left")

    if plot_path and is_new_figure:
        save_path = ensure_dir_and_get_path(plot_path, "_qq_plot.png")
        plt.savefig(save_path, bbox_inches="tight")

    if show and is_new_figure:
        plt.show()

    return analysis_results, ax


def analysis_results_to_df(analysis_results: dict):
    all_lags = sorted(analysis_results["kde"].keys())

    rows = []
    for lag in all_lags:
        row = {"lag": lag}

        if lag in analysis_results["kde"]:
            for key, value in analysis_results["kde"][lag].items():
                row[f"kde_{key}"] = value

        row["price_length"] = analysis_results["price_length"]

        rows.append(row)

    df = pd.DataFrame(rows).set_index("lag")
    return df


def ts_analysis(price, plot_title="", plot_path=None, show=True, save_csv=False):
    """Run KDE summary plot (and optional CSV export)."""
    plt, _ = _import_matplotlib()

    fig, ax = plt.subplots(1, 1, figsize=(12, 6))

    analysis_results = {"price_length": len(price)}

    kde_results, _ = kde_analysis(price, plot_title, ax=ax, show=False)
    analysis_results["kde"] = kde_results

    if plot_title:
        fig.suptitle(f"{plot_title} time-series summary, bars={len(price)}", fontsize=16)

    fig.tight_layout(rect=[0, 0, 1, 0.97])

    if show:
        plt.show()

    if plot_path:
        save_path = ensure_dir_and_get_path(plot_path, "_kde.png")
        plt.savefig(save_path, bbox_inches="tight", dpi=150)
        if save_csv:
            kde_csv_path = ensure_dir_and_get_path(plot_path, "_kde.csv")
            analysis_results_to_df(analysis_results).to_csv(kde_csv_path)
            logger.info("KDE results saved to %s", kde_csv_path)

    return fig, ax


def _period_ts_analysis(price, period, period_index):
    try:
        period_price = price if period == "1min" else price.resample(period).last().dropna()

        n_points = len(period_price)
        if n_points < 200:
            logger.warning("period %s: insufficient points (%s)", period, n_points)

        analysis_results = {"price_length": len(period_price)}
        kde_results, _ = kde_analysis(period_price, f"{period} ", ax=None, show=False)
        analysis_results["kde"] = kde_results

        return {
            "period": period,
            "index": period_index,
            "success": True,
            "error": None,
            "data": {
                "period_price": period_price,
                "n_points": n_points,
                "analysis_results": analysis_results,
            },
        }

    except Exception as e:
        logger.exception("period %s analysis failed: %s", period, e)
        return {
            "period": period,
            "index": period_index,
            "success": False,
            "error": str(e),
            "data": None,
        }


def ts_groupby_period(
    price: pd.Series,
    periods=None,
    save_path=None,
    show=True,
):
    """Multi-frequency KDE analysis with optional aggregate CSV export."""
    if periods is None:
        periods = ["1min", "5min", "15min", "1h", "4h", "1d"]

    plt, _ = _import_matplotlib()
    Parallel, delayed = _import_joblib()

    plot_path = None
    csv_path = None

    start_time = time.time()
    logger.info("Starting multi-period analysis for %s periods", len(periods))

    results = Parallel(n_jobs=-1)(
        delayed(_period_ts_analysis)(price, period, i) for i, period in enumerate(periods)
    )

    results.sort(key=lambda x: x["index"])

    fig = plt.figure(figsize=(20, 8 * len(periods)), constrained_layout=False)
    gs = fig.add_gridspec(nrows=len(periods), ncols=1)

    parallel_time = time.time() - start_time
    logger.info("Parallel segment analysis done in %.2fs", parallel_time)

    analysis_types = ["kde"]
    combined_results = {}

    for result in results:
        period = result["period"]
        i = result["index"]

        if result["success"]:
            period_gs = gs[i].subgridspec(nrows=1, ncols=2)
            axes = np.array([fig.add_subplot(period_gs[0, col]) for col in range(2)])

            period_price = result["data"]["period_price"]
            n_points = result["data"]["n_points"]
            analysis_results = result["data"]["analysis_results"]

            title = f"{period} "
            kde_analysis(period_price, title, ax=axes[0], show=False)

            sub_title = f"{period} summary, bars={n_points}"
            axes[0].text(
                0.5,
                1.1,
                sub_title,
                ha="center",
                va="bottom",
                transform=axes[0].transAxes,
                fontsize=14,
                fontweight="bold",
            )

            for analysis_type in analysis_types:
                if analysis_type in analysis_results:
                    for lag, lag_results in analysis_results[analysis_type].items():
                        key = (period, lag)

                        if key not in combined_results:
                            combined_results[key] = {
                                "period": period,
                                "lag": lag,
                                "period_lag": f"{period}_{lag}",
                            }

                        for metric_key, metric_value in lag_results.items():
                            combined_results[key][f"{analysis_type}_{metric_key}"] = metric_value

        else:
            period_gs = gs[i].subgridspec(nrows=1, ncols=1)
            error_ax = fig.add_subplot(period_gs[0, 0])
            error_ax.text(
                0.5,
                0.5,
                f"{period} analysis failed:\n{result['error']}",
                ha="center",
                va="center",
                fontsize=16,
            )
            error_ax.axis("off")

    fig.suptitle("Multi-period time-series characteristics (KDE)", fontsize=24, y=0.99)

    plt.tight_layout(rect=[0, 0, 1, 0.98])

    if save_path:
        PATH_POSTFIX = "_groupby_period_ts"
        save_path_prev = os.path.splitext(save_path)[0]
        plot_path = f"{save_path_prev}{PATH_POSTFIX}.png"
        csv_path = f"{save_path_prev}{PATH_POSTFIX}.csv"

        plt.savefig(plot_path, bbox_inches="tight", dpi=150)
        logger.info("Figure saved to %s", plot_path)

        if combined_results:
            df = pd.DataFrame(list(combined_results.values()))
            df = df.set_index("period_lag")
            df = df.sort_values(["period", "lag"])

            cols = ["period", "lag"]
            for analysis_type in analysis_types:
                type_cols = [col for col in df.columns if col.startswith(f"{analysis_type}_")]
                cols.extend(sorted(type_cols))

            cols = [col for col in cols if col in df.columns]

            df[cols].to_csv(csv_path)
            logger.info("Combined results saved to %s", csv_path)

    if show:
        plt.show()

    total_time = time.time() - start_time
    logger.info("All periods done in %.2fs", total_time)

    return fig, plot_path, csv_path


class TimeSeriesAnalyzer:
    """Analyze a time series with Hurst, ADF, and KPSS (series-based API)."""

    def __init__(self, series: pd.Series):
        self.series = series.dropna()
        self.data = self.series.to_frame()
        self.results = {}

    def calculate_hurst(
        self,
        min_lag: int = 10,
        max_lag: int = 100,
        series: pd.Series | None = None,
    ) -> float:
        _, _, linregress, _ = _import_statsmodels()

        s = self.series if series is None else series.dropna()
        max_lag = min(max_lag, len(s) // 2)

        if max_lag < min_lag:
            logger.warning(
                "series length %s too short for hurst at min_lag=%s; returning nan",
                len(s),
                min_lag,
            )
            return np.nan

        log_returns = np.log(s).diff().dropna()

        if len(log_returns) <= max_lag:
            logger.warning(
                "log-return length %s insufficient for max_lag=%s; returning nan",
                len(log_returns),
                max_lag,
            )
            return np.nan

        lags = range(min_lag, max_lag + 1)
        lag_used: list[int] = []
        rs_values: list[float] = []

        for lag in lags:
            rs = []
            for i in range(len(log_returns) - lag + 1):
                segment = log_returns.iloc[i : i + lag]
                deviations = segment - segment.mean()
                cumulative = deviations.cumsum()
                range_ = cumulative.max() - cumulative.min()
                std_ = segment.std()
                if std_ != 0:
                    rs.append(range_ / std_)
            if not rs:
                continue
            lag_used.append(lag)
            rs_values.append(float(np.mean(rs)))

        if len(rs_values) < 3:
            logger.warning("only %s R/S points for hurst regression; returning nan", len(rs_values))
            return np.nan

        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("error")
                slope, _, _, _, _ = linregress(
                    np.log(np.asarray(lag_used, dtype=float)),
                    np.log(np.asarray(rs_values, dtype=float)),
                )
                return slope
        except Exception as e:
            logger.warning("hurst regression failed: %s; returning nan", e)
            return np.nan

    def run_adf_test(self, series: pd.Series | None = None) -> dict[str, float | int]:
        adfuller, _, _, _ = _import_statsmodels()

        s = self.series if series is None else series
        s = s.dropna()
        result = adfuller(s, autolag="AIC")
        return {
            "statistic": result[0],
            "pvalue": result[1],
            "lags": result[2],
            "critical_values": result[4],
        }

    def run_kpss_test(
        self,
        regression: str = "ct",
        suppress_warnings: bool = True,
        series: pd.Series | None = None,
    ) -> dict[str, float | dict[str, float] | str | None]:
        _, kpss, _, InterpolationWarning = _import_statsmodels()

        s = self.series if series is None else series
        s = s.dropna()

        if suppress_warnings:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = kpss(s, regression=regression)

                warning_msg = None
                for warning in w:
                    if isinstance(warning.message, InterpolationWarning):
                        warning_msg = str(warning.message)
        else:
            result = kpss(s, regression=regression)
            warning_msg = None

        return {
            "statistic": result[0],
            "pvalue": result[1],
            "critical_values": result[3],
            "warning": warning_msg,
        }

    def analyze_windows(
        self,
        windows: list[int],
        min_lag_func: Callable[[int], int] = lambda w: max(5, w // 6),
        max_lag_func: Callable[[int], int] = lambda w: max(10, w // 3),
        drop_na: bool = True,
        suppress_warnings: bool = True,
    ) -> None:
        _ = drop_na

        for window in windows:
            try:
                min_lag = min_lag_func(window)
                max_lag = max_lag_func(window)

                logger.info("window=%s min_lag=%s max_lag=%s", window, min_lag, max_lag)
                window_data = self.series.iloc[-window:]

                window_max_lag = min(max_lag, len(window_data) // 2)
                if window_max_lag < min_lag:
                    logger.warning("window %s too small for min_lag=%s; skipping", window, min_lag)
                    continue

                hurst = self.calculate_hurst(min_lag, window_max_lag, series=window_data)
                adf_result = self.run_adf_test(series=window_data)
                kpss_result = self.run_kpss_test(
                    regression="ct",
                    suppress_warnings=suppress_warnings,
                    series=window_data,
                )

                self.results[window] = {
                    "hurst": hurst,
                    "adf": adf_result,
                    "kpss": kpss_result,
                    "min_lag": min_lag,
                    "window_max_lag": window_max_lag,
                }

                self._print_results(window)

            except Exception as e:
                logger.exception("window %s failed: %s", window, e)
                continue

    def _print_results(self, window: int) -> None:
        res = self.results[window]

        logger.info(
            "window=%s min_lag=%s max_lag=%s",
            window,
            res["min_lag"],
            res["window_max_lag"],
        )
        if np.isnan(res["hurst"]):
            logger.info("hurst=nan")
        else:
            logger.info("hurst=%.4f", res["hurst"])

        adf_p = res["adf"]["pvalue"]
        adf_interpretation = "non-stationary" if adf_p > 0.05 else "stationary"
        logger.info("ADF p-value=%.4f (%s)", adf_p, adf_interpretation)

        kpss_p = res["kpss"]["pvalue"]
        kpss_interpretation = "non-stationary" if kpss_p < 0.05 else "stationary"
        kpss_warning = res["kpss"]["warning"]

        if kpss_warning:
            if "smaller" in kpss_warning:
                kpss_p_note = f"(warning: true p-value < {kpss_p:.4f})"
            elif "greater" in kpss_warning:
                kpss_p_note = f"(warning: true p-value > {kpss_p:.4f})"
            else:
                kpss_p_note = "(warning: p-value interpolation uncertain)"

            logger.info(
                "KPSS p-value=%.4f (%s) %s",
                kpss_p,
                kpss_interpretation,
                kpss_p_note,
            )
        else:
            logger.info("KPSS p-value=%.4f (%s)", kpss_p, kpss_interpretation)

        score = self._calculate_trend_score(res)
        logger.info("trend_fit_score=%s/5", score)

        trend_type = self._classify_trend_type(res)
        logger.info("trend_type=%s", trend_type)

    def _calculate_trend_score(self, res: dict) -> int:
        if np.isnan(res["hurst"]):
            return 0

        score = 0

        if res["hurst"] > 0.6:
            score += 2
        elif res["hurst"] > 0.55:
            score += 1

        if res["adf"]["pvalue"] > 0.05:
            score += 1

        if res["kpss"]["pvalue"] < 0.05:
            score += 1

        if res["hurst"] > 0.55 and res["adf"]["pvalue"] > 0.05 and res["kpss"]["pvalue"] < 0.05:
            score += 1

        return min(score, 5)

    def _classify_trend_type(self, res: dict) -> str:
        if np.isnan(res["hurst"]):
            return "undetermined (hurst failed)"

        hurst = res["hurst"]
        adf_p = res["adf"]["pvalue"]
        kpss_p = res["kpss"]["pvalue"]

        if hurst > 0.55 and adf_p > 0.05 and kpss_p < 0.05:
            return "strong trend, non-stationary (trend strategies)"
        if hurst > 0.55 and adf_p < 0.05 and kpss_p > 0.05:
            return "trending but stationary (short-term trend possible)"
        if hurst < 0.5 and adf_p < 0.05 and kpss_p > 0.05:
            return "mean-reverting stationary (weak for trend)"
        if hurst > 0.55 and adf_p > 0.05 and kpss_p > 0.05:
            return "conflicting signals (verify further)"
        return "weak trend or counter-trend"

    def get_results_dataframe(self) -> pd.DataFrame:
        columns = [
            "window_size",
            "hurst",
            "adf_pvalue",
            "kpss_pvalue",
            "trend_score",
            "trend_type",
            "min_lag",
            "effective_max_lag",
            "kpss_warning",
        ]
        results_df = pd.DataFrame(columns=columns)

        for window, res in self.results.items():
            score = self._calculate_trend_score(res)
            trend_type = self._classify_trend_type(res)
            kpss_warning = res["kpss"]["warning"]

            if kpss_warning:
                if "smaller" in kpss_warning:
                    kpss_warning_simplified = "true p-value may be smaller"
                elif "greater" in kpss_warning:
                    kpss_warning_simplified = "true p-value may be larger"
                else:
                    kpss_warning_simplified = "p-value estimate uncertain"
            else:
                kpss_warning_simplified = ""

            results_df = pd.concat(
                [
                    results_df,
                    pd.DataFrame(
                        {
                            "window_size": [window],
                            "hurst": [res["hurst"]],
                            "adf_pvalue": [res["adf"]["pvalue"]],
                            "kpss_pvalue": [res["kpss"]["pvalue"]],
                            "trend_score": [score],
                            "trend_type": [trend_type],
                            "min_lag": [res["min_lag"]],
                            "effective_max_lag": [res["window_max_lag"]],
                            "kpss_warning": [kpss_warning_simplified],
                        }
                    ),
                ],
                ignore_index=True,
            )

        return results_df


def analyze_time_series(
    series: pd.Series,
    windows: list[int] = None,
    min_lag_func: Callable[[int], int] = lambda w: max(5, w // 6),
    max_lag_func: Callable[[int], int] = lambda w: max(10, w // 3),
    drop_na: bool = True,
    suppress_warnings: bool = True,
    display_results: bool = True,
) -> pd.DataFrame:
    """Run windowed stationarity analysis and return a summary DataFrame."""
    if windows is None:
        windows = [20, 40, 60]

    analyzer = TimeSeriesAnalyzer(series)
    analyzer.analyze_windows(windows, min_lag_func, max_lag_func, drop_na, suppress_warnings)

    results_df = analyzer.get_results_dataframe()

    if display_results:
        try:
            from IPython.display import display

            logger.info("summary:")
            display(results_df)
        except ImportError:
            logger.info("summary:\n%s", results_df.to_csv(sep="\t", na_rep="nan"))

    return results_df


def analyze_time_series_yearly(
    file_path: str,
    dt_column: str = "datetime",
    close_column: str = "close",
    windows: list[int] = None,
    min_lag_func: Callable[[int], int] = lambda w: max(5, w // 6),
    max_lag_func: Callable[[int], int] = lambda w: max(10, w // 3),
    drop_na: bool = True,
    suppress_warnings: bool = True,
    display_results: bool = True,
) -> pd.DataFrame:
    """Run per-year windowed analysis on a CSV with datetime and close columns."""
    if windows is None:
        windows = [10, 30, 60]

    data = pd.read_csv(file_path)
    data[dt_column] = pd.to_datetime(data[dt_column])
    data["year"] = data[dt_column].dt.year
    start_year = data["year"].min()
    end_year = data["year"].max()

    all_results = []
    for year in sorted(data["year"].unique()):
        logger.info("year=%s", year)

        year_data = data[data["year"] == year]

        if len(year_data) < min(windows):
            continue

        close_series = year_data[close_column].reset_index(drop=True)
        analyzer = TimeSeriesAnalyzer(close_series)

        valid_windows = [w for w in windows if w <= len(year_data)]

        analyzer.analyze_windows(
            valid_windows, min_lag_func, max_lag_func, drop_na, suppress_warnings
        )

        if analyzer.results:
            year_results = analyzer.get_results_dataframe()
            year_results["start_year"] = start_year
            year_results["end_year"] = end_year
            year_results["year"] = year
            all_results.append(year_results)

    if len(all_results) == 0:
        raise ValueError("insufficient data for yearly analysis")

    final_results = pd.concat(all_results, ignore_index=True)

    if display_results:
        try:
            from IPython.display import display

            logger.info("yearly summary:")
            display(final_results)
        except ImportError:
            logger.info("yearly summary:\n%s", final_results.to_csv(sep="\t", na_rep="nan"))

    return final_results


def engle_granger_cointegration(
    y: pd.Series,
    x: pd.Series,
    significance: float = 0.05,
) -> dict:
    """Engle-Granger two-step cointegration test.

    Regresses y on x via OLS (with intercept), then applies ADF to residuals.
    If residuals are stationary, (y, x) are cointegrated.
    """
    adfuller, _, _, _ = _import_statsmodels()
    sm = _import_sm_api()

    aligned = pd.concat([y, x], axis=1, join="inner").dropna()
    if aligned.shape[0] < 20:
        raise ValueError(f"need at least 20 aligned observations, got {aligned.shape[0]}")
    y_aligned = aligned.iloc[:, 0]
    x_aligned = aligned.iloc[:, 1]

    X = sm.add_constant(x_aligned.values)
    ols = sm.OLS(y_aligned.values, X).fit()
    alpha = float(ols.params[0])
    beta = float(ols.params[1])
    residuals = pd.Series(ols.resid, index=aligned.index, name="residual")

    adf = adfuller(residuals.values, autolag="AIC")
    adf_stat = float(adf[0])
    adf_pvalue = float(adf[1])
    adf_lags = int(adf[2])
    adf_crit = {k: float(v) for k, v in adf[4].items()}

    return {
        "alpha": alpha,
        "beta": beta,
        "residuals": residuals,
        "adf_statistic": adf_stat,
        "adf_pvalue": adf_pvalue,
        "adf_lags": adf_lags,
        "adf_critical_values": adf_crit,
        "is_cointegrated": adf_pvalue < significance,
        "n_obs": int(aligned.shape[0]),
        "r_squared": float(ols.rsquared),
    }


def half_life_of_mean_reversion(spread: pd.Series) -> dict:
    """Half-life of mean reversion via AR(1) on first differences.

    Fits Δs_t = c + λ·s_{t-1} + u_t. Half-life = -ln(2) / λ (only meaningful when λ < 0).
    """
    sm = _import_sm_api()

    s = spread.dropna()
    if len(s) < 10:
        raise ValueError(f"need at least 10 observations, got {len(s)}")

    s_lag = s.shift(1).dropna()
    delta_s = s.diff().dropna()
    aligned = pd.concat([delta_s, s_lag], axis=1, join="inner").dropna()
    aligned.columns = ["delta_s", "s_lag"]

    X = sm.add_constant(aligned["s_lag"].values)
    ols = sm.OLS(aligned["delta_s"].values, X).fit()
    constant = float(ols.params[0])
    lam = float(ols.params[1])
    lam_pvalue = float(ols.pvalues[1])

    if lam < 0:
        half_life_bars = float(-np.log(2) / lam)
        is_mean_reverting = True
    else:
        half_life_bars = float("inf")
        is_mean_reverting = False

    return {
        "lambda": lam,
        "constant": constant,
        "lambda_pvalue": lam_pvalue,
        "half_life_bars": half_life_bars,
        "is_mean_reverting": is_mean_reverting,
        "n_obs": int(aligned.shape[0]),
    }
