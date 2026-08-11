"""Optimize prior cash-flow strategy families on 2014-2023 and test 2024+."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from skills.backtest import VectorBacktester, activity_metrics, annual_return_metrics
from skills.store.data_manager import DataManager
from skills.store.workspace import resolve_workspace_paths
from strategies.time_series.cashflow_donchian_atr import (
    DonchianAtrParams,
    donchian_atr_weights,
)
from strategies.time_series.cashflow_total_return_mean_reversion import (
    CashflowMeanReversionParams,
    cashflow_mean_reversion_weights,
)
from strategies.time_series.cashflow_trend import CashflowTrendParams, cashflow_trend_weights
from strategies.time_series.cashflow_vol_recovery import (
    VolRecoveryParams,
    cashflow_vol_recovery_weights,
)
from strategies.time_series.workflows.run_cashflow_donchian_atr_is import (
    core_configs as donchian_core_configs,
)
from strategies.time_series.workflows.run_cashflow_donchian_atr_is import (
    sizing_configs as donchian_sizing_configs,
)
from strategies.time_series.workflows.run_cashflow_total_return_mean_reversion_is import (
    parameter_grid as mean_reversion_configs,
)
from strategies.time_series.workflows.run_cashflow_trend_grid import sensitivity_configs
from strategies.time_series.workflows.run_cashflow_vol_recovery_is import (
    stage1_configs as vol_stage1_configs,
)
from strategies.time_series.workflows.run_cashflow_vol_recovery_is import (
    stage2_configs as vol_stage2_configs,
)

SYMBOL = "932365CNY010.CSI"
FREQUENCY = "1d"
IS_START = "2014-01-01"
IS_END = "2023-12-31"
OOS_START = "2024-01-01"
COMMISSION = 0.0
SLIPPAGE_BP = 0.0
FOLDS = (
    ("2014_2015", "2014-01-01", "2015-12-31"),
    ("2016_2017", "2016-01-01", "2017-12-31"),
    ("2018_2019", "2018-01-01", "2019-12-31"),
    ("2020_2021", "2020-01-01", "2021-12-31"),
    ("2022_2023", "2022-01-01", "2023-12-31"),
)

StrategyParams = (
    CashflowMeanReversionParams | DonchianAtrParams | VolRecoveryParams | CashflowTrendParams
)


def family_config_counts() -> dict[str, int]:
    """Return first-stage grid sizes without evaluating any market data."""
    return {
        "mean_reversion": len(mean_reversion_configs()),
        "donchian_atr_core": len(donchian_core_configs()),
        "vol_recovery_stage1": len(vol_stage1_configs()),
        "trend_breakout": len(sensitivity_configs()),
    }


def _backtester(
    panel: pd.DataFrame,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> VectorBacktester:
    return VectorBacktester(
        panel,
        trade_at="close",
        signal_lag=1,
        commission=COMMISSION,
        slippage_bp=SLIPPAGE_BP,
        start_date=start_date,
        end_date=end_date,
    )


def _weights(family: str, bars: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    if family == "mean_reversion":
        return cashflow_mean_reversion_weights(
            bars, symbol=SYMBOL, params=params  # type: ignore[arg-type]
        )
    if family == "donchian_atr":
        return donchian_atr_weights(bars, symbol=SYMBOL, params=params)  # type: ignore[arg-type]
    if family == "vol_recovery":
        return cashflow_vol_recovery_weights(
            bars, symbol=SYMBOL, params=params  # type: ignore[arg-type]
        )
    if family == "trend_breakout":
        return cashflow_trend_weights(bars, symbol=SYMBOL, params=params)  # type: ignore[arg-type]
    raise ValueError(f"unknown strategy family: {family}")


def _compound(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    return float((1.0 + returns.fillna(0.0)).prod() - 1.0)


def _benchmark_weights(bars: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame({SYMBOL: 1.0}, index=bars.index)
    result.index.name = "eob"
    return result


def _evaluation_row(
    *,
    family: str,
    candidate: str,
    params: StrategyParams,
    bars: pd.DataFrame,
    backtester: VectorBacktester,
    benchmark_result: pd.DataFrame,
) -> dict[str, Any]:
    execution = backtester.run(_weights(family, bars, params))
    result = execution.result_df
    executed = execution.executed_weights[SYMBOL].reindex(result.index).fillna(0.0)
    annual = annual_return_metrics(result)
    benchmark_annual = annual_return_metrics(benchmark_result)
    annual_excess = []
    row: dict[str, Any] = {
        "family": family,
        "candidate": candidate,
        **asdict(params),
        **execution.metrics,
        **activity_metrics(result),
        "entries": float(((executed > 0) & (executed.shift(1).fillna(0.0) <= 0)).sum()),
        "average_exposure": float(executed.mean()),
        "max_exposure": float(executed.max()),
    }
    for year in range(2014, 2024):
        strategy_return = float(annual.get(f"{year}_return", 0.0))
        benchmark_return = float(benchmark_annual.get(f"{year}_return", 0.0))
        row[f"{year}_return"] = strategy_return
        row[f"{year}_benchmark"] = benchmark_return
        row[f"{year}_excess"] = strategy_return - benchmark_return
        annual_excess.append(strategy_return - benchmark_return)
    row["years_beating_buy_hold"] = float(sum(value > 0 for value in annual_excess))
    row["median_annual_excess"] = float(np.median(annual_excess))
    row["worst_annual_excess"] = float(np.min(annual_excess))

    fold_excess = []
    for label, start, end in FOLDS:
        strategy_return = _compound(result.loc[start:end, "return"])
        benchmark_return = _compound(benchmark_result.loc[start:end, "return"])
        excess = strategy_return - benchmark_return
        row[f"fold_{label}_return"] = strategy_return
        row[f"fold_{label}_benchmark"] = benchmark_return
        row[f"fold_{label}_excess"] = excess
        fold_excess.append(excess)
    row["positive_excess_folds"] = float(sum(value > 0 for value in fold_excess))
    row["median_fold_excess"] = float(np.median(fold_excess))
    row["worst_fold_excess"] = float(np.min(fold_excess))
    return row


def rank_in_sample(frame: pd.DataFrame) -> pd.DataFrame:
    """Rank one strategy family using only IS performance and stability."""
    ranked = frame.copy()
    eligible = (
        ranked["max_drawdown"].gt(0.0)
        & ranked["trade_days"].ge(4.0)
        & ranked["total_return"].gt(-1.0)
    )
    ranked["eligible"] = eligible
    components = (
        ("calmar_ratio", 0.20),
        ("sharpe_ratio", 0.15),
        ("total_return", 0.10),
        ("median_fold_excess", 0.30),
        ("worst_fold_excess", 0.25),
    )
    score = pd.Series(0.0, index=ranked.index)
    for source, weight in components:
        score += (
            ranked[source]
            .replace([np.inf, -np.inf], np.nan)
            .rank(pct=True)
            .fillna(0.0)
            * weight
        )
    ranked["optimization_score"] = float("-inf")
    ranked.loc[eligible, "optimization_score"] = score.loc[eligible]
    return ranked.sort_values(
        ["optimization_score", "worst_fold_excess", "median_fold_excess"],
        ascending=False,
    )


def _evaluate_configs(
    *,
    family: str,
    configs: list[tuple[str, StrategyParams]],
    bars: pd.DataFrame,
    backtester: VectorBacktester,
    benchmark_result: pd.DataFrame,
) -> pd.DataFrame:
    rows = [
        _evaluation_row(
            family=family,
            candidate=name,
            params=params,
            bars=bars,
            backtester=backtester,
            benchmark_result=benchmark_result,
        )
        for name, params in configs
    ]
    return rank_in_sample(pd.DataFrame(rows))


def _metric_subset(execution) -> dict[str, float]:
    keys = (
        "total_return",
        "ann_return",
        "max_drawdown",
        "ann_volatility",
        "sharpe_ratio",
        "calmar_ratio",
        "sortino_ratio",
    )
    return {key: float(execution.metrics[key]) for key in keys}


def _annual_oos(execution, benchmark_execution) -> dict[str, float]:
    strategy = annual_return_metrics(execution.result_df)
    benchmark = annual_return_metrics(benchmark_execution.result_df)
    values: dict[str, float] = {}
    for year in range(2024, execution.result_df.index.max().year + 1):
        strategy_return = float(strategy.get(f"{year}_return", 0.0))
        benchmark_return = float(benchmark.get(f"{year}_return", 0.0))
        values[f"oos_{year}_return"] = strategy_return
        values[f"oos_{year}_benchmark"] = benchmark_return
        values[f"oos_{year}_excess"] = strategy_return - benchmark_return
    return values


def _plot_oos(
    performances: dict[str, pd.DataFrame],
    benchmark: pd.DataFrame,
    output_path: Path,
) -> None:
    colors = {
        "mean_reversion": "#176B87",
        "donchian_atr": "#6A4C93",
        "vol_recovery": "#2A9D8F",
        "trend_breakout": "#D97706",
        "buy_hold": "#6B7280",
    }
    labels = {
        "mean_reversion": "Mean reversion combined",
        "donchian_atr": "Donchian + ATR",
        "vol_recovery": "Volatility + recovery",
        "trend_breakout": "Trend breakout",
    }
    fig, (equity_ax, drawdown_ax) = plt.subplots(
        2,
        1,
        figsize=(13, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    for family, result in performances.items():
        equity_ax.plot(
            result.index,
            result["equity"],
            color=colors[family],
            linewidth=1.6,
            label=labels[family],
        )
        drawdown_ax.plot(
            result.index,
            result["drawdown"],
            color=colors[family],
            linewidth=1.0,
        )
    equity_ax.plot(
        benchmark.index,
        benchmark["equity"],
        color=colors["buy_hold"],
        linewidth=1.5,
        linestyle="--",
        label="Buy & Hold",
    )
    drawdown_ax.plot(
        benchmark.index,
        benchmark["drawdown"],
        color=colors["buy_hold"],
        linewidth=1.0,
        linestyle="--",
    )
    equity_ax.set_title(f"{SYMBOL} — Locked OOS Performance ({OOS_START} onward)")
    equity_ax.set_ylabel("Equity")
    equity_ax.legend(loc="upper left", frameon=False, ncol=2)
    equity_ax.grid(True, alpha=0.25)
    drawdown_ax.set_ylabel("Drawdown")
    drawdown_ax.set_xlabel("Signal date")
    drawdown_ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _write_readme(
    output_path: Path,
    champions: pd.DataFrame,
    is_benchmark: dict[str, float],
    oos_benchmark: dict[str, float],
    latest_date: pd.Timestamp,
) -> None:
    rows = []
    for row in champions.itertuples(index=False):
        rows.append(
            f"| {row.family} | {row.candidate} | {row.is_total_return:.2%} | "
            f"{row.oos_total_return:.2%} | {row.oos_max_drawdown:.2%} | "
            f"{row.oos_sharpe_ratio:.3f} | {row.oos_total_excess:.2%} |"
        )
    table = "\n".join(rows)
    output_path.write_text(
        f"""# 932365CNY010.CSI：2014–2023 样本内、2024+ 样本外实验

