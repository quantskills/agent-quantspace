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
from skills.report.strategy_markdown import (
    StrategyReport,
    write_strategy_index,
    write_strategy_report,
)
from skills.store.data_manager import DataManager
from skills.store.workspace import resolve_workspace_paths
from strategies.cross_sectional.asset_class_rotation import (
    ASSET_CLASS_ETF_SYMBOLS,
    apply_asset_class_split_adjustments,
    asset_class_top3_weights,
)
from strategies.cross_sectional.ml_rank import xgboost_rank_weights
from strategies.cross_sectional.rules import ma_gap_reversal_weights
from strategies.time_series.ml import xgboost_triple_barrier_weights
from strategies.time_series.rules import ma_reversion_atr_stop_weights

WORKSPACE_PATHS = resolve_workspace_paths()
REPORT_DIR = WORKSPACE_PATHS.reports_root / "strategy_examples"
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
        return_mode="forward",
    ).run(weights)


def _common_metrics(result_df, base_metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        **base_metrics,
        **annual_return_metrics(result_df),
        **activity_metrics(result_df),
    }


def _global_asset_etf_top3(dm: DataManager) -> StrategyReport:
    panel = dm.read_symbols(list(ASSET_CLASS_ETF_SYMBOLS), frequency=FREQUENCY)
    panel = apply_asset_class_split_adjustments(panel)
    last_dates = panel.reset_index().groupby("symbol")["eob"].max()
    common_end = pd.Timestamp(last_dates.min())
    panel = panel.loc[panel.index.get_level_values("eob") <= common_end]
    available = set(panel.index.get_level_values("symbol"))
    missing = sorted(set(ASSET_CLASS_ETF_SYMBOLS).difference(available))
    if missing:
        raise ValueError(
            f"No overlapping asset-rotation history through {common_end.date()} "
            f"for configured symbols: {missing}"
        )
    close = panel["close"].unstack(level="symbol").sort_index()
    weights = asset_class_top3_weights(close)
    execution = _run_vector_backtest(panel, weights, start_date="2021-01-01")
    metrics = _common_metrics(execution.result_df, execution.metrics)
    metrics.update({"universe_size": 18.0, "top_n": 3.0})
    return StrategyReport(
        slug="global_asset_etf_top3",
        title="Global Asset ETF Top 3 Momentum Rotation",
        domain="cross_sectional",
        strategy_type="Rule-based listed-fund rotation",
        label="20/60/120-day composite momentum",
        description=(
            "A public large-asset rotation example across 18 listed ETF/LOF proxies. "
            "It ranks China and global equity indices, government bonds, gold, crude "
            "oil, soybean meal, nonferrous metals, and broad commodities, then holds "
            "the strongest Top 3 at equal weights."
        ),
        metrics=metrics,
        result_df=execution.result_df,
        notes=[
            "The explicit public universe is defined by strategies.cross_sectional.asset_class_rotation.ASSET_CLASS_ETF_UNIVERSE.",
            "Score is the equal-weight average of trailing 20-day, 60-day, and 120-day returns.",
            "The portfolio rebalances every 20 trading days into the Top 3 assets at equal target weights.",
            "A later-listed or later-imported proxy becomes eligible only after it has enough local history for all lookbacks.",
            f"The report ends on {common_end.date()}, the latest observation shared by all configured proxies.",
            "Raw-price share splits are forward-adjusted for SHSE.513100 (1:5), SHSE.513500 (1:2), and SHSE.510170 (1:4) before signals and returns are computed.",
            "SHSE.501018 and SZSE.164824 are exchange-listed LOF proxies for crude oil and Indian equities, not ETFs.",
            "SHSE.510170 is a broad-commodity producer-equity ETF, not a commodity-futures basket.",
            "Weights are run through the shared VectorBacktester with zero signal lag and forward close-to-close returns.",
            "Transaction cost assumptions are commission 2bp plus slippage 2bp.",
        ],
    )


def _futures_cross_sectional_reversal(dm: DataManager) -> StrategyReport:
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
    return StrategyReport(
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


def _csi300_if_ma10_atr_reversion(dm: DataManager) -> StrategyReport:
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
    return StrategyReport(
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


def _csi300_if_xgboost_triple_barrier(dm: DataManager) -> StrategyReport:
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
    return StrategyReport(
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


def _futures_xgboost_rank(dm: DataManager) -> StrategyReport:
    panel = dm.read_symbols(ML_FUTURE_SYMBOLS, frequency=FREQUENCY)
    weights = xgboost_rank_weights(panel, split_date="2024-01-01", horizon=60, top_n=2)
    execution = _run_vector_backtest(panel, weights, start_date="2024-01-01")
    return StrategyReport(
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
        metrics=_common_metrics(execution.result_df, execution.metrics),
        result_df=execution.result_df,
        notes=[
            "Label is the percentile rank of 60-day forward return within the real futures universe.",
            "Features are generic public momentum, volatility, trend, and mean-reversion factors.",
            "Training uses rows before 2024-01-01; reports show the held-out period.",
            "Weights are run through the shared vectorized VectorBacktester with zero signal lag and forward close-to-close returns.",
        ],
    )


def build_reports(data_root: str | Path | None = None) -> list[StrategyReport]:
    dm = DataManager(data_root=str(data_root) if data_root is not None else None)
    return [
        _futures_cross_sectional_reversal(dm),
        _futures_xgboost_rank(dm),
        _global_asset_etf_top3(dm),
        _csi300_if_ma10_atr_reversion(dm),
        _csi300_if_xgboost_triple_barrier(dm),
    ]


def generate_reports(
    data_root: str | Path | None = None,
    report_dir: str | Path | None = None,
) -> list[Path]:
    output_dir = Path(report_dir) if report_dir is not None else REPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    reports = build_reports(data_root)
    owned_names = {"README.md"}
    for report in reports:
        owned_names.update({f"{report.slug}.md", f"{report.slug}_performance.png"})
    for name in sorted(owned_names):
        stale_path = output_dir / name
        if stale_path.exists():
            stale_path.unlink()
    report_paths = [write_strategy_report(report, output_dir) for report in reports]
    index_path = write_strategy_index(reports, output_dir)
    return [index_path, *report_paths]


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
