"""Optimize Donchian close breakouts with ATR-proxy stops on IS only."""

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
from strategies.time_series.cashflow_donchian_atr import (
    DonchianAtrParams,
    donchian_atr_weights,
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


def core_configs() -> list[tuple[str, DonchianAtrParams]]:
    """Return fixed-exposure core channel and stop parameter combinations."""
    configs: list[tuple[str, DonchianAtrParams]] = []
    counter = 0
    for entry, exit_, atr_lookback, multiplier in itertools.product(
        (20, 40, 55, 80, 120),
        (10, 20, 30, 40, 55),
        (14, 20, 30, 40),
        (2.0, 2.5, 3.0, 3.5, 4.0),
    ):
        if entry <= exit_:
            continue
        counter += 1
        configs.append(
            (
                f"core_{counter:04d}",
                DonchianAtrParams(
                    entry_lookback=entry,
                    exit_lookback=exit_,
                    atr_lookback=atr_lookback,
                    atr_multiplier=multiplier,
                    sizing="fixed",
                ),
            )
        )
    return configs


def sizing_configs(
    core_results: pd.DataFrame,
    params_by_candidate: dict[str, DonchianAtrParams],
    top_core: int = 10,
) -> list[tuple[str, DonchianAtrParams]]:
    """Apply target-volatility sizing around robust core leaders."""
    leaders = core_results.nlargest(top_core, "optimization_score")
    configs: list[tuple[str, DonchianAtrParams]] = []
    counter = 0
    for _, row in leaders.iterrows():
        base = params_by_candidate[str(row["candidate"])]
        for target_vol, vol_lookback in itertools.product(
            (0.08, 0.10, 0.12, 0.15),
            (20, 40, 60),
        ):
            counter += 1
            configs.append(
                (
                    f"sizing_{counter:04d}",
                    replace(
                        base,
                        sizing="target_vol",
                        target_volatility=target_vol,
                        volatility_lookback=vol_lookback,
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
    returns_by_fold: list[float] = []
    for label, start, end in FOLDS:
        metrics = performance_metrics(result_df.loc[start:end, "return"])
        calmar = float(metrics["calmar"])
        if not np.isfinite(calmar):
            calmar = 0.0
        fold_return = float(metrics["total_return"])
        values[f"fold_{label}_return"] = fold_return
        values[f"fold_{label}_calmar"] = calmar
        calmars.append(calmar)
        returns_by_fold.append(fold_return)
    values["median_fold_calmar"] = float(np.median(calmars))
    values["worst_fold_return"] = float(np.min(returns_by_fold))
    values["positive_folds"] = float(sum(value > 0 for value in returns_by_fold))
    return values


def _evaluate(
    candidate: str,
    params: DonchianAtrParams,
    bars: pd.DataFrame,
    panel: pd.DataFrame,
) -> dict[str, Any]:
    weights = donchian_atr_weights(bars, symbol=SYMBOL, params=params)
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


def _rank(frame: pd.DataFrame) -> pd.DataFrame:
    ranked = frame.copy()
    eligible = (ranked["entries"] >= 6) & (ranked["max_drawdown"] > 0)
    components = (
        ("calmar_ratio", "calmar_rank", 0.35),
        ("sharpe_ratio", "sharpe_rank", 0.25),
        ("median_fold_calmar", "fold_calmar_rank", 0.25),
        ("worst_fold_return", "worst_fold_rank", 0.15),
    )
    score = pd.Series(0.0, index=ranked.index)
    for source, output, weight in components:
        ranked[output] = ranked[source].replace([np.inf, -np.inf], np.nan).rank(pct=True)
        score = score + ranked[output].fillna(0.0) * weight
    ranked["optimization_score"] = float("-inf")
    ranked.loc[eligible, "optimization_score"] = score.loc[eligible]
    return ranked


def _evaluate_configs(
    configs: list[tuple[str, DonchianAtrParams]],
    bars: pd.DataFrame,
    panel: pd.DataFrame,
) -> pd.DataFrame:
    return _rank(pd.DataFrame([_evaluate(name, params, bars, panel) for name, params in configs]))


def run_optimization(
    *,
    data_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Run core and sizing optimization with data ending at 2024-12-31."""
    dm = DataManager(data_root=str(data_root) if data_root is not None else None)
    full_panel = dm.read_symbols([SYMBOL], frequency=FREQUENCY)
    panel = full_panel.loc[full_panel.index.get_level_values("eob") <= pd.Timestamp(IS_END)].copy()
    if panel.index.get_level_values("eob").max() > pd.Timestamp(IS_END):
        raise AssertionError("out-of-sample data leaked into the optimization panel")
    bars = panel.xs(SYMBOL, level="symbol").copy()

    first_configs = core_configs()
    params_by_candidate = dict(first_configs)
    core = _evaluate_configs(first_configs, bars, panel)
    second_configs = sizing_configs(core, params_by_candidate)
    params_by_candidate.update(dict(second_configs))
    sizing = _evaluate_configs(second_configs, bars, panel)
    combined = _rank(pd.concat([core, sizing], ignore_index=True))
    combined["selected"] = False
    selected_idx = combined["optimization_score"].idxmax()
    combined.loc[selected_idx, "selected"] = True
    selected_candidate = str(combined.loc[selected_idx, "candidate"])
    selected_params = params_by_candidate[selected_candidate]

    paths = resolve_workspace_paths()
    out = (
        Path(output_dir)
        if output_dir is not None
        else paths.reports_root / "cashflow_donchian_atr_is"
    )
    out.mkdir(parents=True, exist_ok=True)
    core_path = out / "core_results.csv"
    sizing_path = out / "sizing_results.csv"
    all_path = out / "optimization_results.csv"
    params_path = out / "selected_params.json"
    weights_path = out / "selected_weights.parquet"
    performance_path = out / "selected_performance.parquet"
    core.sort_values("optimization_score", ascending=False).to_csv(core_path, index=False)
    sizing.sort_values("optimization_score", ascending=False).to_csv(sizing_path, index=False)
    combined.sort_values("optimization_score", ascending=False).to_csv(all_path, index=False)
    params_path.write_text(
        json.dumps(
            {
                "candidate": selected_candidate,
                "sample_end": IS_END,
                "selection_scope": "in_sample_only",
                "parameters": asdict(selected_params),
                "atr_definition": "Wilder-smoothed absolute close change (close-only proxy)",
                "commission": COMMISSION,
                "slippage_bp": SLIPPAGE_BP,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    weights = donchian_atr_weights(bars, symbol=SYMBOL, params=selected_params)
    execution = _execute(panel, weights)
    weights.to_parquet(weights_path)
    execution.result_df.to_parquet(performance_path)
    selected_metrics = _evaluate(selected_candidate, selected_params, bars, panel)
    excluded = set(asdict(selected_params)) | {"candidate"}
    report = StrategyReport(
        slug="selected_donchian_atr",
        title=f"{SYMBOL} Donchian + ATR Proxy IS Optimization",
        domain="time_series",
        strategy_type="Close-channel Donchian breakout with ATR-proxy stop",
        label=selected_candidate,
        description=f"In-sample optimization only; all data ends on {IS_END}.",
        metrics={key: value for key, value in selected_metrics.items() if key not in excluded},
        result_df=execution.result_df,
        notes=[
            "No observations after 2024-12-31 are loaded into this optimization panel.",
            "Entry is a close above the prior Donchian upper channel.",
            "Exit is the prior closing-low channel or the initial/trailing ATR-proxy stop.",
            "ATR uses Wilder-smoothed absolute close changes because historical OHLC is unavailable.",
            "Signals are shifted one bar; costs are 2 bp commission plus 2 bp slippage.",
        ],
    )
    report_path = write_strategy_report(report, out)
    return {
        "core": core_path,
        "sizing": sizing_path,
        "all_results": all_path,
        "selected_params": params_path,
        "selected_weights": weights_path,
        "selected_performance": performance_path,
        "selected_report": report_path,
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
