"""Test correlation and Top-3 overlap for the formal Lesson 06 ETF factor pool.

Run:
    uv run python -m strategies.cross_sectional.workflows.run_prompt_test_correlation
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from skills.analyze.factor_information import (
    mean_daily_factor_rank_correlation,
    rolling_factor_rank_correlation,
    top_n_jaccard_overlap,
)
from skills.compute.wrappers import Factor
from skills.report.charts import plot_ic_heatmap, plot_rolling_pair_correlation
from skills.strategy.cross_sectional.factor_combination import orient_factor_frames
from strategies.cross_sectional.asset_class_rotation import ASSET_CLASS_ETF_UNIVERSE
from strategies.cross_sectional.workflows.run_lesson06_multifactor import (
    CORE_FACTORS,
    FACTOR_SPECS,
    _load_panel,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "reports" / "prompt_test_correlation"
DEFAULT_START = "2019-01-02"
DEFAULT_END = "2026-05-31"
DEFAULT_ROLLING_WINDOW = 252
DEFAULT_ROLLING_MIN_PERIODS = 126
DEFAULT_MIN_ASSETS = 6
DEFAULT_TOP_N = 3


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run factor-correlation and Top-N overlap diagnostics."
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--rolling-window", type=int, default=DEFAULT_ROLLING_WINDOW)
    parser.add_argument(
        "--rolling-min-periods", type=int, default=DEFAULT_ROLLING_MIN_PERIODS
    )
    parser.add_argument("--min-assets", type=int, default=DEFAULT_MIN_ASSETS)
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    return parser.parse_args(argv)


def _compute_selected_factors(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    raw: dict[str, pd.DataFrame] = {}
    directions: dict[str, int] = {}
    symbols = list(ASSET_CLASS_ETF_UNIVERSE.values())
    for name in CORE_FACTORS:
        func, params, direction, _source, _label = FACTOR_SPECS[name]
        raw[name] = Factor(func, **params).cal_df(panel, dropna=False).reindex(columns=symbols)
        directions[name] = int(direction)
    return orient_factor_frames(raw, directions)


def _common_sample(
    factors: Mapping[str, pd.DataFrame],
    *,
    start: str,
    end: str,
    min_assets: int,
) -> dict[str, pd.DataFrame]:
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    sliced = {
        name: frame.loc[(frame.index >= start_ts) & (frame.index <= end_ts)]
        for name, frame in factors.items()
    }
    availability = pd.concat(
        {name: frame.notna().sum(axis=1) for name, frame in sliced.items()}, axis=1
    )
    eligible = availability.ge(min_assets).all(axis=1)
    if not eligible.any():
        raise ValueError("No date has the required asset coverage for every factor.")
    dates = eligible.index[eligible]
    return {name: frame.loc[dates] for name, frame in sliced.items()}


def _pair_summary(
    correlation: pd.DataFrame,
    overlap: pd.DataFrame,
    rolling: pd.DataFrame,
) -> pd.DataFrame:
    pairs = []
    names = list(correlation)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            pairs.append(
                {
                    "factor_a": left,
                    "factor_b": right,
                    "mean_spearman": float(correlation.loc[left, right]),
                    "abs_mean_spearman": abs(float(correlation.loc[left, right])),
                    "mean_top3_jaccard": float(overlap.loc[left, right]),
                }
            )
    summary = pd.DataFrame(pairs)
    valid = rolling.dropna(subset=["correlation"]).sort_values("eob")
    stats = (
        valid.groupby(["factor_a", "factor_b"], as_index=False)["correlation"]
        .agg(
            rolling_mean="mean",
            rolling_std="std",
            rolling_min="min",
            rolling_max="max",
            rolling_observations="count",
        )
    )
    latest = (
        valid.groupby(["factor_a", "factor_b"], as_index=False)
        .tail(1)[["factor_a", "factor_b", "eob", "correlation"]]
        .rename(columns={"eob": "latest_eob", "correlation": "latest_rolling_spearman"})
    )
    summary = summary.merge(stats, on=["factor_a", "factor_b"], how="left")
    summary = summary.merge(latest, on=["factor_a", "factor_b"], how="left")
    summary["rolling_range"] = summary["rolling_max"] - summary["rolling_min"]
    return summary.sort_values("abs_mean_spearman", ascending=False).reset_index(drop=True)


def _markdown_table(frame: pd.DataFrame) -> str:
    headers = list(frame.columns)
    rows = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for values in frame.itertuples(index=False, name=None):
        cells = []
        for value in values:
            if isinstance(value, (float, np.floating)):
                cells.append(f"{value:.4f}")
            else:
                cells.append(str(value))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _write_report(
    output: Path,
    summary: pd.DataFrame,
    *,
    requested_start: str,
    requested_end: str,
    actual_start: pd.Timestamp,
    actual_end: pd.Timestamp,
    observations: int,
    rolling_window: int,
    rolling_min_periods: int,
    min_assets: int,
    top_n: int,
) -> None:
    strongest_corr = summary.nlargest(5, "abs_mean_spearman")[
        ["factor_a", "factor_b", "mean_spearman", "latest_rolling_spearman"]
    ]
    strongest_overlap = summary.nlargest(5, "mean_top3_jaccard")[
        ["factor_a", "factor_b", "mean_top3_jaccard", "mean_spearman"]
    ]
    largest_ranges = summary.nlargest(5, "rolling_range")[
        ["factor_a", "factor_b", "rolling_min", "rolling_max", "rolling_range"]
    ]
    high_corr_count = int(summary["abs_mean_spearman"].ge(0.7).sum())
    high_overlap_count = int(summary["mean_top3_jaccard"].ge(0.5).sum())
    report = f"""# 正式 18 ETF 六因子相关性与 Top 3 重叠度测试

