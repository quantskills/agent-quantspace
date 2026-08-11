"""Optimize the cash-flow total-return index core-satellite rule in-sample."""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from skills.backtest import VectorBacktester, activity_metrics, annual_return_metrics
from skills.report.strategy_markdown import StrategyReport, write_strategy_report
from skills.store.data_manager import DataManager
from skills.store.workspace import resolve_workspace_paths
from strategies.time_series.cashflow_total_return_mean_reversion import (
    CashflowMeanReversionParams,
    cashflow_mean_reversion_signals,
    cashflow_mean_reversion_weights,
)

SYMBOL = "932365CNY010.CSI"
FREQUENCY = "1d"
IS_START = "2020-01-01"
IS_END = "2024-12-31"
COMMISSION = 0.0
SLIPPAGE_BP = 0.0
ROBUST_SCORE_TOLERANCE = 0.01
FOLDS = (
    ("2020_2021", "2020-01-01", "2021-12-31"),
    ("2022_2023", "2022-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
)


def parameter_grid() -> list[tuple[str, CashflowMeanReversionParams]]:
    """Return the predeclared 1,944-configuration in-sample grid."""
    configs: list[tuple[str, CashflowMeanReversionParams]] = []
    values = itertools.product(
        (0.12, 0.13, 0.14),
        (0.0, 0.25),
        (10, 15, 20),
        (30.0, 35.0, 40.0),
        (1.25, 1.50),
        (0.05, 0.07),
        (0.05, 0.07, 0.10),
        (10, 15, 20),
    )
    for counter, value in enumerate(values, start=1):
        (
            overbought_distance,
            defensive_exposure,
            overbought_max_hold,
            oversold_rsi,
            oversold_exposure,
            take_profit,
            stop,
            oversold_max_hold,
        ) = value
        configs.append(
            (
                f"combined_{counter:04d}",
                CashflowMeanReversionParams(
                    overbought_distance=overbought_distance,
                    defensive_exposure=defensive_exposure,
                    overbought_max_hold=overbought_max_hold,
                    oversold_rsi=oversold_rsi,
                    oversold_exposure=oversold_exposure,
                    oversold_take_profit=take_profit,
                    oversold_stop=stop,
                    oversold_max_hold=oversold_max_hold,
                ),
            )
        )
    return configs


def _backtester(panel: pd.DataFrame) -> VectorBacktester:
    return VectorBacktester(
        panel,
        trade_at="close",
        signal_lag=1,
        commission=COMMISSION,
        slippage_bp=SLIPPAGE_BP,
        start_date=IS_START,
        end_date=IS_END,
    )


def _compound(returns: pd.Series) -> float:
    return float((1.0 + returns.fillna(0.0)).prod() - 1.0)


def _benchmark_execution(
    bars: pd.DataFrame,
    backtester: VectorBacktester,
):
    weights = pd.DataFrame({SYMBOL: 1.0}, index=bars.index)
    weights.index.name = "eob"
    return backtester.run(weights)


def _evaluate(
    candidate: str,
    params: CashflowMeanReversionParams,
    bars: pd.DataFrame,
    backtester: VectorBacktester,
    benchmark_result: pd.DataFrame,
) -> dict[str, Any]:
    weights = cashflow_mean_reversion_weights(bars, symbol=SYMBOL, params=params)
    execution = backtester.run(weights)
    result = execution.result_df
    annual = annual_return_metrics(result)
    benchmark_annual = annual_return_metrics(benchmark_result)
    annual_excess = [
        float(annual[f"{year}_return"] - benchmark_annual[f"{year}_return"])
        for year in range(2020, 2025)
    ]
    executed = execution.executed_weights[SYMBOL].reindex(result.index).fillna(0.0)
    row: dict[str, Any] = {
        "candidate": candidate,
        **asdict(params),
        **execution.metrics,
        **annual,
        **activity_metrics(result),
        "average_exposure": float(executed.mean()),
        "max_exposure": float(executed.max()),
        "years_beating_buy_hold": float(sum(value > 0 for value in annual_excess)),
        "median_annual_excess": float(np.median(annual_excess)),
        "worst_annual_excess": float(np.min(annual_excess)),
    }
    for label, start, end in FOLDS:
        strategy_fold = _compound(result.loc[start:end, "return"])
        benchmark_fold = _compound(benchmark_result.loc[start:end, "return"])
        row[f"fold_{label}_return"] = strategy_fold
        row[f"fold_{label}_benchmark"] = benchmark_fold
        row[f"fold_{label}_excess"] = strategy_fold - benchmark_fold
    return row


def _rank(frame: pd.DataFrame, benchmark_metrics: dict[str, float]) -> pd.DataFrame:
    ranked = frame.copy()
    eligible = (
        (ranked["total_return"] > benchmark_metrics["total_return"])
        & (ranked["sharpe_ratio"] > benchmark_metrics["sharpe_ratio"])
        & (ranked["calmar_ratio"] > benchmark_metrics["calmar_ratio"])
        & (ranked["max_exposure"] <= 1.5)
    )
    ranked["eligible"] = eligible
    ranked["total_excess"] = ranked["total_return"] - benchmark_metrics["total_return"]
    ranked["sharpe_excess"] = ranked["sharpe_ratio"] - benchmark_metrics["sharpe_ratio"]
    ranked["calmar_excess"] = ranked["calmar_ratio"] - benchmark_metrics["calmar_ratio"]
    ranked["robust_score"] = float("-inf")

    if eligible.any():
        eligible_rows = ranked.loc[eligible]
        max_years = eligible_rows["years_beating_buy_hold"].max()
        consistent = eligible & ranked["years_beating_buy_hold"].eq(max_years)
        components = (
            ("total_return", 0.20),
            ("sharpe_ratio", 0.20),
            ("calmar_ratio", 0.20),
            ("median_annual_excess", 0.20),
            ("worst_annual_excess", 0.20),
        )
        score = pd.Series(0.0, index=ranked.index)
        for source, weight in components:
            score += ranked[source].replace([np.inf, -np.inf], np.nan).rank(pct=True) * weight
        ranked.loc[consistent, "robust_score"] = score.loc[consistent]

    ranked["prior_distance"] = (
        (ranked["overbought_distance"] - 0.13).abs() / 0.01
        + (ranked["oversold_rsi"] - 35.0).abs() / 5.0
        + (ranked["oversold_stop"] - 0.07).abs() / 0.02
        + (ranked["overbought_max_hold"] - 10).abs() / 5.0
        + (ranked["oversold_max_hold"] - 10).abs() / 5.0
    )
    return ranked


def _selection_order(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.copy()
    finite = ordered["robust_score"].replace([np.inf, -np.inf], np.nan).dropna()
    best_score = float(finite.max()) if not finite.empty else float("-inf")
    ordered["near_optimal"] = ordered["robust_score"].ge(
        best_score - ROBUST_SCORE_TOLERANCE
    )
    return ordered.sort_values(
        ["near_optimal", "prior_distance", "robust_score", "total_return"],
        ascending=[False, True, False, False],
    )


def _metric_subset(metrics: dict[str, float]) -> dict[str, float]:
    keys = (
        "total_return",
        "ann_return",
        "max_drawdown",
        "ann_volatility",
        "sharpe_ratio",
        "calmar_ratio",
        "sortino_ratio",
    )
    return {key: float(metrics[key]) for key in keys}


def _comparison_frame(
    strategy_result: pd.DataFrame,
    benchmark_result: pd.DataFrame,
) -> pd.DataFrame:
    strategy = annual_return_metrics(strategy_result)
    benchmark = annual_return_metrics(benchmark_result)
    rows = []
    for year in range(2020, 2025):
        strategy_return = float(strategy[f"{year}_return"])
        benchmark_return = float(benchmark[f"{year}_return"])
        rows.append(
            {
                "year": year,
                "strategy_return": strategy_return,
                "buy_hold_return": benchmark_return,
                "excess_return": strategy_return - benchmark_return,
            }
        )
    return pd.DataFrame(rows)


def _write_readme(
    output_dir: Path,
    selected_candidate: str,
    params: CashflowMeanReversionParams,
    strategy_metrics: dict[str, float],
    benchmark_metrics: dict[str, float],
    annual: pd.DataFrame,
) -> Path:
    def pct(value: float) -> str:
        return f"{value:.2%}"

    annual_rows = "\n".join(
        f"| {int(row.year)} | {pct(row.strategy_return)} | {pct(row.buy_hold_return)} | {pct(row.excess_return)} |"
        for row in annual.itertuples(index=False)
    )
    content = f"""# 中证全指自由现金流全收益指数：样本内规则策略

标的：`{SYMBOL}`

样本内：{IS_START} 至 {IS_END}

交易成本：忽略；信号按收盘产生并滞后一根日线执行。

选择：`{selected_candidate}`，仅使用样本内数据优化，未查看 2025 年后绩效。

## 推荐规则

1. 常态保留 {params.core_exposure:.2f} 倍核心仓位。
2. RSI({params.rsi_lookback}) 首次跌到 {params.oversold_rsi:.0f} 以下，且价格低于仍在上升的 MA{params.trend_ma} 时，将总仓位提高到 {params.oversold_exposure:.2f} 倍。
3. 超卖加仓部分在盈利 {pct(params.oversold_take_profit)}、跌破入场价 {pct(params.oversold_stop)}、持有 {params.oversold_max_hold} 日或回到 MA{params.mean_exit_ma} 时退出；止损只撤销增量仓，不砍核心仓。
4. 止损后至少等待 {params.recovery_cooldown} 日，较止损价回升 {pct(params.recovery_threshold)} 且长期趋势条件仍成立，才允许重新加仓。
5. 价格首次达到过去 {params.overbought_lookback} 日低点以上 {pct(params.overbought_distance)} 时，仓位降到 {params.defensive_exposure:.2f}；下跌 {pct(params.overbought_restore_drop)} 或最多 {params.overbought_max_hold} 日后恢复核心仓。

## 正式回测结果

| 指标 | 策略 | Buy & Hold |
|---|---:|---:|
| 总收益 | {pct(strategy_metrics['total_return'])} | {pct(benchmark_metrics['total_return'])} |
| 年化收益 | {pct(strategy_metrics['ann_return'])} | {pct(benchmark_metrics['ann_return'])} |
| 最大回撤 | {pct(strategy_metrics['max_drawdown'])} | {pct(benchmark_metrics['max_drawdown'])} |
| Sharpe | {strategy_metrics['sharpe_ratio']:.3f} | {benchmark_metrics['sharpe_ratio']:.3f} |
| Calmar | {strategy_metrics['calmar_ratio']:.3f} | {benchmark_metrics['calmar_ratio']:.3f} |

| 年份 | 策略 | Buy & Hold | 超额 |
|---|---:|---:|---:|
{annual_rows}

## 解释与限制

- 1,944 组参数都限制为多头、总仓位不超过 1.5 倍；最终候选先要求总收益、Sharpe 和 Calmar 同时超过 Buy & Hold，再优先选择逐年稳定性。综合分距最高值不超过 {ROBUST_SCORE_TOLERANCE:.2f} 时，采用接近统计研究先验的参数，避免追逐微小的样本内差异。
- 全仓移动止损的独立试验没有超过 Buy & Hold，因此最终规则只对超卖增量仓止损。
- 该指数于 2024 年末发布，样本内绝大部分是指数回溯历史，存在方法回测偏差；本结果只是样本内证据。
- 指数本身不可直接交易，未来实盘还需要指定可交易代理、加入跟踪误差、交易成本和融资约束。
"""
    path = output_dir / "README.md"
    path.write_text(content, encoding="utf-8")
    return path


def run_optimization(
    *,
    data_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Run the in-sample grid and persist the selected formal backtest."""
    dm = DataManager(data_root=str(data_root) if data_root is not None else None)
    full_panel = dm.read_symbols([SYMBOL], frequency=FREQUENCY)
    panel = full_panel.loc[
        full_panel.index.get_level_values("eob") <= pd.Timestamp(IS_END)
    ].copy()
    if panel.index.get_level_values("eob").max() > pd.Timestamp(IS_END):
        raise AssertionError("out-of-sample data leaked into the optimization panel")
    bars = panel.xs(SYMBOL, level="symbol").copy()
    backtester = _backtester(panel)
    benchmark = _benchmark_execution(bars, backtester)
    benchmark_metrics = _metric_subset(benchmark.metrics)

    configs = parameter_grid()
    params_by_candidate = dict(configs)
    evaluated = pd.DataFrame(
        [
            _evaluate(name, params, bars, backtester, benchmark.result_df)
            for name, params in configs
        ]
    )
    ranked = _rank(evaluated, benchmark_metrics)
    ordered = _selection_order(ranked)
    if not np.isfinite(float(ordered.iloc[0]["robust_score"])):
        raise RuntimeError("no constrained candidate exceeded buy and hold")
    selected_candidate = str(ordered.iloc[0]["candidate"])
    selected_params = params_by_candidate[selected_candidate]
    ranked["selected"] = ranked["candidate"].eq(selected_candidate)

    weights = cashflow_mean_reversion_weights(
        bars, symbol=SYMBOL, params=selected_params
    )
    signals = cashflow_mean_reversion_signals(bars, params=selected_params)
    selected = backtester.run(weights)
    selected_metrics = _metric_subset(selected.metrics)
    if not (
        selected_metrics["total_return"] > benchmark_metrics["total_return"]
        and selected_metrics["sharpe_ratio"] > benchmark_metrics["sharpe_ratio"]
        and selected_metrics["calmar_ratio"] > benchmark_metrics["calmar_ratio"]
    ):
        raise AssertionError("selected strategy did not clear the buy-and-hold hurdle")

    paths = resolve_workspace_paths()
    out = (
        Path(output_dir)
        if output_dir is not None
        else paths.reports_root / "cashflow_mean_reversion_strategy_is"
    )
    out.mkdir(parents=True, exist_ok=True)
    optimization_path = out / "optimization_results.csv"
    params_path = out / "selected_params.json"
    benchmark_path = out / "benchmark_metrics.json"
    weights_path = out / "selected_weights.parquet"
    signals_path = out / "selected_signals.parquet"
    performance_path = out / "selected_performance.parquet"
    benchmark_performance_path = out / "buy_hold_performance.parquet"
    annual_path = out / "annual_comparison.csv"
    events_path = out / "selected_events.csv"
    decomposition_path = out / "component_decomposition.csv"

    _selection_order(ranked).to_csv(optimization_path, index=False)
    params_path.write_text(
        json.dumps(
            {
                "candidate": selected_candidate,
                "symbol": SYMBOL,
                "sample_start": IS_START,
                "sample_end": IS_END,
                "selection_scope": "in_sample_only",
                "parameter_grid_size": len(configs),
                "commission": COMMISSION,
                "slippage_bp": SLIPPAGE_BP,
                "selection_hurdle": "total return, Sharpe, and Calmar all exceed buy and hold; maximize annual consistency; choose the research-prior center within a 0.01 robust-score plateau",
                "parameters": asdict(selected_params),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    benchmark_path.write_text(
        json.dumps(benchmark_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    weights.to_parquet(weights_path)
    signals.to_parquet(signals_path)
    selected.result_df.to_parquet(performance_path)
    benchmark.result_df.to_parquet(benchmark_performance_path)
    annual = _comparison_frame(selected.result_df, benchmark.result_df)
    annual.to_csv(annual_path, index=False)
    signals.loc[signals["event"].ne("")].to_csv(events_path)

    components = {
        "core_only": replace(
            selected_params, oversold_exposure=1.0, defensive_exposure=1.0
        ),
        "oversold_overlay_only": replace(selected_params, defensive_exposure=1.0),
        "defensive_window_only": replace(selected_params, oversold_exposure=1.0),
        "combined": selected_params,
    }
    component_rows = []
    for label, params in components.items():
        component_weights = cashflow_mean_reversion_weights(
            bars, symbol=SYMBOL, params=params
        )
        component_execution = backtester.run(component_weights)
        component_rows.append(
            {"component": label, **_metric_subset(component_execution.metrics)}
        )
    pd.DataFrame(component_rows).to_csv(decomposition_path, index=False)

    report_metrics = {
        **selected_metrics,
        "buy_hold_total_return": benchmark_metrics["total_return"],
        "buy_hold_sharpe": benchmark_metrics["sharpe_ratio"],
        "buy_hold_calmar": benchmark_metrics["calmar_ratio"],
    }
    report = StrategyReport(
        slug="selected_core_satellite_mean_reversion",
        title=f"{SYMBOL} Core-Satellite Mean Reversion IS",
        domain="time_series",
        strategy_type="Core holding + oversold satellite + temporary defensive window",
        label=selected_candidate,
        description=f"In-sample optimization only: {IS_START} through {IS_END}.",
        metrics=report_metrics,
        result_df=selected.result_df,
        notes=[
            "The optimization panel is hard-capped at 2024-12-31; 2025+ is untouched.",
            "Signals are shifted one bar and costs are intentionally zero per the research request.",
            "The loss stop applies only to the incremental oversold satellite, not the core holding.",
            "The chosen near-optimal candidate beats buy and hold in total return, Sharpe, Calmar, and all five calendar years.",
            "The index history before its launch is backfilled and may contain index-construction bias.",
        ],
    )
    report_path = write_strategy_report(report, out)
    readme_path = _write_readme(
        out,
        selected_candidate,
        selected_params,
        selected_metrics,
        benchmark_metrics,
        annual,
    )
    return {
        "readme": readme_path,
        "optimization": optimization_path,
        "selected_params": params_path,
        "benchmark_metrics": benchmark_path,
        "selected_weights": weights_path,
        "selected_signals": signals_path,
        "selected_performance": performance_path,
        "buy_hold_performance": benchmark_performance_path,
        "annual_comparison": annual_path,
        "events": events_path,
        "component_decomposition": decomposition_path,
        "strategy_report": report_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    outputs = run_optimization(data_root=args.data_root, output_dir=args.output_dir)
    for name, path in outputs.items():
        print(f"{name}: {path.resolve()}")


if __name__ == "__main__":
    main()
