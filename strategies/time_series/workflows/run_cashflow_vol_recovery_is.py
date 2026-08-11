"""Optimize volatility sizing, loss stops, and recovery re-entry on IS only."""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from skills.analyze.attribution_counterfactual import performance_metrics
from skills.backtest import VectorBacktester, activity_metrics, annual_return_metrics
from skills.report.strategy_markdown import StrategyReport, write_strategy_report
from skills.store.data_manager import DataManager
from skills.store.workspace import resolve_workspace_paths
from strategies.time_series.cashflow_vol_recovery import (
    VolRecoveryParams,
    cashflow_vol_recovery_weights,
)

SYMBOL = "932365.CSI"
FREQUENCY = "1d_adj"
IS_END = "2024-12-31"
COMMISSION = 0.0002
SLIPPAGE_BP = 2.0
FOLDS = (
    ("2019_2020", "2019-01-01", "2020-12-31"),
    ("2021_2022", "2021-01-01", "2022-12-31"),
    ("2023_2024", "2023-01-01", "2024-12-31"),
)


def stage1_configs() -> list[tuple[str, VolRecoveryParams]]:
    """Broad sizing and trend search with fixed stop/recovery defaults."""
    common = list(
        itertools.product(
            (100, 120, 160),
            (20, 40, 55),
            (20, 40, 60),
        )
    )
    configs: list[tuple[str, VolRecoveryParams]] = []
    counter = 0
    for trend_ma, breakout, vol_lookback in common:
        for target_vol in (0.08, 0.10, 0.12, 0.15):
            counter += 1
            configs.append(
                (
                    f"stage1_target_vol_{counter:04d}",
                    VolRecoveryParams(
                        family="target_vol",
                        trend_ma=trend_ma,
                        breakout_lookback=breakout,
                        volatility_lookback=vol_lookback,
                        target_volatility=target_vol,
                    ),
                )
            )

    band_profiles = (
        (1.0, 0.6, 0.3),
        (0.8, 0.5, 0.2),
        (1.0, 0.5, 0.1),
    )
    for trend_ma, breakout, vol_lookback in common:
        for regime_lookback, profile in itertools.product((120, 252), band_profiles):
            counter += 1
            configs.append(
                (
                    f"stage1_vol_band_{counter:04d}",
                    VolRecoveryParams(
                        family="vol_band",
                        trend_ma=trend_ma,
                        breakout_lookback=breakout,
                        volatility_lookback=vol_lookback,
                        regime_lookback=regime_lookback,
                        low_vol_exposure=profile[0],
                        mid_vol_exposure=profile[1],
                        high_vol_exposure=profile[2],
                    ),
                )
            )

    for trend_ma, breakout, vol_lookback in common:
        hybrid_values = itertools.product(
            (0.08, 0.10, 0.12),
            (0.03, 0.05),
            (0.25, 0.50),
        )
        for target_vol, reduce_trigger, reduced_multiplier in hybrid_values:
            counter += 1
            configs.append(
                (
                    f"stage1_hybrid_{counter:04d}",
                    VolRecoveryParams(
                        family="hybrid",
                        trend_ma=trend_ma,
                        breakout_lookback=breakout,
                        volatility_lookback=vol_lookback,
                        target_volatility=target_vol,
                        reduce_trigger=reduce_trigger,
                        reduced_exposure_multiplier=reduced_multiplier,
                    ),
                )
            )
    return configs


def stage2_configs(
    stage1: pd.DataFrame,
    params_by_candidate: dict[str, VolRecoveryParams],
    top_per_family: int = 2,
) -> list[tuple[str, VolRecoveryParams]]:
    """Tune stop/recovery parameters around robust Stage-1 family leaders."""
    leaders = (
        stage1.sort_values("optimization_score", ascending=False)
        .groupby("family", sort=False)
        .head(top_per_family)
    )
    configs: list[tuple[str, VolRecoveryParams]] = []
    counter = 0
    for _, row in leaders.iterrows():
        base = params_by_candidate[str(row["candidate"])]
        for loss_stop, recovery, cooldown in itertools.product(
            (0.04, 0.06, 0.08, 0.10),
            (0.01, 0.02, 0.04, 0.06),
            (0, 5, 10, 20),
        ):
            if base.family == "hybrid" and base.reduce_trigger >= loss_stop:
                continue
            counter += 1
            configs.append(
                (
                    f"stage2_{base.family}_{counter:04d}",
                    replace(
                        base,
                        loss_stop=loss_stop,
                        recovery_threshold=recovery,
                        cooldown_bars=cooldown,
                    ),
                )
            )
    return configs