## 主要发现

- 15 个因子对中，{high_corr_count} 对的全样本平均绝对 Spearman 相关性不低于 0.70，{high_overlap_count} 对的平均 Top 3 Jaccard 重叠度不低于 0.50；这些组合存在明显的重复暴露。
- 最高相关因子对为 `{strongest_corr.iloc[0].factor_a}` / `{strongest_corr.iloc[0].factor_b}`，平均相关性 {strongest_corr.iloc[0].mean_spearman:.4f}，样本末 {rolling_window} 日滚动相关性 {strongest_corr.iloc[0].latest_rolling_spearman:.4f}。
- Top 3 重叠最高的因子对为 `{strongest_overlap.iloc[0].factor_a}` / `{strongest_overlap.iloc[0].factor_b}`，平均 Jaccard 为 {strongest_overlap.iloc[0].mean_top3_jaccard:.4f}。
- 滚动区间最大的因子对为 `{largest_ranges.iloc[0].factor_a}` / `{largest_ranges.iloc[0].factor_b}`，滚动相关性从 {largest_ranges.iloc[0].rolling_min:.4f} 到 {largest_ranges.iloc[0].rolling_max:.4f}；静态均值不能替代时变监控。

### 平均绝对相关性最高的 5 对

{_markdown_table(strongest_corr)}

### Top 3 重叠度最高的 5 对

{_markdown_table(strongest_overlap)}

### 滚动相关区间最大的 5 对

{_markdown_table(largest_ranges)}

## 方法说明

- 因子池：现有 Lesson 06 `CORE_FACTORS` 六因子；参数、函数和方向直接读取既有 `FACTOR_SPECS`，不另行重定义。
- 资产池：`ASSET_CLASS_ETF_UNIVERSE` 的 18 只 ETF/LOF；数据为 `data/market/1d_adj`，并沿用正式工作流的公开拆分调整。
- 请求区间：{requested_start} 至 {requested_end}；满足共同覆盖后的实际检验区间为 {actual_start.date()} 至 {actual_end.date()}，共 {observations} 个交易日。
- 共同样本：每个交易日要求六个因子各自至少有 {min_assets} 只可用资产，再对三项检验使用完全一致的日期集合，避免长窗口 warm-up 把 Top 3 重叠度机械压低。
- 截面相关性：调用 Analyze Skill 的 `mean_daily_factor_rank_correlation`；逐日计算两个已统一方向因子的横截面 Spearman 相关性，再对日期取均值。
- 滚动相关性：调用 `rolling_factor_rank_correlation`；对逐日横截面 Spearman 做 {rolling_window} 日滚动均值，至少 {rolling_min_periods} 个有效日。
- Top {top_n} 重叠度：调用 `top_n_jaccard_overlap`；逐日取每个因子排名最高的 {top_n} 只资产，计算 `|A∩B| / |A∪B|` 后按日期取均值。
- 图片：使用 Report Skill；矩阵调用 `plot_ic_heatmap`，滚动历史调用 `plot_rolling_pair_correlation`。

![全样本平均截面 Spearman 相关性](mean_daily_spearman_correlation.png)

![252 日滚动截面 Spearman 相关性](rolling_252d_spearman_correlation.png)

![Top 3 Jaccard 重叠度](top3_jaccard_overlap.png)

## 复现命令

