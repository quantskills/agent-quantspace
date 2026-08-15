"""Backtest the MA golden/death-cross rule and write an HTML research archive."""

from __future__ import annotations

from datetime import date

import matplotlib.pyplot as plt
import pandas as pd

from skills.backtest import VectorBacktester
from skills.compute.indicators import ma_cross
from skills.report import (
    ReportFigure,
    ReportTable,
    ResearchReport,
    charts,
    write_research_bundle,
    write_research_catalog,
)
from skills.store.data_manager import DataManager
from strategies.time_series.rules import ma_golden_death_cross_weights

SYMBOL = "SHSE.510300"
FREQUENCY = "1d_adj"
SHORT = 10
LONG = 60
ALT_SHORT = 5
ALT_LONG = 20
START_DATE = "2020-01-01"
NAMESPACE = "ma_cross"
SLUG = "shse510300_ma10_ma60"
REPRODUCE_COMMAND = "uv run python -m strategies.time_series.workflows.run_ma_cross_report"
EXECUTION = {
    "trade_at": "close",
    "signal_lag": 1,
    "commission": 0.0002,
    "slippage_bp": 2.0,
    "return_mode": "forward",
}


def _filter_panel(panel: pd.DataFrame, start_date: str = START_DATE) -> pd.DataFrame:
    dates = panel.index.get_level_values("eob")
    return panel.loc[dates >= pd.Timestamp(start_date)].sort_index()


def _sample_bounds(panel: pd.DataFrame) -> tuple[str, str]:
    dates = pd.to_datetime(panel.index.get_level_values("eob").unique())
    return str(dates.min().date()), str(dates.max().date())


def _backtester(panel: pd.DataFrame) -> VectorBacktester:
    return VectorBacktester(
        data=panel,
        trade_at=EXECUTION["trade_at"],
        signal_lag=EXECUTION["signal_lag"],
        commission=EXECUTION["commission"],
        slippage_bp=EXECUTION["slippage_bp"],
        start_date=START_DATE,
    )


def _metrics_frame(labeled: dict[str, dict]) -> pd.DataFrame:
    keys = sorted({key for metrics in labeled.values() for key in metrics})
    rows = []
    for key in keys:
        row = {"metric": key}
        for label, metrics in labeled.items():
            row[label] = metrics.get(key)
        rows.append(row)
    return pd.DataFrame(rows)


def _event_counts(bars: pd.DataFrame, short: int, long: int) -> pd.DataFrame:
    spread = ma_cross(bars, short=short, long=long)
    previous = spread.shift(1)
    golden = int(((previous <= 0) & (spread > 0)).sum())
    death = int(((previous >= 0) & (spread < 0)).sum())
    long_days = int((spread > 0).sum())
    return pd.DataFrame(
        [
            {"item": "golden_cross_count", "value": golden},
            {"item": "death_cross_count", "value": death},
            {"item": "long_days", "value": long_days},
            {"item": "sample_days", "value": int(spread.notna().sum())},
        ]
    )


def _plot_price_and_mas(bars: pd.DataFrame, short: int, long: int, title: str) -> bytes:
    close = bars["close"].astype(float)
    ma_short = close.rolling(short, min_periods=short).mean()
    ma_long = close.rolling(long, min_periods=long).mean()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(close.index, close, label="收盘价", linewidth=1.2, color="black")
    ax.plot(ma_short.index, ma_short, label=f"MA{short}", linewidth=1.1, color="steelblue")
    ax.plot(ma_long.index, ma_long, label=f"MA{long}", linewidth=1.1, color="darkorange")
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Price")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    return charts.fig_to_png(fig)


