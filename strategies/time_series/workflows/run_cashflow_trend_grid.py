"""Run in-sample sensitivity selection and locked OOS evaluation for 932365.CSI."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pandas as pd

from skills.backtest import VectorBacktester, activity_metrics, annual_return_metrics
from skills.report.strategy_markdown import StrategyReport, write_strategy_report
from skills.store.data_manager import DataManager
from skills.store.workspace import resolve_workspace_paths
from strategies.time_series.cashflow_trend import (
    CashflowTrendParams,
    cashflow_trend_weights,
)

SYMBOL = "932365.CSI"
FREQUENCY = "1d_adj"
IS_END = "2024-12-31"
OOS_START = "2025-01-01"
COMMISSION = 0.0002
SLIPPAGE_BP = 2.0


def sensitivity_configs() -> list[tuple[str, CashflowTrendParams]]:
    """Return baseline plus one-factor-at-a-time parameter sensitivity cases."""
    base = CashflowTrendParams()
    cases = [("baseline", base)]
    variations: list[tuple[str, dict[str, Any]]] = [
        ("trend_ma_100", {"trend_ma": 100}),
        ("trend_ma_160", {"trend_ma": 160}),
        ("breakout_40", {"breakout_lookback": 40}),
        ("breakout_55", {"breakout_lookback": 55}),
        ("ma_30_90", {"fast_ma": 30, "slow_ma": 90}),
        ("atr_20", {"atr_lookback": 20}),
        ("initial_stop_3", {"initial_stop_atr": 3.0}),
        ("trailing_stop_2_5", {"trailing_stop_atr": 2.5}),
        ("trailing_stop_3_5", {"trailing_stop_atr": 3.5}),
        ("exit_10", {"exit_lookback": 10}),
        ("exit_30", {"exit_lookback": 30}),
        ("target_vol_12", {"target_volatility": 0.12}),
    ]
    cases.extend((name, replace(base, **changes)) for name, changes in variations)
    return cases


def _execute(
    panel: pd.DataFrame,
    weights: pd.DataFrame,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
):
    return VectorBacktester(
        data=panel,
        trade_at="close",
        signal_lag=1,
        commission=COMMISSION,
        slippage_bp=SLIPPAGE_BP,
        start_date=start_date,
        end_date=end_date,
    ).run(weights)


def _metrics(execution) -> dict[str, float]:
    metrics = {
        **execution.metrics,
        **annual_return_metrics(execution.result_df),
        **activity_metrics(execution.result_df),
    }
    executed = execution.executed_weights[SYMBOL].reindex(execution.result_df.index).fillna(0.0)
    entries = ((executed > 0) & (executed.shift(1).fillna(0.0) <= 0)).sum()
    metrics["entries"] = float(entries)
    metrics["average_exposure"] = float(executed.mean())
    return metrics


def _prefixed(prefix: str, values: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in values.items()}


def _selection_score(row: pd.Series) -> float:
    if row["is_entries"] < 4 or row["is_max_drawdown"] <= 0:
        return float("-inf")
    return float(row["is_calmar_ratio"])


def run_grid(
    *,
    data_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Run sensitivity cases, select on IS only, and write locked OOS artifacts."""
    dm = DataManager(data_root=str(data_root) if data_root is not None else None)
    panel = dm.read_symbols([SYMBOL], frequency=FREQUENCY)
    bars = panel.xs(SYMBOL, level="symbol").copy()

    rows: list[dict[str, Any]] = []
    weights_by_name: dict[str, pd.DataFrame] = {}
    for name, params in sensitivity_configs():
        weights = cashflow_trend_weights(bars, symbol=SYMBOL, params=params)
        weights_by_name[name] = weights
        is_execution = _execute(panel, weights, end_date=IS_END)
        oos_execution = _execute(panel, weights, start_date=OOS_START)
        rows.append(
            {
                "candidate": name,
                **asdict(params),
                **_prefixed("is", _metrics(is_execution)),
                **_prefixed("oos", _metrics(oos_execution)),
            }
        )

    results = pd.DataFrame(rows)
    results["selection_score"] = results.apply(_selection_score, axis=1)
    results["selected"] = False
    selected_idx = results["selection_score"].idxmax()
    results.loc[selected_idx, "selected"] = True
    selected_row = results.loc[selected_idx]
    selected_name = str(selected_row["candidate"])
    selected_params = dict(sensitivity_configs())[selected_name]
    selected_weights = weights_by_name[selected_name]

    is_execution = _execute(panel, selected_weights, end_date=IS_END)
    oos_execution = _execute(panel, selected_weights, start_date=OOS_START)

    paths = resolve_workspace_paths()
    out = Path(output_dir) if output_dir is not None else paths.reports_root / "cashflow_trend"
    out.mkdir(parents=True, exist_ok=True)
    grid_path = out / "parameter_sensitivity.csv"
    params_path = out / "selected_params.json"
    weights_path = out / "selected_weights.parquet"
    is_path = out / "selected_is_performance.parquet"
    oos_path = out / "selected_oos_performance.parquet"
    results.sort_values("selection_score", ascending=False).to_csv(grid_path, index=False)
    params_path.write_text(
        json.dumps(
            {
                "candidate": selected_name,
                "selection_rule": "highest in-sample Calmar with at least 4 entries",
                "is_end": IS_END,
                "oos_start": OOS_START,
                "parameters": asdict(selected_params),
                "commission": COMMISSION,
                "slippage_bp": SLIPPAGE_BP,
                "atr_definition": "Wilder-smoothed absolute close change (close-only proxy)",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    selected_weights.to_parquet(weights_path)
    is_execution.result_df.to_parquet(is_path)
    oos_execution.result_df.to_parquet(oos_path)

    common_notes = [
        "Signals use only official close levels; pre-launch OHLC values are not fabricated.",
        "ATR is a Wilder-smoothed absolute close-change proxy because historical high/low is unavailable.",
        "Signals are formed at the close and shifted one bar before earning forward close returns.",
        "Transaction costs assume 2 bp commission plus 2 bp slippage per unit turnover.",
        "The index is not directly tradable; a real execution proxy requires separate tracking-error and cost tests.",
    ]
    write_strategy_report(
        StrategyReport(
            slug="selected_in_sample",
            title=f"{SYMBOL} Selected Trend Rule — In Sample",
            domain="time_series",
            strategy_type="Close-only trend breakout",
            label=f"Selected candidate: {selected_name}",
            description=f"Parameter selection sample ends on {IS_END}.",
            metrics=_metrics(is_execution),
            result_df=is_execution.result_df,
            notes=[*common_notes, "This segment was used for parameter selection."],
        ),
        out,
    )
    write_strategy_report(
        StrategyReport(
            slug="selected_out_of_sample",
            title=f"{SYMBOL} Selected Trend Rule — Out of Sample",
            domain="time_series",
            strategy_type="Close-only trend breakout",
            label=f"Locked candidate: {selected_name}",
            description=f"Locked-parameter evaluation begins on {OOS_START}.",
            metrics=_metrics(oos_execution),
            result_df=oos_execution.result_df,
            notes=[*common_notes, "Parameters were selected without using this segment's metrics."],
        ),
        out,
    )

    return {
        "grid": grid_path,
        "params": params_path,
        "weights": weights_path,
        "is_performance": is_path,
        "oos_performance": oos_path,
        "is_report": out / "selected_in_sample.md",
        "oos_report": out / "selected_out_of_sample.md",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    outputs = run_grid(data_root=args.data_root, output_dir=args.output_dir)
    for name, path in outputs.items():
        print(f"{name}: {path.resolve()}")


if __name__ == "__main__":
    main()