```bash
uv run python -m strategies.cross_sectional.workflows.run_prompt_test_correlation \\
  --output reports/prompt_test_correlation \\
  --start {requested_start} \\
  --end {requested_end} \\
  --rolling-window {rolling_window} \\
  --rolling-min-periods {rolling_min_periods} \\
  --min-assets {min_assets} \\
  --top-n {top_n}
```

完整数字见 `mean_daily_spearman_correlation.csv`、`rolling_252d_spearman_correlation.csv`、`top3_jaccard_overlap.csv` 和 `pair_summary.csv`。本报告为研究诊断，不构成投资建议。
"""
    (output / "report.md").write_text(report, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.top_n <= 0:
        raise ValueError("top-n must be positive")
    if args.min_assets < args.top_n:
        raise ValueError("min-assets must be at least top-n")
    if args.rolling_window <= 0:
        raise ValueError("rolling-window must be positive")
    if not 0 < args.rolling_min_periods <= args.rolling_window:
        raise ValueError("rolling-min-periods must be between 1 and rolling-window")
    if pd.Timestamp(args.start) > pd.Timestamp(args.end):
        raise ValueError("start must not be after end")

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)

    panel = _load_panel(args.end)
    factors = _common_sample(
        _compute_selected_factors(panel),
        start=args.start,
        end=args.end,
        min_assets=args.min_assets,
    )
    correlation = mean_daily_factor_rank_correlation(factors)
    rolling = rolling_factor_rank_correlation(
        factors, window=args.rolling_window, min_periods=args.rolling_min_periods
    )
    overlap = top_n_jaccard_overlap(factors, top_n=args.top_n)
    summary = _pair_summary(correlation, overlap, rolling)

    correlation.to_csv(output / "mean_daily_spearman_correlation.csv")
    rolling.to_csv(output / "rolling_252d_spearman_correlation.csv", index=False)
    overlap.to_csv(output / "top3_jaccard_overlap.csv")
    summary.to_csv(output / "pair_summary.csv", index=False)

    definitions = []
    for name in CORE_FACTORS:
        func, params, direction, source, label = FACTOR_SPECS[name]
        definitions.append(
            {
                "factor": name,
                "display_name_zh": label,
                "callable": f"{func.__module__}.{func.__name__}",
                "params": json.dumps(params, ensure_ascii=False, sort_keys=True),
                "direction": int(direction),
                "source": source,
            }
        )
    pd.DataFrame(definitions).to_csv(output / "factor_definitions.csv", index=False)
    pd.DataFrame(
        [
            {"asset_class": asset_class, "symbol": symbol}
            for asset_class, symbol in ASSET_CLASS_ETF_UNIVERSE.items()
        ]
    ).to_csv(output / "universe.csv", index=False)

    (output / "mean_daily_spearman_correlation.png").write_bytes(
        plot_ic_heatmap(
            correlation,
            "Mean daily cross-sectional Spearman correlation",
            vmin=-1.0,
            vmax=1.0,
            annotate=True,
            dpi=180,
        )
    )
    (output / "rolling_252d_spearman_correlation.png").write_bytes(
        plot_rolling_pair_correlation(
            rolling,
            title=f"Rolling {args.rolling_window}-day cross-sectional Spearman correlation",
            dpi=180,
        )
    )
    (output / "top3_jaccard_overlap.png").write_bytes(
        plot_ic_heatmap(
            overlap,
            f"Mean Top-{args.top_n} Jaccard overlap",
            vmin=0.0,
            vmax=1.0,
            annotate=True,
            dpi=180,
        )
    )

    dates = next(iter(factors.values())).index
    config = {
        "data_frequency": "1d_adj",
        "universe": list(ASSET_CLASS_ETF_UNIVERSE.values()),
        "factors": definitions,
        "requested_start": str(args.start),
        "requested_end": str(args.end),
        "actual_start": str(dates.min().date()),
        "actual_end": str(dates.max().date()),
        "observations": int(len(dates)),
        "min_assets_per_factor": int(args.min_assets),
        "rolling_window": int(args.rolling_window),
        "rolling_min_periods": int(args.rolling_min_periods),
        "top_n": int(args.top_n),
    }
    (output / "experiment_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_report(
        output,
        summary,
        requested_start=args.start,
        requested_end=args.end,
        actual_start=dates.min(),
        actual_end=dates.max(),
        observations=len(dates),
        rolling_window=args.rolling_window,
        rolling_min_periods=args.rolling_min_periods,
        min_assets=args.min_assets,
        top_n=args.top_n,
    )


if __name__ == "__main__":
    main()