样本内：{IS_START} 至 {IS_END}；样本外：{OOS_START} 至 {latest_date.date()}。

所有参数只根据样本内及五个连续两年折叠选择；样本外不参与排名。

收盘信号滞后一根日线执行，交易成本为 0。

| 策略族 | 样本内入选参数 | IS 总收益 | OOS 总收益 | OOS 最大回撤 | OOS Sharpe | OOS 超额 |
|---|---|---:|---:|---:|---:|---:|
{table}
| buy_hold | benchmark | {is_benchmark['total_return']:.2%} | {oos_benchmark['total_return']:.2%} | {oos_benchmark['max_drawdown']:.2%} | {oos_benchmark['sharpe_ratio']:.3f} | 0.00% |

样本内和样本外均使用中证全指自由现金流全收益指数本身。指数不可直接交易；本实验没有代理产品跟踪误差、融资成本和成交成本。
""",
        encoding="utf-8",
    )


def run_experiment(
    *,
    data_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Run IS-only family selection, then evaluate locked parameters on 2024+."""
    dm = DataManager(data_root=str(data_root) if data_root is not None else None)
    full_panel = dm.read_symbols([SYMBOL], frequency=FREQUENCY)
    is_panel = full_panel.loc[
        full_panel.index.get_level_values("eob") <= pd.Timestamp(IS_END)
    ].copy()
    if is_panel.index.get_level_values("eob").max() > pd.Timestamp(IS_END):
        raise AssertionError("out-of-sample observations entered the optimization panel")
    is_bars = is_panel.xs(SYMBOL, level="symbol").copy()
    full_bars = full_panel.xs(SYMBOL, level="symbol").copy()
    is_backtester = _backtester(is_panel, start_date=IS_START, end_date=IS_END)
    is_benchmark_execution = is_backtester.run(_benchmark_weights(is_bars))

    paths = resolve_workspace_paths()
    out = (
        Path(output_dir)
        if output_dir is not None
        else paths.reports_root / "cashflow_split_2014_2023"
    )
    out.mkdir(parents=True, exist_ok=True)

    results: dict[str, pd.DataFrame] = {}
    params_by_family: dict[str, dict[str, StrategyParams]] = {}

    mean_configs = mean_reversion_configs()
    params_by_family["mean_reversion"] = dict(mean_configs)
    results["mean_reversion"] = _evaluate_configs(
        family="mean_reversion",
        configs=mean_configs,
        bars=is_bars,
        backtester=is_backtester,
        benchmark_result=is_benchmark_execution.result_df,
    )

    donchian_first = donchian_core_configs()
    donchian_params: dict[str, StrategyParams] = dict(donchian_first)
    donchian_core = _evaluate_configs(
        family="donchian_atr",
        configs=donchian_first,
        bars=is_bars,
        backtester=is_backtester,
        benchmark_result=is_benchmark_execution.result_df,
    )
    donchian_second = donchian_sizing_configs(
        donchian_core, dict(donchian_first), top_core=10
    )
    donchian_params.update(dict(donchian_second))
    donchian_sizing = _evaluate_configs(
        family="donchian_atr",
        configs=donchian_second,
        bars=is_bars,
        backtester=is_backtester,
        benchmark_result=is_benchmark_execution.result_df,
    )
    results["donchian_atr"] = rank_in_sample(
        pd.concat([donchian_core, donchian_sizing], ignore_index=True)
    )
    params_by_family["donchian_atr"] = donchian_params

    vol_first = vol_stage1_configs()
    vol_params: dict[str, StrategyParams] = dict(vol_first)
    vol_stage1 = _evaluate_configs(
        family="vol_recovery",
        configs=vol_first,
        bars=is_bars,
        backtester=is_backtester,
        benchmark_result=is_benchmark_execution.result_df,
    )
    vol_second = vol_stage2_configs(vol_stage1, dict(vol_first), top_per_family=2)
    vol_params.update(dict(vol_second))
    vol_stage2 = _evaluate_configs(
        family="vol_recovery",
        configs=vol_second,
        bars=is_bars,
        backtester=is_backtester,
        benchmark_result=is_benchmark_execution.result_df,
    )
    results["vol_recovery"] = rank_in_sample(
        pd.concat([vol_stage1, vol_stage2], ignore_index=True)
    )
    params_by_family["vol_recovery"] = vol_params

    trend_configs = sensitivity_configs()
    params_by_family["trend_breakout"] = dict(trend_configs)
    results["trend_breakout"] = _evaluate_configs(
        family="trend_breakout",
        configs=trend_configs,
        bars=is_bars,
        backtester=is_backtester,
        benchmark_result=is_benchmark_execution.result_df,
    )

    selected: dict[str, tuple[str, StrategyParams]] = {}
    for family, frame in results.items():
        if not np.isfinite(float(frame.iloc[0]["optimization_score"])):
            raise RuntimeError(f"no eligible in-sample candidate for {family}")
        candidate = str(frame.iloc[0]["candidate"])
        selected[family] = (candidate, params_by_family[family][candidate])
        frame = frame.copy()
        frame["selected"] = frame["candidate"].eq(candidate)
        results[family] = frame
        frame.to_csv(out / f"{family}_optimization_results.csv", index=False)

    oos_backtester = _backtester(full_panel, start_date=OOS_START)
    oos_benchmark_execution = oos_backtester.run(_benchmark_weights(full_bars))
    champion_rows = []
    oos_performances: dict[str, pd.DataFrame] = {}
    selected_payload: dict[str, Any] = {}
    is_benchmark_metrics = _metric_subset(is_benchmark_execution)
    oos_benchmark_metrics = _metric_subset(oos_benchmark_execution)

    for family, (candidate, params) in selected.items():
        is_row = results[family].loc[results[family]["candidate"].eq(candidate)].iloc[0]
        full_weights = _weights(family, full_bars, params)
        oos_execution = oos_backtester.run(full_weights)
        oos_metrics = _metric_subset(oos_execution)
        annual_oos = _annual_oos(oos_execution, oos_benchmark_execution)
        champion_rows.append(
            {
                "family": family,
                "candidate": candidate,
                "is_optimization_score": float(is_row["optimization_score"]),
                "is_total_return": float(is_row["total_return"]),
                "is_ann_return": float(is_row["ann_return"]),
                "is_max_drawdown": float(is_row["max_drawdown"]),
                "is_sharpe_ratio": float(is_row["sharpe_ratio"]),
                "is_calmar_ratio": float(is_row["calmar_ratio"]),
                "is_positive_excess_folds": float(is_row["positive_excess_folds"]),
                "is_worst_fold_excess": float(is_row["worst_fold_excess"]),
                **{f"oos_{key}": value for key, value in oos_metrics.items()},
                "oos_total_excess": oos_metrics["total_return"]
                - oos_benchmark_metrics["total_return"],
                **annual_oos,
            }
        )
        selected_payload[family] = {
            "candidate": candidate,
            "parameters": asdict(params),
        }
        full_weights.to_parquet(out / f"{family}_selected_weights.parquet")
        oos_execution.result_df.to_parquet(out / f"{family}_oos_performance.parquet")
        oos_performances[family] = oos_execution.result_df

    champions = pd.DataFrame(champion_rows).sort_values(
        ["oos_total_return", "oos_sharpe_ratio"], ascending=False
    )
    champions_path = out / "family_champions_is_oos.csv"
    champions.to_csv(champions_path, index=False)
    oos_benchmark_execution.result_df.to_parquet(out / "buy_hold_oos_performance.parquet")
    params_path = out / "selected_params.json"
    params_path.write_text(
        json.dumps(
            {
                "symbol": SYMBOL,
                "in_sample": {"start": IS_START, "end": IS_END},
                "out_of_sample": {
                    "start": OOS_START,
                    "end": str(full_bars.index.max().date()),
                },
                "selection": "IS-only percentile score over return, Sharpe, Calmar, and five contiguous fold excess returns",
                "commission": COMMISSION,
                "slippage_bp": SLIPPAGE_BP,
                "families": selected_payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    benchmark_path = out / "benchmark_metrics.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "in_sample": is_benchmark_metrics,
                "out_of_sample": oos_benchmark_metrics,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    chart_path = out / "oos_family_comparison.png"
    _plot_oos(
        oos_performances,
        oos_benchmark_execution.result_df,
        chart_path,
    )
    readme_path = out / "README.md"
    _write_readme(
        readme_path,
        champions,
        is_benchmark_metrics,
        oos_benchmark_metrics,
        full_bars.index.max(),
    )
    return {
        "readme": readme_path,
        "champions": champions_path,
        "selected_params": params_path,
        "benchmark_metrics": benchmark_path,
        "oos_chart": chart_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    outputs = run_experiment(data_root=args.data_root, output_dir=args.output_dir)
    for name, path in outputs.items():
        print(f"{name}: {path.resolve()}")


if __name__ == "__main__":
    main()
