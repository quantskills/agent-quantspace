"""Reproduce every empirical result used by Lesson 06.

Run:
    uv run python -m strategies.cross_sectional.workflows.run_lesson06_multifactor

Scenario example:
    uv run python -m strategies.cross_sectional.workflows.run_lesson06_multifactor \
      --output reports/lesson_06_multifactor_no_trend252_5bp \
      --exclude-factor trend252_skip22 --commission-bp 2 --slippage-bp 3
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from skills.analyze.factor_information import (
    compute_ic_information_surface,
    execution_forward_return_wide,
    factor_rank_autocorrelation,
    mean_daily_factor_rank_correlation,
    rank_ic_series,
    rolling_factor_rank_correlation,
    top_n_jaccard_overlap,
)
from skills.backtest import VectorBacktester
from skills.compute.indicators import (
    er,
    mom_skip,
    trend_score,
    trend_score_v2_skip,
)
from skills.compute.wrappers import Factor
from skills.report.charts import (
    plot_equity_comparison,
    plot_factor_weight_history,
    plot_horizon_ic,
    plot_ic_heatmap,
    plot_lagged_ic,
    plot_rebalance_comparison,
)
from skills.store.data_manager import DataManager
from skills.strategy.cross_sectional.factor_combination import (
    DynamicFactorWeightConfig,
    combine_factor_scores,
    orient_factor_frames,
    rank_factor_frames,
)
from skills.strategy.cross_sectional.selection import apply_rebalance_schedule
from strategies.cross_sectional.asset_class_rotation import (
    ASSET_CLASS_ETF_SYMBOLS,
    apply_asset_class_split_adjustments,
)
from strategies.cross_sectional.mined_factors.mean_reversion import mr_quantile_deviation
from strategies.cross_sectional.mined_factors.trend_momentum_revise2 import (
    tm2_breakout_persistence_momentum,
    tm2_trend_information_ratio,
)
from strategies.cross_sectional.mined_factors.volatility_risk_revise2 import (
    vr2_return_skew_risk_premium,
)
from strategies.cross_sectional.mined_factors.volume_liquidity import vl_up_day_volume_share

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "reports" / "lesson_06_multifactor"
START = "2019-01-02"
CALIBRATION_END = "2024-12-31"
OOS_START = "2025-01-02"
END = "2026-05-31"
HORIZONS = [1, 3, 5, 10, 20, 40, 60]
LAGS = [0, 1, 2, 3, 5, 10, 15, 20, 30, 40, 60]
REBALANCE_DAYS = [1, 3, 5, 10, 20]
SIGNAL_LAG = 1
COMMISSION = 0.0002
SLIPPAGE_BP = 3.0
BASELINE_REBALANCE_DAYS = 5
TOP_N = 3

FACTOR_SPECS = {
    "trend25": (trend_score, {"period": 25}, 1, "old_session", "25日趋势强度"),
    "trend22": (
        trend_score,
        {"period": 22},
        1,
        "compute_skill_user_added",
        "22日趋势评分",
    ),
    "mom_skip252_22": (
        mom_skip,
        {"total": 252, "skip": 22},
        1,
        "compute_skill_user_added",
        "12-1 跳月动量",
    ),
    "trend252_skip22": (
        trend_score_v2_skip,
        {"period": 252, "skip": 22},
        1,
        "old_session",
        "12-1 动量趋势",
    ),
    "er14": (er, {"period": 14}, 1, "old_session", "价格路径效率"),
    "quantile_reversion60": (
        mr_quantile_deviation,
        {"period": 60, "q": 0.5},
        -1,
        "formal_pool",
        "分位数偏离反转",
    ),
    "trend_ir25": (
        tm2_trend_information_ratio,
        {"period": 25},
        1,
        "formal_pool",
        "趋势信息比率",
    ),
    "skew_premium40": (
        vr2_return_skew_risk_premium,
        {"period": 40},
        1,
        "formal_pool",
        "偏度风险溢价",
    ),
    "upday_volume20": (
        vl_up_day_volume_share,
        {"period": 20},
        1,
        "formal_pool",
        "上涨日成交量占比",
    ),
    "breakout_persistence20": (
        tm2_breakout_persistence_momentum,
        {"period": 20, "slope_period": 20},
        1,
        "formal_pool",
        "突破持续性",
    ),
}

CORE_FACTORS = [
    "trend252_skip22",
    "quantile_reversion60",
    "upday_volume20",
    "breakout_persistence20",
    "trend22",
    "mom_skip252_22",
]


def _load_panel(end: str) -> pd.DataFrame:
    panel = DataManager().read_symbols(list(ASSET_CLASS_ETF_SYMBOLS), frequency="1d_adj")
    panel = apply_asset_class_split_adjustments(panel)
    dates = panel.index.get_level_values("eob")
    return panel.loc[(dates >= pd.Timestamp("2018-01-02")) & (dates <= pd.Timestamp(end))]


def _compute_factors(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    raw_factors = {}
    for name, (func, params, _direction, _source, _label) in FACTOR_SPECS.items():
        values = Factor(func, **params).cal_df(panel, dropna=False)
        raw_factors[name] = values.reindex(columns=list(ASSET_CLASS_ETF_SYMBOLS))
    return raw_factors


def _backtest(
    panel: pd.DataFrame,
    weights: pd.DataFrame,
    start: str,
    end: str,
    *,
    commission: float,
    slippage_bp: float,
):
    return VectorBacktester(
        panel,
        trade_at="close",
        signal_lag=SIGNAL_LAG,
        commission=commission,
        slippage_bp=slippage_bp,
        start_date=start,
        end_date=end,
    ).run(weights)


def _metric_row(name: str, segment: str, result) -> dict[str, object]:
    return {
        "method": name,
        "segment": segment,
        **result.metrics,
        "annual_turnover": float(result.result_df["turnover"].mean() * 252.0),
        "observations": int(len(result.result_df)),
    }


def _write_charts(
    output: Path,
    surface: pd.DataFrame,
    core: list[str],
    baseline: int,
    corr_calibration: pd.DataFrame,
    corr_oos: pd.DataFrame,
    rebalance: pd.DataFrame,
    factor_weights: pd.DataFrame,
    equities: pd.DataFrame,
    *,
    start_date: str,
    oos_start: str,
) -> None:
    for segment, filename in (
        ("full", "horizon_ic_full.png"),
        ("calibration", "horizon_ic_calibration.png"),
        ("oos", "horizon_ic_oos.png"),
    ):
        (output / filename).write_bytes(
            plot_horizon_ic(surface, factors=core, segment=segment)
        )

    for segment, filename in (
        ("full", "lagged_ic.png"),
        ("calibration", "lagged_ic_calibration.png"),
    ):
        (output / filename).write_bytes(
            plot_lagged_ic(surface, factors=core, segment=segment)
        )
    representative = core[0]
    matrix = surface[
        (surface.segment == "calibration") & (surface.factor == representative)
    ].pivot(index="horizon", columns="lag", values="ic_mean")
    (output / "ic_information_surface.png").write_bytes(
        plot_ic_heatmap(
            matrix,
            f"IC information surface · in-sample · {representative}",
            vmin=-0.1,
            vmax=0.1,
            annotate=True,
            dpi=180,
        )
    )
    (output / "factor_correlation_calibration.png").write_bytes(
        plot_ic_heatmap(
            corr_calibration,
            "Factor rank correlation · in-sample",
            vmin=-1.0,
            vmax=1.0,
            annotate=True,
            dpi=180,
        )
    )
    (output / "factor_correlation_oos.png").write_bytes(
        plot_ic_heatmap(
            corr_oos,
            "Factor rank correlation · OOS",
            vmin=-1.0,
            vmax=1.0,
            annotate=True,
            dpi=180,
        )
    )
    (output / "rebalance_comparison.png").write_bytes(
        plot_rebalance_comparison(rebalance, selected_days=baseline)
    )
    (output / "factor_weights.png").write_bytes(
        plot_factor_weight_history(factor_weights, start=start_date)
    )

    for plot_start, filename, title in (
        (start_date, "equity_curves_full.png", "Five combinations · full sample"),
        (oos_start, "equity_curves_oos.png", "Five combinations · out-of-sample"),
    ):
        (output / filename).write_bytes(
            plot_equity_comparison(equities, start=plot_start, title=title)
        )


def _markdown_table(frame: pd.DataFrame) -> str:
    headers = list(frame.columns)
    rows = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for values in frame.itertuples(index=False, name=None):
        cells = [
            f"{value:.4f}" if isinstance(value, (float, np.floating)) else str(value)
            for value in values
        ]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Lesson 06 multifactor experiment.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output directory. Relative paths are resolved from the workspace root.",
    )
    parser.add_argument(
        "--exclude-factor",
        action="append",
        default=[],
        help="Core factor to remove; may be supplied more than once.",
    )
    parser.add_argument("--commission-bp", type=float, default=COMMISSION * 10_000)
    parser.add_argument("--slippage-bp", type=float, default=SLIPPAGE_BP)
    parser.add_argument("--start", default=START)
    parser.add_argument("--calibration-end", default=CALIBRATION_END)
    parser.add_argument("--oos-start", default=OOS_START)
    parser.add_argument("--end", default=END)
    parser.add_argument(
        "--normalization",
        choices=["rank", "zscore"],
        default="rank",
        help="Daily cross-sectional factor normalization used by every combination method.",
    )
    parser.add_argument(
        "--baseline-rebalance-days",
        type=int,
        choices=REBALANCE_DAYS,
        default=BASELINE_REBALANCE_DAYS,
        help="Classroom baseline rebalance interval; defaults to 5 trading days.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    excluded = set(args.exclude_factor)
    unknown = excluded.difference(CORE_FACTORS)
    if unknown:
        raise ValueError(f"Unknown core factors requested for exclusion: {sorted(unknown)}")
    core = [factor for factor in CORE_FACTORS if factor not in excluded]
    if not core:
        raise ValueError("At least one core factor is required.")
    commission = float(args.commission_bp) / 10_000.0
    slippage_bp = float(args.slippage_bp)
    total_cost_bp = float(args.commission_bp) + slippage_bp
    start_date = str(args.start)
    calibration_end = str(args.calibration_end)
    oos_start = str(args.oos_start)
    end_date = str(args.end)
    if not (
        pd.Timestamp(start_date)
        <= pd.Timestamp(calibration_end)
        < pd.Timestamp(oos_start)
        <= pd.Timestamp(end_date)
    ):
        raise ValueError("Expected start <= calibration_end < oos_start <= end.")
    panel = _load_panel(end_date)

    def run_backtest(weights: pd.DataFrame, start: str, end: str):
        return _backtest(
            panel,
            weights,
            start,
            end,
            commission=commission,
            slippage_bp=slippage_bp,
        )

    prices = panel["close"].unstack("symbol").reindex(columns=list(ASSET_CLASS_ETF_SYMBOLS))
    raw_factors = _compute_factors(panel)
    factor_directions = {
        name: int(direction)
        for name, (_func, _params, direction, _source, _label) in FACTOR_SPECS.items()
    }
    factors = orient_factor_frames(raw_factors, factor_directions)
    segments = {
        "full": (start_date, end_date),
        "calibration": (start_date, calibration_end),
        "oos": (oos_start, end_date),
    }
    ic_result = compute_ic_information_surface(
        factors,
        prices,
        horizons=HORIZONS,
        lags=LAGS,
        signal_lag=SIGNAL_LAG,
        segments=segments,
        min_cross_section=6,
    )
    surface = ic_result.summary
    daily_ic = ic_result.daily_ic
    surface.to_csv(output / "ic_information_surface.csv", index=False)
    daily_ic.to_parquet(output / "daily_ic.parquet", index=False)

    horizon = surface[surface.lag == 0].copy()
    horizon.to_csv(output / "horizon_ic_summary.csv", index=False)
    lagged = surface[surface.horizon.isin([1, 5, 10, 20])].copy()
    lagged.to_csv(output / "lagged_ic_summary.csv", index=False)

    reval = []
    for name, (_func, params, direction, source, label) in FACTOR_SPECS.items():
        full = surface[
            (surface.factor == name)
            & (surface.segment == "full")
            & (surface.horizon == 5)
            & (surface.lag == 0)
        ].iloc[0]
        calibration_row = surface[
            (surface.factor == name)
            & (surface.segment == "calibration")
            & (surface.horizon == 5)
            & (surface.lag == 0)
        ].iloc[0]
        oos = surface[
            (surface.factor == name)
            & (surface.segment == "oos")
            & (surface.horizon == 5)
            & (surface.lag == 0)
        ].iloc[0]
        reval.append(
            {
                "factor": name,
                "display_name_zh": label,
                "source": source,
                "parameters": json.dumps(params, ensure_ascii=False, sort_keys=True),
                "direction": direction,
                "full_ic": full.ic_mean,
                "full_hac_t": full.hac_t,
                "full_effective_dates": full.effective_dates,
                "calibration_ic": calibration_row.ic_mean,
                "calibration_hac_t": calibration_row.hac_t,
                "calibration_effective_dates": calibration_row.effective_dates,
                "oos_ic": oos.ic_mean,
                "oos_hac_t": oos.hac_t,
                "oos_effective_dates": oos.effective_dates,
            }
        )
    revaluation = pd.DataFrame(reval)

    revaluation["selected_core"] = revaluation.factor.isin(core)
    revaluation.to_csv(output / "factor_ic_revaluation.csv", index=False)

    raw_core = {name: raw_factors[name] for name in core}
    core_directions = {name: factor_directions[name] for name in core}
    ranked_core = rank_factor_frames({name: factors[name] for name in core})
    corr_full = mean_daily_factor_rank_correlation(
        ranked_core, start=start_date, end=end_date
    )
    corr_calibration = mean_daily_factor_rank_correlation(
        ranked_core, start=start_date, end=calibration_end
    )
    corr_oos = mean_daily_factor_rank_correlation(
        ranked_core, start=oos_start, end=end_date
    )
    corr_full.to_csv(output / "factor_correlation_full.csv")
    corr_calibration.to_csv(output / "factor_correlation_calibration.csv")
    corr_oos.to_csv(output / "factor_correlation_oos.csv")
    correlation_history = rolling_factor_rank_correlation(ranked_core)
    correlation_history.to_csv(output / "factor_rolling_correlation.csv", index=False)
    top_n_jaccard_overlap(ranked_core, top_n=TOP_N).to_csv(output / "factor_top3_overlap.csv")
    ranked_calibration = {
        name: frame.loc[start_date:calibration_end] for name, frame in ranked_core.items()
    }
    top_n_jaccard_overlap(ranked_calibration, top_n=TOP_N).to_csv(
        output / "factor_top3_overlap_calibration.csv"
    )

    equal = combine_factor_scores(
        raw_core,
        method="equal_rank",
        directions=core_directions,
        normalization=args.normalization,
        top_n=TOP_N,
    )
    rebalance_rows = []
    for days in REBALANCE_DAYS:
        weights = apply_rebalance_schedule(equal.target_weights, every=days, start=start_date)
        horizon_ic = rank_ic_series(
            equal.composite_scores,
            execution_forward_return_wide(prices, horizon=days, lag=0, signal_lag=SIGNAL_LAG),
        ).loc[start_date:calibration_end]
        lag_ic = rank_ic_series(
            equal.composite_scores,
            execution_forward_return_wide(prices, horizon=days, lag=days, signal_lag=SIGNAL_LAG),
        ).loc[start_date:calibration_end]
        autocorr = factor_rank_autocorrelation(equal.composite_scores, periods=[days]).iloc[0]
        for segment, start, end in (
            ("calibration", start_date, calibration_end),
            ("oos", oos_start, end_date),
        ):
            result = run_backtest(weights, start, end)
            row = _metric_row(f"equal_rank_{days}d", segment, result)
            row.update(
                {
                    "rebalance_days": days,
                    "horizon_ic": float(horizon_ic.mean()),
                    "lagged_ic_at_interval": float(lag_ic.mean()),
                    "lagged_ic_retention": float(lag_ic.mean() / horizon_ic.mean())
                    if horizon_ic.mean()
                    else np.nan,
                    "rank_autocorrelation": float(autocorr),
                }
            )
            rebalance_rows.append(row)
    rebalance = pd.DataFrame(rebalance_rows)
    calibration = rebalance[rebalance.segment == "calibration"].copy()
    eligible = calibration[
        (calibration.horizon_ic > 0)
        & (calibration.lagged_ic_at_interval > 0)
        & (calibration.lagged_ic_retention >= 0.5)
    ]
    if eligible.empty:
        eligible = calibration[
            (calibration.horizon_ic > 0) & (calibration.lagged_ic_at_interval > 0)
        ]
    best_sharpe = eligible.sharpe_ratio.max()
    near_best = eligible[eligible.sharpe_ratio >= best_sharpe - 0.05]
    evidence_selected_baseline = int(
        near_best.sort_values(["annual_turnover", "rebalance_days"]).iloc[0].rebalance_days
    )
    baseline = (
        int(args.baseline_rebalance_days)
        if args.baseline_rebalance_days is not None
        else evidence_selected_baseline
    )
    rebalance["selected_baseline"] = rebalance.rebalance_days.eq(baseline)
    rebalance.to_csv(output / "rebalance_comparison.csv", index=False)

    chosen_ic = daily_ic[
        (daily_ic.horizon == baseline) & (daily_ic.lag == 0) & daily_ic.factor.isin(core)
    ]
    ic_history = chosen_ic.pivot(index="eob", columns="factor", values="ic").reindex(prices.index)
    methods = ["equal_rank", "equal_vote", "rolling_ic", "rolling_icir", "max_icir"]
    performance_rows, weight_rows, target_rows, equity_rows = [], [], [], []
    combination_results = {}
    for method in methods:
        kwargs = {}
        if method not in {"equal_rank", "equal_vote"}:
            kwargs = {
                "ic_history": ic_history,
                "correlation_history": correlation_history if method == "max_icir" else None,
                "dynamic_config": DynamicFactorWeightConfig(
                    availability_delay=SIGNAL_LAG + baseline,
                    lookback=252,
                    min_periods=126,
                    max_weight=0.5,
                    correlation_shrinkage=0.5,
                ),
            }
        combo = combine_factor_scores(
            raw_core,
            method=method,
            directions=core_directions,
            normalization=args.normalization,
            top_n=TOP_N,
            **kwargs,
        )
        held = apply_rebalance_schedule(
            combo.target_weights, every=baseline, start=start_date
        )
        combination_results[method] = (combo, held)
        fw = combo.factor_weights.stack().rename("weight").reset_index()
        fw.columns = ["eob", "factor", "weight"]
        fw.insert(0, "method", method)
        weight_rows.append(fw)
        tw = held.stack().rename("weight").reset_index()
        tw.columns = ["eob", "symbol", "weight"]
        tw.insert(0, "method", method)
        target_rows.append(tw)
        for segment, start, end in (
            ("full", start_date, end_date),
            ("calibration", start_date, calibration_end),
            ("oos", oos_start, end_date),
        ):
            result = run_backtest(held, start, end)
            performance_rows.append(_metric_row(method, segment, result))
        full_result = run_backtest(held, start_date, end_date)
        eq = full_result.result_df[["equity", "return", "drawdown"]].reset_index(names="eob")
        eq.insert(0, "method", method)
        equity_rows.append(eq)

    single_rows = []
    for name in core:
        single = combine_factor_scores(
            {name: raw_factors[name]},
            method="equal_rank",
            directions={name: factor_directions[name]},
            normalization=args.normalization,
            top_n=TOP_N,
        )
        held = apply_rebalance_schedule(
            single.target_weights, every=baseline, start=start_date
        )
        for segment, start, end in (
            ("full", start_date, end_date),
            ("oos", oos_start, end_date),
        ):
            row = _metric_row(name, segment, run_backtest(held, start, end))
            row["factor"] = name
            single_rows.append(row)
    pd.DataFrame(single_rows).to_csv(output / "single_factor_performance.csv", index=False)
    combination_performance = pd.DataFrame(performance_rows)
    combination_performance.to_csv(output / "combination_performance.csv", index=False)
    factor_weights = pd.concat(weight_rows, ignore_index=True)
    target_weights = pd.concat(target_rows, ignore_index=True)
    equities = pd.concat(equity_rows, ignore_index=True)
    factor_weights.to_csv(output / "factor_weights.csv", index=False)
    target_weights.to_csv(output / "target_weights.csv", index=False)
    equities.to_csv(output / "equity_curves.csv", index=False)

    config = {
        "data": {
            "frequency": "1d_adj",
            "universe": list(ASSET_CLASS_ETF_SYMBOLS),
            "split_adjustments": "apply_asset_class_split_adjustments",
        },
        "sample": {
            "start": start_date,
            "calibration_end": calibration_end,
            "oos_start": oos_start,
            "end": end_date,
        },
        "ic": {
            "formula": "corr(F_t, R[t+1+L,t+1+L+H])",
            "horizons": HORIZONS,
            "lags": LAGS,
            "rank": "Spearman",
            "hac_lag": "H-1",
        },
        "backtest": {
            "trade_at": "close",
            "signal_lag": SIGNAL_LAG,
            "commission": commission,
            "commission_bp": float(args.commission_bp),
            "slippage_bp": slippage_bp,
            "total_cost_bp": total_cost_bp,
            "top_n": TOP_N,
        },
        "dynamic_weights": {
            "window": 252,
            "min_periods": 126,
            "non_negative": True,
            "max_weight": 0.5,
            "availability_delay": SIGNAL_LAG + baseline,
            "fallback": "equal",
        },
        "factor_specs": {
            name: {
                "params": params,
                "direction": direction,
                "source": source,
                "display_name_zh": label,
            }
            for name, (_func, params, direction, source, label) in FACTOR_SPECS.items()
        },
        "selected_core_factors": core,
        "factor_normalization": args.normalization,
        "selected_rebalance_days": baseline,
        "evidence_selected_rebalance_days": evidence_selected_baseline,
        "rebalance_override": args.baseline_rebalance_days,
        "selection_rule": "Lesson 06 core factor pool with explicit scenario exclusions.",
        "excluded_core_factors": sorted(excluded),
    }
    (output / "experiment_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _write_charts(
        output,
        surface,
        core,
        baseline,
        corr_calibration,
        corr_oos,
        rebalance,
        factor_weights,
        equities,
        start_date=start_date,
        oos_start=oos_start,
    )
    full = combination_performance[combination_performance.segment == "full"].sort_values(
        "sharpe_ratio", ascending=False
    )
    oos = combination_performance[combination_performance.segment == "oos"].sort_values(
        "sharpe_ratio", ascending=False
    )
    try:
        output_arg = output.relative_to(ROOT)
    except ValueError:
        output_arg = output
    reproduce_parts = [
        "uv run python -m strategies.cross_sectional.workflows.run_lesson06_multifactor",
        f"--output {output_arg}",
        *(f"--exclude-factor {factor}" for factor in sorted(excluded)),
        f"--commission-bp {args.commission_bp:g}",
        f"--slippage-bp {slippage_bp:g}",
        f"--start {start_date}",
        f"--calibration-end {calibration_end}",
        f"--oos-start {oos_start}",
        f"--end {end_date}",
        f"--normalization {args.normalization}",
        *(
            [f"--baseline-rebalance-days {args.baseline_rebalance_days}"]
            if args.baseline_rebalance_days is not None
            else []
        ),
    ]
    reproduce_command = " \\\n  ".join(reproduce_parts)
    report = [
        "# 第 6 课：多因子组合实验报告",
        "",
        "## 实验口径",
        "",
        f"- 样本：{start_date} 至 {end_date}；{oos_start} 起为样本外。",
        "- IC：横截面 Spearman；收益从信号后一日开始；Horizon 与 Lag 分开。",
        "- 重叠收益：Newey–West HAC，滞后阶数 H-1。",
        f"- 核心因子：{', '.join(core)}。",
        f"- 因子预处理：统一方向后逐日做横截面 {args.normalization} 归一化。",
        f"- 课堂基准调仓周期：{baseline} 个交易日。动态 IC 在 {SIGNAL_LAG + baseline} 日后才进入权重。",
        f"- 回测：Top 3 ETF 资产等权，佣金 {args.commission_bp:g}bp + 滑点 {slippage_bp:g}bp = 单边总成本 {total_cost_bp:g}bp。",
        "",
        "## 全样本组合结果",
        "",
        _markdown_table(
            full[["method", "ann_return", "sharpe_ratio", "max_drawdown", "annual_turnover"]]
        ),
        "",
        "## 教学结论",
        "",
        "1. Horizon IC 描述预测期限；Lagged IC 描述同一信号延迟使用后的衰减，两者不是同一个指标。",
        "2. 累计收益窗口扩大时 Horizon IC 可以先上升；这不代表信号没有随等待而失效。",
        "3. 调仓周期需要同时看对应 Horizon IC、周期末 Lagged IC、排名自相关、换手和含成本绩效。",
        "4. 因子相关性表示重复信息；最大 ICIR 通过收缩相关矩阵降低重复暴露。",
        "",
        "## 复现",
        "",
        "```bash",
        reproduce_command,
        "```",
        "",
        "所有课件数字均来自同目录 CSV/JSON，图来自同一命令生成的 PNG。",
    ]
    (output / "experiment_report.md").write_text("\n".join(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "core": core,
                "baseline": baseline,
                "total_cost_bp": total_cost_bp,
                "full": full[["method", "sharpe_ratio"]].to_dict("records"),
                "oos": oos[["method", "sharpe_ratio"]].to_dict("records"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
