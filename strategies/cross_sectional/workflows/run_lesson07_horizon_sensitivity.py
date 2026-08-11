"""Lesson 07 horizon × model sensitivity (signal_lag=0, close-to-close).

Runs each (horizon, model) job in a process pool. LogDiff features are built once
and shared via parquet.

Run:
    uv run python -m strategies.cross_sectional.workflows.run_lesson07_horizon_sensitivity
    uv run python -m strategies.cross_sectional.workflows.run_lesson07_horizon_sensitivity --workers 8
"""

from __future__ import annotations

import argparse
import io
import json
import os
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg", force=True)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from skills.backtest import VectorBacktester
from skills.compute.features import make_logdiff_panel_features
from skills.ml.pca_fold import ModelKind
from skills.report.charts import plot_equity_comparison
from skills.store.data_manager import DataManager
from skills.strategy.cross_sectional import hold_weights_on_calendar
from strategies.cross_sectional.asset_class_rotation import ASSET_CLASS_ETF_SYMBOLS
from strategies.cross_sectional.ml_rank import (
    DEFAULT_RETRAIN_STEP,
    expanding_pca_multi_model_scores,
    rank_scores_to_weights,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "reports" / "lesson_07_etf18_horizon_sensitivity"
MODELS: tuple[ModelKind, ...] = ("lasso", "rf", "xgboost")
HORIZONS: tuple[int, ...] = (1, 5, 10, 22)

N_PCA = 50
MIN_TRAIN = 250
RETRAIN_STEP = DEFAULT_RETRAIN_STEP  # ~5 Expanding folds
TOP_N = 3
SIGNAL_LAG = 0
COMMISSION = 0.0002
SLIPPAGE_BP = 3.0


def _load_panel() -> pd.DataFrame:
    # Use pre-adjusted bars only. ``apply_asset_class_split_adjustments`` is for
    # raw ``1d`` prices that still jump on share-split dates; applying it again on
    # ``1d_adj`` double-adjusts (e.g. SHSE.513100 on 2022-01-14) and creates fake
    # ~100%+ portfolio spikes in the equity curve.
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


def _metric_row(model: str, horizon: int, result) -> dict[str, object]:
    return {
        "model": model,
        "horizon": horizon,
        **result.metrics,
        "annual_turnover": float(result.result_df["turnover"].mean() * 252.0),
        "observations": int(len(result.result_df)),
        "oos_start": str(result.result_df.index.min().date()),
        "oos_end": str(result.result_df.index.max().date()),
    }


def _run_one_horizon(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Worker entry: one horizon, all models, shared per-fold PCA."""
    started = time.perf_counter()
    horizon = int(payload["horizon"])
    models = tuple(payload["models"])
    output = Path(payload["output"])
    rf_n_jobs = int(payload["rf_n_jobs"])

    panel = pd.read_parquet(payload["panel_path"])
    features = pd.read_parquet(payload["features_path"])
    close = (
        panel["close"]
        .unstack(level="symbol")
        .sort_index()
        .reindex(columns=list(ASSET_CLASS_ETF_SYMBOLS))
    )

    multi = expanding_pca_multi_model_scores(
        panel,
        models=models,  # type: ignore[arg-type]
        horizon=horizon,
        min_train=int(payload["min_train"]),
        retrain_step=int(payload["retrain_step"]),
        n_pca=int(payload["n_pca"]),
        features=features,
        rf_n_jobs=rf_n_jobs,
    )

    payloads: list[dict[str, Any]] = []
    for model, result in multi.items():
        tag = f"h{horizon}_{model}"
        result.scores.to_frame().to_parquet(output / f"scores_{tag}.parquet")
        result.fold_metrics.to_csv(output / f"fold_metrics_{tag}.csv", index=False)

        score_df = result.scores.unstack(level="symbol")
        weights = rank_scores_to_weights(
            score_df,
            close,
            top_n=int(payload["top_n"]),
            weighting="equal",
        )
        weights = hold_weights_on_calendar(weights, dates=close.index, symbols=close.columns)
        weights.to_parquet(output / f"target_weights_{tag}.parquet")

        first_signal = weights.index[weights.sum(axis=1).gt(0.0)].min()
        backtest = _backtest(
            panel,
            weights,
            start_date=None if pd.isna(first_signal) else str(first_signal.date()),
        )
        backtest.result_df.to_parquet(output / f"performance_{tag}.parquet")

        eq = backtest.result_df[["equity", "return", "drawdown"]].reset_index(names="eob")
        eq.insert(0, "model", model)
        eq.insert(1, "horizon", horizon)
        eq.to_parquet(output / f"equity_{tag}.parquet")

        payloads.append(
            {
                "model": model,
                "horizon": horizon,
                "elapsed_sec": round(time.perf_counter() - started, 1),
                "comparison": _metric_row(model, horizon, backtest),
                "ml_overall": {"model": model, "horizon": horizon, **result.overall_metrics},
                "ann_return": backtest.metrics.get("ann_return"),
                "sharpe_ratio": backtest.metrics.get("sharpe_ratio"),
                "max_drawdown": backtest.metrics.get("max_drawdown"),
                "rank_ic": result.overall_metrics.get("rank_ic"),
            }
        )
    return payloads


def _plot_metric_heatmap(
    comparison: pd.DataFrame,
    *,
    value: str,
    title: str,
    fmt: str,
    models: Sequence[str],
    horizons: Sequence[int],
) -> bytes:
    pivot = comparison.pivot(index="model", columns="horizon", values=value)
    pivot = pivot.reindex(index=list(models), columns=list(horizons))
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    data = pivot.to_numpy(dtype=float)
    im = ax.imshow(data, aspect="auto", cmap="RdYlGn")
    ax.set_xticks(range(len(horizons)), [str(h) for h in horizons])
    ax.set_yticks(range(len(models)), list(models))
    ax.set_xlabel("Horizon (days)")
    ax.set_ylabel("Model")
    ax.set_title(title)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            ax.text(j, i, format(data[i, j], fmt), ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=160)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _plot_horizon_panels(
    equities: pd.DataFrame,
    *,
    start: str,
    models: Sequence[str],
    horizons: Sequence[int],
) -> bytes:
    n = len(horizons)
    nrows = 2 if n > 2 else 1
    ncols = int(np.ceil(n / nrows))
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 3.6 * nrows), sharex=True, sharey=True)
    axes_flat = np.atleast_1d(axes).ravel()
    for ax, horizon in zip(axes_flat, horizons, strict=False):
        subset = equities[(equities["horizon"] == horizon) & (equities["eob"] >= pd.Timestamp(start))]
        for model in models:
            frame = subset[subset["model"] == model].set_index("eob").sort_index()
            if frame.empty:
                continue
            equity = frame["equity"].astype(float)
            equity = equity.div(equity.iloc[0])
            ax.plot(equity.index, equity, lw=1.6, label=model)
        ax.set_title(f"horizon={horizon}d")
        ax.grid(alpha=0.16)
        ax.axhline(1.0, color="gray", lw=0.8, alpha=0.5)
    axes_flat[0].legend(loc="upper left", fontsize=8, frameon=False)
    for ax in axes_flat[len(horizons) :]:
        ax.set_visible(False)
    fig.suptitle("Net value by forecast horizon · Top3 equal · signal_lag=0", y=1.01)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=160)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _plot_model_panels(
    equities: pd.DataFrame,
    *,
    start: str,
    models: Sequence[str],
    horizons: Sequence[int],
) -> bytes:
    fig, axes = plt.subplots(1, len(models), figsize=(4.5 * len(models), 4.2), sharex=True, sharey=True)
    axes_list = np.atleast_1d(axes).ravel()
    for ax, model in zip(axes_list, models, strict=True):
        subset = equities[(equities["model"] == model) & (equities["eob"] >= pd.Timestamp(start))]
        for horizon in horizons:
            frame = subset[subset["horizon"] == horizon].set_index("eob").sort_index()
            if frame.empty:
                continue
            equity = frame["equity"].astype(float)
            equity = equity.div(equity.iloc[0])
            ax.plot(equity.index, equity, lw=1.6, label=f"h={horizon}")
        ax.set_title(model)
        ax.grid(alpha=0.16)
        ax.axhline(1.0, color="gray", lw=0.8, alpha=0.5)
        ax.legend(loc="upper left", fontsize=8, frameon=False, ncol=2)
    fig.suptitle("Net value by model across horizons · Top3 equal · signal_lag=0", y=1.02)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=160)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _default_workers() -> int:
    # One process per horizon; RF uses multiple threads inside each process.
    return max(1, min(len(HORIZONS), os.cpu_count() or 4))


def _rf_n_jobs_for_workers(workers: int) -> int:
    cpu = os.cpu_count() or 4
    return max(1, cpu // max(1, workers))


def _metrics_from_performance(result_df: pd.DataFrame) -> dict[str, float]:
    """Rebuild backtest summary metrics from a saved performance frame."""
    if result_df.empty:
        return {
            "ann_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "ann_volatility": 0.0,
            "total_return": 0.0,
        }
    returns = result_df["return"].astype(float)
    equity = result_df["equity"].astype(float)
    drawdown = result_df["drawdown"].astype(float)
    n = len(result_df)
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if n else 0.0
    ann_return = float((1.0 + total_return) ** (252.0 / n) - 1.0) if n else 0.0
    ann_volatility = float(returns.std(ddof=0) * np.sqrt(252.0)) if n else 0.0
    max_drawdown = abs(float(drawdown.min())) if n else 0.0
    sharpe = ann_return / ann_volatility if ann_volatility > 0 else 0.0
    return {
        "ann_return": ann_return,
        "sharpe_ratio": float(sharpe),
        "max_drawdown": max_drawdown,
        "ann_volatility": ann_volatility,
        "total_return": total_return,
    }


def _load_cached_job(output: Path, *, horizon: int, model: str) -> dict[str, Any] | None:
    """Load a previously finished job from on-disk artifacts, if complete."""
    tag = f"h{horizon}_{model}"
    equity_path = output / f"equity_{tag}.parquet"
    perf_path = output / f"performance_{tag}.parquet"
    fold_path = output / f"fold_metrics_{tag}.csv"
    if not (equity_path.is_file() and perf_path.is_file() and fold_path.is_file()):
        return None
    perf = pd.read_parquet(perf_path)
    metrics = _metrics_from_performance(perf)
    fold = pd.read_csv(fold_path)
    ml_overall: dict[str, Any] = {
        "model": model,
        "horizon": horizon,
        "rank_ic": float(fold["rank_ic"].mean()) if "rank_ic" in fold else np.nan,
        "pca_explained_variance_sum": (
            float(fold["pca_explained_variance_sum"].mean())
            if "pca_explained_variance_sum" in fold
            else np.nan
        ),
        "mse": float(fold["mse"].mean()) if "mse" in fold else np.nan,
        "rmse": float(fold["rmse"].mean()) if "rmse" in fold else np.nan,
        "r2": float(fold["r2"].mean()) if "r2" in fold else np.nan,
    }
    comparison = {
        "model": model,
        "horizon": horizon,
        **metrics,
        "annual_turnover": float(perf["turnover"].mean() * 252.0),
        "observations": int(len(perf)),
        "oos_start": str(pd.Timestamp(perf.index.min()).date()),
        "oos_end": str(pd.Timestamp(perf.index.max()).date()),
    }
    return {
        "model": model,
        "horizon": horizon,
        "elapsed_sec": 0.0,
        "comparison": comparison,
        "ml_overall": ml_overall,
        "ann_return": metrics["ann_return"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "rank_ic": ml_overall["rank_ic"],
        "cached": True,
    }


def _limit_blas_threads() -> None:
    """Keep spawned workers single-threaded.

    PCA/SVD calls multi-threaded BLAS by default, so N worker processes would each
    start one thread per core and thrash. Set before the pool spawns children.
    """
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ.setdefault(name, "1")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lesson 07 horizon × model sensitivity.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-train", type=int, default=MIN_TRAIN)
    parser.add_argument("--retrain-step", type=int, default=RETRAIN_STEP)
    parser.add_argument("--top-n", type=int, default=TOP_N)
    parser.add_argument("--n-pca", type=int, default=N_PCA)
    parser.add_argument("--workers", type=int, default=_default_workers())
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip (horizon, model) jobs that already have equity/performance/fold artifacts.",
    )
    parser.add_argument(
        "--horizons",
        default=",".join(str(h) for h in HORIZONS),
        help="Comma-separated horizons, e.g. 1,5,10,22",
    )
    parser.add_argument(
        "--models",
        default=",".join(MODELS),
        help="Comma-separated models: lasso,rf,xgboost",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    started = time.perf_counter()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)

    horizons = tuple(int(x) for x in str(args.horizons).split(",") if x.strip())
    models = tuple(x.strip() for x in str(args.models).split(",") if x.strip())
    for model in models:
        if model not in MODELS:
            raise ValueError(f"unsupported model: {model!r}")
    workers = max(1, int(args.workers))

    panel = _load_panel()
    dates = panel.index.get_level_values("eob").unique()
    sample_start = str(pd.Timestamp(dates.min()).date())
    sample_end = str(pd.Timestamp(dates.max()).date())

    print(json.dumps({"event": "building_features"}, ensure_ascii=False), flush=True)
    features = make_logdiff_panel_features(panel)
    panel_path = output / "_cache_panel.parquet"
    features_path = output / "_cache_features.parquet"
    panel.to_parquet(panel_path)
    features.to_parquet(features_path)

    params = {
        "data": {
            "frequency": "1d_adj",
            "universe": list(ASSET_CLASS_ETF_SYMBOLS),
        },
        "sample": {"start": sample_start, "end": sample_end},
        "model_protocol": {
            "models": list(models),
            "horizons": list(horizons),
            "n_pca": int(args.n_pca),
            "min_train": int(args.min_train),
            "retrain_step": int(args.retrain_step),
            "purge": "equals each horizon",
            "label": "cross_sectional_rank_labels",
        },
        "portfolio": {"top_n": int(args.top_n), "weighting": "equal"},
        "backtest": {
            "trade_at": "close",
            "signal_lag": SIGNAL_LAG,
            "note": "close 出信号并同日 close 成交",
            "commission": COMMISSION,
            "slippage_bp": SLIPPAGE_BP,
        },
        "parallel": {
            "workers": workers,
            "unit": "horizon (models share per-fold PCA)",
            "rf_n_jobs": _rf_n_jobs_for_workers(workers),
        },
    }
    (output / "params.json").write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")

    rf_n_jobs = _rf_n_jobs_for_workers(workers)
    comparison_rows: list[dict[str, object]] = []
    ml_rows: list[dict[str, object]] = []
    jobs: list[dict[str, Any]] = []
    n_cached_pairs = 0
    for horizon in horizons:
        if args.resume:
            cached_models = {
                model: _load_cached_job(output, horizon=horizon, model=model) for model in models
            }
            if all(cached_models[model] is not None for model in models):
                for model in models:
                    cached = cached_models[model]
                    assert cached is not None
                    comparison_rows.append(cached["comparison"])
                    ml_rows.append(cached["ml_overall"])
                    n_cached_pairs += 1
                    print(
                        json.dumps(
                            {
                                "event": "skip_cached",
                                "horizon": horizon,
                                "model": model,
                                "ann_return": cached["ann_return"],
                                "sharpe_ratio": cached["sharpe_ratio"],
                                "rank_ic": cached["rank_ic"],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                continue
        jobs.append(
            {
                "horizon": horizon,
                "models": list(models),
                "output": str(output),
                "panel_path": str(panel_path),
                "features_path": str(features_path),
                "min_train": int(args.min_train),
                "retrain_step": int(args.retrain_step),
                "n_pca": int(args.n_pca),
                "top_n": int(args.top_n),
                "rf_n_jobs": rf_n_jobs,
            }
        )
    print(
        json.dumps(
            {
                "event": "parallel_start",
                "n_horizon_jobs": len(jobs),
                "n_cached_pairs": n_cached_pairs,
                "workers": workers,
                "rf_n_jobs": rf_n_jobs,
                "retrain_step": int(args.retrain_step),
                "resume": bool(args.resume),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    if jobs:
        _limit_blas_threads()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_one_horizon, job): job for job in jobs}
            for fut in as_completed(futures):
                job = futures[fut]
                try:
                    results = fut.result()
                except Exception as exc:  # noqa: BLE001 — surface worker failure then stop
                    print(
                        json.dumps(
                            {
                                "event": "error",
                                "horizon": job["horizon"],
                                "models": job["models"],
                                "error": str(exc),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    raise
                for payload in results:
                    comparison_rows.append(payload["comparison"])
                    ml_rows.append(payload["ml_overall"])
                    print(
                        json.dumps(
                            {
                                "event": "done",
                                "horizon": payload["horizon"],
                                "model": payload["model"],
                                "elapsed_sec": payload["elapsed_sec"],
                                "ann_return": payload["ann_return"],
                                "sharpe_ratio": payload["sharpe_ratio"],
                                "max_drawdown": payload["max_drawdown"],
                                "rank_ic": payload["rank_ic"],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )

    panel_path.unlink(missing_ok=True)
    features_path.unlink(missing_ok=True)

    comparison = pd.DataFrame(comparison_rows).sort_values(["horizon", "model"]).reset_index(drop=True)
    comparison.to_csv(output / "comparison.csv", index=False)
    ml_metrics = pd.DataFrame(ml_rows).sort_values(["horizon", "model"]).reset_index(drop=True)
    ml_metrics.to_csv(output / "ml_overall_metrics.csv", index=False)

    equity_parts = [
        pd.read_parquet(output / f"equity_h{h}_{m}.parquet") for h in horizons for m in models
    ]
    equities = pd.concat(equity_parts, ignore_index=True)
    equities.to_parquet(output / "equities_long.parquet")
    chart_start = str(comparison["oos_start"].min())

    for horizon in horizons:
        subset = equities[equities["horizon"] == horizon].copy()
        plot_df = subset.rename(columns={"model": "method"})[
            ["method", "eob", "equity", "return", "drawdown"]
        ]
        (output / f"performance_h{horizon}_models.png").write_bytes(
            plot_equity_comparison(
                plot_df,
                start=chart_start,
                title=f"horizon={horizon}d · lasso/rf/xgboost · signal_lag=0",
            )
        )

    (output / "performance_by_horizon.png").write_bytes(
        _plot_horizon_panels(equities, start=chart_start, models=models, horizons=horizons)
    )
    (output / "performance_by_model.png").write_bytes(
        _plot_model_panels(equities, start=chart_start, models=models, horizons=horizons)
    )
    (output / "heatmap_ann_return.png").write_bytes(
        _plot_metric_heatmap(
            comparison,
            value="ann_return",
            title="Annualized return by model × horizon",
            fmt=".1%",
            models=models,
            horizons=horizons,
        )
    )
    (output / "heatmap_sharpe.png").write_bytes(
        _plot_metric_heatmap(
            comparison,
            value="sharpe_ratio",
            title="Sharpe by model × horizon",
            fmt=".2f",
            models=models,
            horizons=horizons,
        )
    )
    (output / "heatmap_rank_ic.png").write_bytes(
        _plot_metric_heatmap(
            ml_metrics,
            value="rank_ic",
            title="OOS Rank IC by model × horizon",
            fmt=".3f",
            models=models,
            horizons=horizons,
        )
    )

    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(horizons))
    width = 0.25
    for i, model in enumerate(models):
        vals = [
            float(
                comparison.loc[
                    (comparison.model == model) & (comparison.horizon == h), "ann_return"
                ].iloc[0]
            )
            for h in horizons
        ]
        ax.bar(x + (i - 1) * width, vals, width=width, label=model)
    ax.set_xticks(x, [str(h) for h in horizons])
    ax.set_xlabel("Horizon (days)")
    ax.set_ylabel("Ann. return")
    ax.set_title("Ann. return · model × horizon · signal_lag=0")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=160)
    plt.close(fig)
    (output / "bars_ann_return.png").write_bytes(buf.getvalue())

    elapsed = time.perf_counter() - started
    readme = [
        "# Lesson 07 · Horizon × Model Sensitivity",
        "",
        "## 口径",
        "",
        f"- 样本区间：{sample_start} 至 {sample_end}",
        f"- horizons：{', '.join(str(h) for h in horizons)}（purge=horizon）",
        f"- models：{', '.join(models)}",
        f"- Top {args.top_n} 等权；`signal_lag={SIGNAL_LAG}`（close 出信号并同日 close 成交）",
        f"- 成本：佣金 {COMMISSION * 10_000:g}bp + 滑点 {SLIPPAGE_BP:g}bp",
        f"- 并行：ProcessPoolExecutor workers={workers}",
        "",
        "## 图",
        "",
        "- `performance_by_horizon.png` — 每个 horizon 一张，三模型净值",
        "- `performance_by_model.png` — 每个模型一张，四 horizon 净值",
        "- `heatmap_ann_return.png` / `heatmap_sharpe.png` / `heatmap_rank_ic.png`",
        "- `bars_ann_return.png`",
        "",
        f"耗时约 {elapsed / 60:.1f} 分钟。",
    ]
    (output / "README.md").write_text("\n".join(readme), encoding="utf-8")

    print(
        json.dumps(
            {
                "output": str(output),
                "elapsed_sec": round(elapsed, 1),
                "workers": workers,
                "comparison": comparison[
                    ["model", "horizon", "ann_return", "sharpe_ratio", "max_drawdown", "annual_turnover"]
                ].to_dict("records"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