def _execute(panel: pd.DataFrame, weights: pd.DataFrame):
    return VectorBacktester(
        data=panel,
        trade_at="close",
        signal_lag=1,
        commission=COMMISSION,
        slippage_bp=SLIPPAGE_BP,
    ).run(weights)


def _fold_metrics(result_df: pd.DataFrame) -> dict[str, float]:
    values: dict[str, float] = {}
    calmars: list[float] = []
    fold_returns: list[float] = []
    for label, start, end in FOLDS:
        returns = result_df.loc[start:end, "return"]
        metrics = performance_metrics(returns)
        calmar = float(metrics["calmar"])
        if not np.isfinite(calmar):
            calmar = 0.0
        values[f"fold_{label}_return"] = float(metrics["total_return"])
        values[f"fold_{label}_calmar"] = calmar
        calmars.append(calmar)
        fold_returns.append(float(metrics["total_return"]))
    values["median_fold_calmar"] = float(np.median(calmars))
    values["worst_fold_return"] = float(np.min(fold_returns))
    values["positive_folds"] = float(sum(value > 0 for value in fold_returns))
    return values


def _evaluate(
    candidate: str,
    params: VolRecoveryParams,
    bars: pd.DataFrame,
    panel: pd.DataFrame,
) -> dict[str, Any]:
    weights = cashflow_vol_recovery_weights(bars, symbol=SYMBOL, params=params)
    execution = _execute(panel, weights)
    result = execution.result_df
    executed = execution.executed_weights[SYMBOL].reindex(result.index).fillna(0.0)
    entries = float(((executed > 0) & (executed.shift(1).fillna(0.0) <= 0)).sum())
    return {
        "candidate": candidate,
        **asdict(params),
        **execution.metrics,
        **annual_return_metrics(result),
        **activity_metrics(result),
        **_fold_metrics(result),
        "entries": entries,
        "average_exposure": float(executed.mean()),
    }


def _rank_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    ranked = frame.copy()
    eligible = (ranked["entries"] >= 6) & (ranked["max_drawdown"] > 0)
    components = {
        "calmar_rank": ("calmar_ratio", 0.35),
        "sharpe_rank": ("sharpe_ratio", 0.25),
        "fold_calmar_rank": ("median_fold_calmar", 0.25),
        "worst_fold_rank": ("worst_fold_return", 0.15),
    }
    ranked["optimization_score"] = float("-inf")
    score = pd.Series(0.0, index=ranked.index)
    for output, (source, weight) in components.items():
        ranked[output] = ranked[source].replace([np.inf, -np.inf], np.nan).rank(pct=True)
        score = score + ranked[output].fillna(0.0) * weight
    ranked.loc[eligible, "optimization_score"] = score.loc[eligible]
    return ranked


def _evaluate_configs(
    configs: list[tuple[str, VolRecoveryParams]],
    bars: pd.DataFrame,
    panel: pd.DataFrame,
) -> pd.DataFrame:
    return _rank_candidates(
        pd.DataFrame([_evaluate(name, params, bars, panel) for name, params in configs])
    )


def _write_report(
    *,
    slug: str,
    title: str,
    candidate: str,
    params: VolRecoveryParams,
    bars: pd.DataFrame,
    panel: pd.DataFrame,
    output_dir: Path,
) -> tuple[Path, pd.DataFrame, pd.DataFrame]:
    weights = cashflow_vol_recovery_weights(bars, symbol=SYMBOL, params=params)
    execution = _execute(panel, weights)
    metrics = _evaluate(candidate, params, bars, panel)
    excluded = set(asdict(params)) | {"candidate"}
    report_metrics = {key: value for key, value in metrics.items() if key not in excluded}
    report = StrategyReport(
        slug=slug,
        title=title,
        domain="time_series",
        strategy_type=f"{params.family} sizing + loss-stop recovery",
        label=candidate,
        description=f"In-sample optimization only; all data ends on {IS_END}.",
        metrics=report_metrics,
        result_df=execution.result_df,
        notes=[
            "No observations after 2024-12-31 are loaded into this optimization panel.",
            "Entry uses a rising long MA, close-channel breakout, and MA20 above MA60.",
            "A loss stop exits relative to entry close; re-entry requires cooldown, price recovery, and a positive trend regime.",
            "Signals are shifted one bar and earn forward close-to-close returns.",
            "Transaction costs assume 2 bp commission plus 2 bp slippage per unit turnover.",
            "The index is not directly tradable; execution-proxy validation remains separate.",
        ],
    )
    return write_strategy_report(report, output_dir), weights, execution.result_df


