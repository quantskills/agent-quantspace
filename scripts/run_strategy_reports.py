"""Generate strategy example reports from local PandaData Parquet files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from skills.backtest import (
    VectorBacktester,
    activity_metrics,
    annual_return_metrics,
    benchmark_return_corr,
)
from skills.report import (
    ReportFigure,
    ReportTable,
    ResearchReport,
    charts,
    write_research_bundle,
    write_research_catalog,
)
from skills.store.data_manager import DataManager
from skills.store.workspace import resolve_workspace_paths
from strategies.cross_sectional.ml_rank import expanding_pca_model_weights
from strategies.cross_sectional.rules import ma_gap_reversal_weights
from strategies.time_series.ml import xgboost_triple_barrier_weights
from strategies.time_series.rules import ma_reversion_atr_stop_weights

WORKSPACE_PATHS = resolve_workspace_paths()
PUBLIC_NAMESPACE = "strategy_examples"
REPRODUCE_COMMAND = "uv run python -m scripts.run_strategy_reports"
FREQUENCY = "1d"
RULE_FUTURE_SYMBOLS = [
    "CFFEX.IF99",
    "CFFEX.IC99",
    "CFFEX.IM99",
    "SHFE.CU99",
    "SHFE.RB99",
    "SHFE.AL99",
    "DCE.I99",
    "DCE.M99",
    "DCE.Y99",
    "CZCE.TA99",
    "CZCE.MA99",
    "CZCE.CF99",
    "INE.SC99",
]
ML_FUTURE_SYMBOLS = ["CFFEX.IF99", "SHFE.AG99", "SHFE.AU99", "SHFE.CU99", "DCE.Y99", "CZCE.MA99"]
CSI300_FUTURE_SYMBOL = "CFFEX.IF99"
GOLD_FUTURE_SYMBOL = "SHFE.AU99"


def _run_vector_backtest(panel, weights, *, start_date: str):
    return VectorBacktester(
        data=panel,
        trade_at="close",
        signal_lag=0,
        commission=0.0002,
        slippage_bp=2.0,
        start_date=start_date,
    ).run(weights)


def _common_metrics(result_df, base_metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        **base_metrics,
        **annual_return_metrics(result_df),
        **activity_metrics(result_df),
    }


def _sample_range(result_df: pd.DataFrame) -> tuple[str, str]:
    if result_df.empty:
        raise ValueError("result_df is empty; cannot fill sample_start/sample_end")
    index = pd.to_datetime(result_df.index)
    return str(index.min().date()), str(index.max().date())


def _recent_rows_table(result_df: pd.DataFrame) -> ReportTable | None:
    columns = [
        column
        for column in ["return", "raw_return", "cum_return", "drawdown", "turnover"]
        if column in result_df.columns
    ]
    if not columns or result_df.empty:
        return None
    view = result_df[columns].tail(5).copy()
    view.insert(0, "Date", pd.to_datetime(view.index).strftime("%Y-%m-%d"))
    return ReportTable(
        name="recent_rows",
        caption="Recent result rows",
        frame=view.reset_index(drop=True),
    )


def _public_example(
    *,
    slug: str,
    title: str,
    domain: str,
    strategy_type: str,
    label: str,
    description: str,
    universe: list[str],
    metrics: dict[str, Any],
    result_df: pd.DataFrame,
    notes: list[str],
) -> ResearchReport:
    sample_start, sample_end = _sample_range(result_df)
    png = charts.plot_backtest_performance(result_df, title=f"{title} Performance")
    tables = []
    recent = _recent_rows_table(result_df)
    if recent is not None:
        tables.append(recent)
    return ResearchReport(
        namespace=PUBLIC_NAMESPACE,
        slug=slug,
        title=title,
        question=description,
        universe=list(universe),
        frequency=FREQUENCY,
        sample_start=sample_start,
        sample_end=sample_end,
        in_sample_end=None,
        out_of_sample_start=None,
        hypothesis=description,
        method_notes=list(notes),
        execution={
            "trade_at": "close",
            "signal_lag": 0,
            "commission": 0.0002,
            "slippage_bp": 2.0,
            "strategy_type": strategy_type,
            "label": label,
        },
        metrics=metrics,
        metrics_source="BacktestResult.metrics",
        figures=[
            ReportFigure(name="equity", caption="Equity and drawdown", png=png)
        ],
        tables=tables,
        caveats=["Public example only; not a live trading recommendation."],
        next_steps=[
            f"Re-run with `{REPRODUCE_COMMAND}` after refreshing local Parquet files."
        ],
        reproduce_command=REPRODUCE_COMMAND,
        visibility="public_example",
        domain=domain,
        kind="public_example",
        tags=[domain, strategy_type],
    )


def _futures_cross_sectional_reversal(dm: DataManager) -> ResearchReport:
    panel = dm.read_symbols([*RULE_FUTURE_SYMBOLS, GOLD_FUTURE_SYMBOL], frequency=FREQUENCY)
    close = panel["close"].unstack(level="symbol").sort_index()
    tradable_panel = panel.loc[panel.index.get_level_values("symbol").isin(RULE_FUTURE_SYMBOLS)]
    weights = ma_gap_reversal_weights(
        close,
        RULE_FUTURE_SYMBOLS,
        lookback=120,
        top_n=2,
        vol_lookback=60,
        rebalance_days=3,
    )
    execution = _run_vector_backtest(tradable_panel, weights, start_date="2024-01-01")
    metrics = _common_metrics(execution.result_df, execution.metrics)
    metrics["gold_return_corr"] = benchmark_return_corr(
        execution.result_df,
        close[GOLD_FUTURE_SYMBOL],
    )
    return _public_example(
        slug="futures_cross_sectional_reversal",
        title="Futures Cross-Sectional Reversal",
        domain="cross_sectional",
        strategy_type="Rule-based futures",
        label="none",
        description=(
            "A non-precious futures rotation example. It ranks stock-index, industrial, "
            "agricultural, and energy futures by 120-day moving-average gap reversal "
            "strength, then holds the two most stretched contracts with risk-parity weights."
        ),
        universe=list(RULE_FUTURE_SYMBOLS),
        metrics=metrics,
        result_df=execution.result_df,
        notes=[
            "Uses PandaData dominant futures daily bars stored under data/market/1d/.",
            "Precious metals are excluded from the tradable universe so the result is not a disguised gold trend.",
            "Signal is the negative distance from the 120-day moving average; larger values are more mean-reversion stretched.",
            "The top two contracts are rebalanced every three trading days with 60-day risk-parity weights.",
            "Weights are run through the shared vectorized VectorBacktester with zero signal lag and forward close-to-close returns.",
            "Transaction cost assumptions are commission 2bp plus slippage 2bp.",
        ],
    )


def _csi300_if_ma10_atr_reversion(dm: DataManager) -> ResearchReport:
    panel = dm.read_symbols([CSI300_FUTURE_SYMBOL], frequency=FREQUENCY)
    bars = panel.xs(CSI300_FUTURE_SYMBOL, level="symbol")
    weights = ma_reversion_atr_stop_weights(
        bars,
        symbol=CSI300_FUTURE_SYMBOL,
        ma_lookback=10,
        atr_lookback=14,
        atr_multiplier=2.0,
    )
    execution = _run_vector_backtest(panel, weights, start_date="2024-01-01")
    return _public_example(
        slug="csi300_if_ma10_atr_reversion",
        title="CSI 300 IF MA10 ATR Reversion",
        domain="time_series",
        strategy_type="Rule-based futures",
        label="none",
        description=(
            "A single-instrument time-series rule example that holds CFFEX CSI 300 "
            "index futures when price is below its 10-day moving average, with an ATR "
            "trailing stop controlling exits."
        ),
        universe=[CSI300_FUTURE_SYMBOL],
        metrics=_common_metrics(execution.result_df, execution.metrics),
        result_df=execution.result_df,
        notes=[
            "Uses PandaData CFFEX.IF99 dominant CSI 300 index futures daily bars stored under data/market/1d/.",
            "Report window starts on 2024-01-01, matching the local IF parameter sweep window.",
            "Entry rule: hold IF when close is below MA10.",
            "Exit rule: leave the position when close falls below the highest price since entry minus 2.0 times ATR(14).",
            "Weights are run through the shared vectorized VectorBacktester with zero signal lag and forward close-to-close returns.",
            "Transaction cost assumptions are commission 2bp plus slippage 2bp.",
        ],
    )


def _csi300_if_xgboost_triple_barrier(dm: DataManager) -> ResearchReport:
    panel = dm.read_symbols([CSI300_FUTURE_SYMBOL], frequency=FREQUENCY)
    bars = panel.xs(CSI300_FUTURE_SYMBOL, level="symbol")
    weights = xgboost_triple_barrier_weights(
        bars,
        symbol=CSI300_FUTURE_SYMBOL,
        split_date="2024-01-01",
        diff_lookback=2,
        label_l=3,
        label_pt_sl=0.8,
        label_t_limit=2,
        threshold=0.10,
    )
    execution = _run_vector_backtest(panel, weights, start_date="2024-01-01")
    return _public_example(
        slug="csi300_if_xgboost_triple_barrier",
        title="CSI 300 IF XGBoost Triple-Barrier",
        domain="time_series",
        strategy_type="XGBoost futures",
        label="triple-barrier",
        description=(
            "A real-data time-series ML example. XGBoost classifies triple-barrier states "
            "from log-difference and price/volume features on CFFEX.IF99, then takes "
            "long or short IF exposure when the corresponding barrier probability is high."
        ),
        universe=[CSI300_FUTURE_SYMBOL],
        metrics=_common_metrics(execution.result_df, execution.metrics),
        result_df=execution.result_df,
        notes=[
            "Label is generated by TripleBarrierLabelMaker with L=3, pt_sl=0.8, t_limit=2.",
            "Model is XGBoost multi-class classification with strategy-domain log-difference features plus public price/volume factors.",
            "Training uses rows before 2024-01-01; reports show the held-out period.",
            "Signal is the predicted positive-minus-negative barrier probability spread; absolute spread above 0.10 opens a position.",
            "Weights are run through the shared vectorized VectorBacktester with zero signal lag and forward close-to-close returns.",
        ],
    )


def _futures_xgboost_rank(dm: DataManager) -> ResearchReport:
    panel = dm.read_symbols(ML_FUTURE_SYMBOLS, frequency=FREQUENCY)
    weights = expanding_pca_model_weights(
        panel,
        model="xgboost",
        horizon=20,
        top_n=2,
        weighting="risk_parity",
    )
    execution = _run_vector_backtest(panel, weights, start_date="2024-01-01")
    return _public_example(
        slug="futures_xgboost_rank",
        title="Futures XGBoost Rank",
        domain="cross_sectional",
        strategy_type="XGBoost futures",
        label="rank label",
        description=(
            "A real-data cross-sectional ML example. XGBoost predicts each future's "
            "forward-return rank label and allocates to the top two predicted ranks "
            "with risk-parity weights."
        ),
        universe=list(ML_FUTURE_SYMBOLS),
        metrics=_common_metrics(execution.result_df, execution.metrics),
        result_df=execution.result_df,
        notes=[
            "Label is the percentile rank of 20-day forward return within the real futures universe.",
            "Features are LogDiff OHLC features reduced with train-only StandardScaler + PCA(50).",
            "Training uses expanding walk-forward folds with purge equal to the label horizon.",
            "Weights are run through the shared vectorized VectorBacktester with zero signal lag and forward close-to-close returns.",
        ],
    )


def build_reports(data_root: str | Path | None = None) -> list[ResearchReport]:
    dm = DataManager(data_root=str(data_root) if data_root is not None else None)
    return [
        _futures_cross_sectional_reversal(dm),
        _futures_xgboost_rank(dm),
        _csi300_if_ma10_atr_reversion(dm),
        _csi300_if_xgboost_triple_barrier(dm),
    ]


def generate_reports(
    data_root: str | Path | None = None,
    reports_root: str | Path | None = None,
    report_dir: str | Path | None = None,
) -> list[Path]:
    if report_dir is not None:
        namespace_dir = Path(report_dir)
        root = namespace_dir.parent
    else:
        root = (
            Path(reports_root)
            if reports_root is not None
            else WORKSPACE_PATHS.reports_root
        )
        namespace_dir = root / PUBLIC_NAMESPACE
    namespace_dir.mkdir(parents=True, exist_ok=True)

    reports = build_reports(data_root)
    stale_names = {"index.html", "README.md"}
    for report in reports:
        stale_names.update({f"{report.slug}.html", f"{report.slug}.md"})
    for name in sorted(stale_names):
        stale_path = namespace_dir / name
        if stale_path.exists():
            stale_path.unlink()

    index_paths: list[Path] = []
    for report in reports:
        study_dir = write_research_bundle(report, reports_root=root)
        png = report.figures[0].png if report.figures else None
        if png:
            (namespace_dir / f"{report.slug}_performance.png").write_bytes(png)
        index_paths.append(study_dir / "index.html")
    write_research_catalog(root)
    return index_paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        default=None,
        help="Data root containing market/1d Parquet files (default: workspace data/).",
    )
    args = parser.parse_args()
    paths = generate_reports(data_root=args.data_root)
    print("Generated strategy reports:")
    for path in paths:
        print(path.relative_to(WORKSPACE_PATHS.workspace_root))


if __name__ == "__main__":
    main()