def run_report(*, data_manager: DataManager | None = None) -> dict:
    """Run the MA-cross backtest and write ``reports/ma_cross/shse510300_ma10_ma60``."""
    reader = data_manager or DataManager()
    panel = _filter_panel(reader.read_symbols([SYMBOL], frequency=FREQUENCY))
    sample_start, sample_end = _sample_bounds(panel)
    bars = panel.xs(SYMBOL, level="symbol").copy()
    bars.index = pd.to_datetime(bars.index)

    weights = ma_golden_death_cross_weights(bars, symbol=SYMBOL, short=SHORT, long=LONG)
    alt_weights = ma_golden_death_cross_weights(
        bars, symbol=SYMBOL, short=ALT_SHORT, long=ALT_LONG
    )
    buy_hold_weights = pd.DataFrame(1.0, index=weights.index, columns=weights.columns)

    bt = _backtester(panel)
    result = bt.run(weights)
    alt_result = bt.run(alt_weights)
    buy_hold = bt.run(buy_hold_weights)

    metrics = dict(result.metrics)
    comparison = _metrics_frame(
        {
            "ma10_ma60": metrics,
            "ma5_ma20": dict(alt_result.metrics),
            "buy_hold": dict(buy_hold.metrics),
        }
    )
    events = _event_counts(bars, SHORT, LONG)

    report = ResearchReport(
        namespace=NAMESPACE,
        slug=SLUG,
        title="沪深300ETF 均线金叉死叉",
        question=(
            "在 SHSE.510300 上，MA10 上穿 MA60 做多、下穿平仓，"
            "在给定交易成本下是否优于买入持有？"
        ),
        universe=[SYMBOL],
        frequency=FREQUENCY,
        sample_start=sample_start,
        sample_end=sample_end,
        in_sample_end=None,
        out_of_sample_start=None,
        hypothesis=(
            "短均线上穿长均线表示趋势转多，金叉后持有多头；"
            "短均线下穿长均线表示趋势转空，死叉后空仓等待下一次金叉。"
        ),
        method_notes=[
            "规则来自 strategies.time_series.rules.ma_golden_death_cross_weights。",
            "均线差值复用 skills.compute.indicators.ma_cross；仓位为 spread>0 时 +1，否则 0。",
            f"主参数 short={SHORT}、long={LONG}；对照参数 short={ALT_SHORT}、long={ALT_LONG}。",
            "价格使用 data/market/1d_adj 前复权日线，避免分红除权缺口干扰均线交叉。",
            "未做参数搜索；10/60 为教科书趋势跟踪组合。",
        ],
        execution=dict(EXECUTION),
        metrics=metrics,
        metrics_source="BacktestResult.metrics",
        figures=[
            ReportFigure(
                name="equity",
                caption="MA10/MA60 金叉死叉净值与回撤（含交易成本）",
                png=charts.plot_backtest_performance(
                    result.result_df,
                    title="沪深300ETF MA10/MA60 金叉死叉",
                ),
            ),
            ReportFigure(
                name="price_ma",
                caption="复权收盘价与 MA10、MA60",
                png=_plot_price_and_mas(
                    bars,
                    SHORT,
                    LONG,
                    title="SHSE.510300 收盘价与均线",
                ),
            ),
        ],
        tables=[
            ReportTable(
                name="cross_events",
                caption="样本内金叉、死叉次数与持仓天数",
                frame=events,
            ),
            ReportTable(
                name="strategy_vs_buy_hold_comparison",
                caption="对照：MA10/MA60、MA5/MA20 与买入持有（BacktestResult.metrics）",
                frame=comparison,
            ),
        ],
        caveats=[
            "单品种、单规则、全样本结果，不能外推到其他 ETF 或期货。",
            "未做样本外切分，也未对均线窗口做网格搜索。",
            "历史回测结果不代表未来收益，不构成交易建议。",
        ],
        next_steps=[
            "增加 2024 之后的样本外切分。",
            "补充佣金与滑点敏感性。",
            "比较金叉做多/死叉做空的多空版本。",
        ],
        reproduce_command=REPRODUCE_COMMAND,
        visibility="private",
        domain="time_series",
        kind="research",
        tags=["rule", "etf", "ma_cross"],
        as_of=date.today().isoformat(),
    )
    study_dir = write_research_bundle(report)
    catalog_path = write_research_catalog()
    return {
        "study_dir": study_dir,
        "catalog_path": catalog_path,
        "metrics": metrics,
        "sample_start": sample_start,
        "sample_end": sample_end,
    }


def main() -> None:
    summary = run_report()
    print(f"study_dir: {summary['study_dir']}")
    print(f"catalog: {summary['catalog_path']}")
    print(f"sample: {summary['sample_start']} – {summary['sample_end']}")
    for key, value in summary["metrics"].items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
