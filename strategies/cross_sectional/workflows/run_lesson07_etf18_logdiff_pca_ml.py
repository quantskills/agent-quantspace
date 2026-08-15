"""Lesson 07: 18-ETF LogDiff + expanding PCA + cross-sectional ML rank backtest.

Run:
    uv run python -m strategies.cross_sectional.workflows.run_lesson07_etf18_logdiff_pca_ml
"""

from __future__ import annotations

import argparse
import io
import json
import time
from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from skills.backtest import VectorBacktester
from skills.compute.features import make_logdiff_panel_features
from skills.ml.pca_fold import ModelKind
from skills.report.charts import plot_backtest_performance, plot_equity_comparison
from skills.store.data_manager import DataManager
from skills.strategy.cross_sectional import hold_weights_on_calendar
from strategies.cross_sectional.asset_class_rotation import ASSET_CLASS_ETF_SYMBOLS
from strategies.cross_sectional.ml_rank import (
    DEFAULT_RETRAIN_STEP,
    expanding_pca_multi_model_scores,
    rank_scores_to_weights,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "reports" / "lesson_07_etf18_logdiff_pca_ml"
MODELS: tuple[ModelKind, ...] = ("ols", "lasso", "rf", "xgboost")

N_PCA = 50
MIN_TRAIN = 250
RETRAIN_STEP = DEFAULT_RETRAIN_STEP
HORIZON = 20
TOP_N = 3
SIGNAL_LAG = 0
COMMISSION = 0.0002
SLIPPAGE_BP = 3.0


def _load_panel() -> pd.DataFrame:
    # ``1d_adj`` is already split-adjusted; do not also call
    # ``apply_asset_class_split_adjustments`` (that helper is for raw ``1d``).
    return DataManager().read_symbols(list(ASSET_CLASS_ETF_SYMBOLS), frequency="1d_adj")


def _backtest(panel: pd.DataFrame, weights: pd.DataFrame, *, start_date: str | None = None):
    return VectorBacktester(
        panel,
        trade_at="close",
        signal_lag=SIGNAL_LAG,
        commission=COMMISSION,
        slippage_bp=SLIPPAGE_BP,
        start_date=start_date,
    ).run(weights)


def _metric_row(model: str, result) -> dict[str, object]:
    return {
        "model": model,
        **result.metrics,
        "annual_turnover": float(result.result_df["turnover"].mean() * 252.0),
        "observations": int(len(result.result_df)),
        "oos_start": str(result.result_df.index.min().date()),
        "oos_end": str(result.result_df.index.max().date()),
    }


def _plot_drawdown_comparison(equities: pd.DataFrame, *, start: str, title: str, dpi: int = 180) -> bytes:
    data = equities[equities["eob"] >= pd.Timestamp(start)]
    fig, ax = plt.subplots(figsize=(9.5, 4.5))
    for model, group in data.groupby("method"):
        frame = group.set_index("eob").sort_index()
        if frame.empty:
            continue
        equity = frame["equity"].astype(float)
        drawdown = equity.div(equity.cummax()).sub(1.0)
        ax.plot(drawdown.index, drawdown, lw=1.8, label=model)
    ax.set(xlabel="", ylabel="Drawdown", title=title)
    ax.legend(ncol=3, fontsize=8, frameon=False)
    ax.grid(alpha=0.16)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=dpi)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Lesson 07 ETF18 LogDiff PCA ML workflow.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output directory. Relative paths resolve from the workspace root.",
    )
    parser.add_argument("--min-train", type=int, default=MIN_TRAIN)
    parser.add_argument("--retrain-step", type=int, default=RETRAIN_STEP)
    parser.add_argument("--horizon", type=int, default=HORIZON)
    parser.add_argument("--top-n", type=int, default=TOP_N)
    parser.add_argument("--n-pca", type=int, default=N_PCA)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    started = time.perf_counter()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)

    panel = _load_panel()
    dates = panel.index.get_level_values("eob").unique()
    sample_start = str(pd.Timestamp(dates.min()).date())
    sample_end = str(pd.Timestamp(dates.max()).date())
    close = panel["close"].unstack(level="symbol").sort_index().reindex(columns=list(ASSET_CLASS_ETF_SYMBOLS))

    params = {
        "data": {
            "frequency": "1d_adj",
            "universe": list(ASSET_CLASS_ETF_SYMBOLS),
            "split_adjustments": "none (1d_adj already adjusted)",
        },
        "sample": {"start": sample_start, "end": sample_end},
        "features": {
            "builder": "make_logdiff_panel_features",
            "n_features": 1440,
            "lookback": 5,
        },
        "model_protocol": {
            "models": list(MODELS),
            "n_pca": int(args.n_pca),
            "min_train": int(args.min_train),
            "retrain_step": int(args.retrain_step),
            "horizon": int(args.horizon),
            "purge": int(args.horizon),
            "label": "cross_sectional_rank_labels",
        },
        "portfolio": {
            "top_n": int(args.top_n),
            "weighting": "equal",
        },
        "backtest": {
            "trade_at": "close",
            "signal_lag": SIGNAL_LAG,
            "note": "close 出信号并同日 close 成交" if SIGNAL_LAG == 0 else "forward close-to-close after signal lag",
            "return": "same-bar close fill when signal_lag=0",
            "commission": COMMISSION,
            "commission_bp": COMMISSION * 10_000,
            "slippage_bp": SLIPPAGE_BP,
            "total_cost_bp": COMMISSION * 10_000 + SLIPPAGE_BP,
        },
    }
    (output / "params.json").write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")

    comparison_rows: list[dict[str, object]] = []
    equity_rows: list[pd.DataFrame] = []
    features = make_logdiff_panel_features(panel)

    model_started = time.perf_counter()
    multi = expanding_pca_multi_model_scores(
        panel,
        models=MODELS,
        horizon=int(args.horizon),
        min_train=int(args.min_train),
        retrain_step=int(args.retrain_step),
        n_pca=int(args.n_pca),
        features=features,
    )
    print(
        json.dumps(
            {
                "event": "scores_done",
                "models": list(MODELS),
                "elapsed_sec": round(time.perf_counter() - model_started, 1),
            },
            ensure_ascii=False,
        )
    )

    for model, result in multi.items():
        result.scores.to_frame().to_parquet(output / f"scores_{model}.parquet")
        result.fold_metrics.to_csv(output / f"fold_metrics_{model}.csv", index=False)
        pd.DataFrame([result.overall_metrics]).to_csv(
            output / f"overall_metrics_{model}.csv",
            index=False,
        )

        score_df = result.scores.unstack(level="symbol")
        weights = rank_scores_to_weights(
            score_df,
            close,
            top_n=int(args.top_n),
            weighting="equal",
        )
        weights = hold_weights_on_calendar(weights, dates=close.index, symbols=close.columns)
        weights.to_parquet(output / f"target_weights_{model}.parquet")

        first_signal = weights.index[weights.sum(axis=1).gt(0.0)].min()
        oos_start = None if pd.isna(first_signal) else str(first_signal.date())
        backtest = _backtest(panel, weights, start_date=oos_start)
        backtest.result_df.to_parquet(output / f"performance_{model}.parquet")
        (output / f"performance_{model}.png").write_bytes(
            plot_backtest_performance(
                backtest.result_df,
                title=f"Lesson 07 · {model} · Top {args.top_n} equal weight",
            )
        )

        comparison_rows.append(_metric_row(model, backtest))
        eq = backtest.result_df[["equity", "return", "drawdown"]].reset_index(names="eob")
        eq.insert(0, "method", model)
        equity_rows.append(eq)
        print(
            json.dumps(
                {
                    "model": model,
                    "oos_start": oos_start,
                    "sharpe_ratio": backtest.metrics.get("sharpe_ratio"),
                },
                ensure_ascii=False,
            )
        )

    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(output / "comparison.csv", index=False)
    overall_metrics = comparison[
        ["model", "ann_return", "sharpe_ratio", "max_drawdown", "annual_turnover", "observations"]
    ].copy()
    overall_metrics.to_csv(output / "overall_metrics.csv", index=False)

    equities = pd.concat(equity_rows, ignore_index=True)
    chart_start = str(comparison["oos_start"].min())
    (output / "performance_comparison.png").write_bytes(
        plot_equity_comparison(
            equities,
            start=chart_start,
            title="Lesson 07 · ols / lasso / rf / xgboost · Top 3 equal weight",
        )
    )
    (output / "performance_comparison_drawdown.png").write_bytes(
        _plot_drawdown_comparison(
            equities,
            start=chart_start,
            title="Lesson 07 · drawdown comparison",
        )
    )

    elapsed = time.perf_counter() - started
    readme = [
        "# Lesson 07 · 18 ETF LogDiff + Expanding PCA + ML Rank",
        "",
        "## 口径",
        "",
        f"- 样本区间：{sample_start} 至 {sample_end}；OOS 回测自首个非零权重日起（约 min_train={args.min_train} 之后）。",
        f"- 特征：单标的 LogDiff 1440 列；fold 内 train-only PCA({args.n_pca})，不做额外标准化。",
        f"- 标签：{args.horizon} 日 forward return 的横截面百分位 rank；purge={args.horizon}。",
        f"- 组合：每日按预测分数选 Top {args.top_n}，等权；权重在信号日之间前向持有。",
        f"- 回测：close 成交，signal_lag={SIGNAL_LAG}，佣金 {COMMISSION * 10_000:g}bp + 滑点 {SLIPPAGE_BP:g}bp。",
        f"- 模型：{', '.join(MODELS)}。",
        "",
        "## 复现",
        "",
        "```bash",
        "uv run python -m strategies.cross_sectional.workflows.run_lesson07_etf18_logdiff_pca_ml",
        "```",
        "",
        f"本次运行耗时约 {elapsed / 60:.1f} 分钟。",
    ]
    (output / "README.md").write_text("\n".join(readme), encoding="utf-8")

    print(
        json.dumps(
            {
                "output": str(output),
                "sample": {"start": sample_start, "end": sample_end},
                "oos_start": chart_start,
                "elapsed_sec": round(elapsed, 1),
                "comparison": comparison[
                    ["model", "ann_return", "sharpe_ratio", "max_drawdown", "annual_turnover"]
                ].to_dict("records"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