def run_optimization(
    *,
    data_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Run two-stage optimization using only observations before 2025."""
    dm = DataManager(data_root=str(data_root) if data_root is not None else None)
    full_panel = dm.read_symbols([SYMBOL], frequency=FREQUENCY)
    panel = full_panel.loc[full_panel.index.get_level_values("eob") <= pd.Timestamp(IS_END)].copy()
    if panel.index.get_level_values("eob").max() > pd.Timestamp(IS_END):
        raise AssertionError("out-of-sample data leaked into the optimization panel")
    bars = panel.xs(SYMBOL, level="symbol").copy()

    first_configs = stage1_configs()
    params_by_candidate = dict(first_configs)
    stage1 = _evaluate_configs(first_configs, bars, panel)
    second_configs = stage2_configs(stage1, params_by_candidate)
    params_by_candidate.update(dict(second_configs))
    stage2 = _evaluate_configs(second_configs, bars, panel)
    combined = _rank_candidates(pd.concat([stage1, stage2], ignore_index=True))
    combined["selected"] = False
    selected_idx = combined["optimization_score"].idxmax()
    combined.loc[selected_idx, "selected"] = True
    selected_candidate = str(combined.loc[selected_idx, "candidate"])
    selected_params = params_by_candidate[selected_candidate]

    champions = (
        combined.sort_values("optimization_score", ascending=False)
        .groupby("family", sort=True)
        .head(1)
        .reset_index(drop=True)
    )
    paths = resolve_workspace_paths()
    out = (
        Path(output_dir)
        if output_dir is not None
        else paths.reports_root / "cashflow_vol_recovery_is"
    )
    out.mkdir(parents=True, exist_ok=True)
    stage1_path = out / "stage1_results.csv"
    stage2_path = out / "stage2_results.csv"
    all_path = out / "optimization_results.csv"
    champions_path = out / "family_champions.csv"
    params_path = out / "selected_params.json"
    weights_path = out / "selected_weights.parquet"
    performance_path = out / "selected_performance.parquet"
    stage1.sort_values("optimization_score", ascending=False).to_csv(stage1_path, index=False)
    stage2.sort_values("optimization_score", ascending=False).to_csv(stage2_path, index=False)
    combined.sort_values("optimization_score", ascending=False).to_csv(all_path, index=False)
    champions.to_csv(champions_path, index=False)
    params_path.write_text(
        json.dumps(
            {
                "candidate": selected_candidate,
                "sample_end": IS_END,
                "selection_scope": "in_sample_only",
                "selection_rule": (
                    "weighted percentile ranks: full Calmar 35%, full Sharpe 25%, "
                    "median fold Calmar 25%, worst fold return 15%; minimum 6 entries"
                ),
                "parameters": asdict(selected_params),
                "commission": COMMISSION,
                "slippage_bp": SLIPPAGE_BP,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    selected_report, selected_weights, selected_performance = _write_report(
        slug="selected_overall",
        title=f"{SYMBOL} Volatility/Recovery IS-Optimized Rule",
        candidate=selected_candidate,
        params=selected_params,
        bars=bars,
        panel=panel,
        output_dir=out,
    )
    selected_weights.to_parquet(weights_path)
    selected_performance.to_parquet(performance_path)

    for _, champion in champions.iterrows():
        candidate = str(champion["candidate"])
        family = str(champion["family"])
        _write_report(
            slug=f"best_{family}",
            title=f"{SYMBOL} Best IS {family} Rule",
            candidate=candidate,
            params=params_by_candidate[candidate],
            bars=bars,
            panel=panel,
            output_dir=out,
        )

    return {
        "stage1": stage1_path,
        "stage2": stage2_path,
        "all_results": all_path,
        "champions": champions_path,
        "selected_params": params_path,
        "selected_weights": weights_path,
        "selected_performance": performance_path,
        "selected_report": selected_report,
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
