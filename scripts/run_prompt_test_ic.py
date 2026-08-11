"""Run Horizon IC and Lagged IC for the six selected ETF18 factors.

Run:
    uv run python -m scripts.run_prompt_test_ic
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from skills.analyze.factor_information import compute_horizon_ic, compute_lagged_ic
from skills.compute.wrappers import Factor
from skills.report.charts import plot_horizon_ic, plot_lagged_ic
from skills.store.data_manager import DataManager
from skills.strategy.cross_sectional.factor_combination import orient_factor_frames
from strategies.cross_sectional.asset_class_rotation import (
    ASSET_CLASS_ETF_SYMBOLS,
    ASSET_CLASS_ETF_UNIVERSE,
    apply_asset_class_split_adjustments,
)
from strategies.cross_sectional.workflows.run_lesson06_multifactor import (
    CALIBRATION_END,
    CORE_FACTORS,
    END,
    FACTOR_SPECS,
    HORIZONS,
    LAGS,
    OOS_START,
    SIGNAL_LAG,
    START,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "prompt_test_ic"
LAGGED_HORIZONS = (1, 5, 10, 20)
MIN_CROSS_SECTION = 6


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test Horizon IC and Lagged IC for the selected ETF18 factors."
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--start", default=START)
    parser.add_argument("--calibration-end", default=CALIBRATION_END)
    parser.add_argument("--oos-start", default=OOS_START)
    parser.add_argument("--end", default=END)
    return parser.parse_args(argv)


def _load_panel(end: str) -> pd.DataFrame:
    panel = DataManager().read_symbols(
        list(ASSET_CLASS_ETF_SYMBOLS), frequency="1d_adj"
    )
    panel = apply_asset_class_split_adjustments(panel)
    dates = panel.index.get_level_values("eob")
    return panel.loc[
        (dates >= pd.Timestamp("2018-01-02")) & (dates <= pd.Timestamp(end))
    ]


def _compute_selected_factors(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    raw: dict[str, pd.DataFrame] = {}
    directions: dict[str, int] = {}
    for name in CORE_FACTORS:
        func, params, direction, _source, _label = FACTOR_SPECS[name]
        raw[name] = Factor(func, **params).cal_df(panel, dropna=False).reindex(
            columns=list(ASSET_CLASS_ETF_SYMBOLS)
        )
        directions[name] = int(direction)
    return orient_factor_frames(raw, directions)


def _coverage_table(panel: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    inverse_names = {symbol: name for name, symbol in ASSET_CLASS_ETF_UNIVERSE.items()}
    rows = []
    for symbol in ASSET_CLASS_ETF_SYMBOLS:
        bars = panel.xs(symbol, level="symbol")
        evaluation = bars.loc[
            (bars.index >= pd.Timestamp(start)) & (bars.index <= pd.Timestamp(end))
        ]
        rows.append(
            {
                "asset": inverse_names[symbol],
                "symbol": symbol,
                "input_first_eob": bars.index.min().date().isoformat(),
                "input_last_eob": bars.index.max().date().isoformat(),
                "input_rows": len(bars),
                "evaluation_first_eob": evaluation.index.min().date().isoformat(),
                "evaluation_last_eob": evaluation.index.max().date().isoformat(),
                "evaluation_rows": len(evaluation),
            }
        )
    return pd.DataFrame(rows)


def _factor_table() -> pd.DataFrame:
    rows = []
    for name in CORE_FACTORS:
        func, params, direction, source, label = FACTOR_SPECS[name]
        rows.append(
            {
                "factor": name,
                "display_name_zh": label,
                "callable": f"{func.__module__}.{func.__name__}",
                "parameters": repr(params),
                "direction": int(direction),
                "source": source,
            }
        )
    return pd.DataFrame(rows)


def _format_number(value: object) -> str:
    if isinstance(value, (float, np.floating)):
        return "NA" if not np.isfinite(value) else f"{value:.4f}"
    return str(value)


def _markdown_table(frame: pd.DataFrame) -> str:
    headers = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for values in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(_format_number(value) for value in values) + " |")
    return "\n".join(lines)


def _write_methodology(
    output: Path,
    *,
    horizon: pd.DataFrame,
    lagged: pd.DataFrame,
    coverage: pd.DataFrame,
    start: str,
    calibration_end: str,
    oos_start: str,
    end: str,
) -> None:
    h5 = horizon[
        (horizon["segment"] == "full") & (horizon["horizon"] == 5)
    ][["factor", "ic_mean", "hac_t", "hac_p", "effective_dates"]].sort_values(
        "ic_mean", ascending=False
    )
    decay = lagged[
        (lagged["segment"] == "full")
        & (lagged["horizon"] == 5)
        & (lagged["lag"].isin([0, 5, 20, 60]))
    ].pivot(index="factor", columns="lag", values="ic_mean")
    decay = decay.reindex(CORE_FACTORS).reset_index()
    decay.columns = [
        "factor" if column == "factor" else f"lag_{int(column)}_ic"
        for column in decay.columns
    ]
    actual_end = coverage["evaluation_last_eob"].max()
    reproduce = (
        "uv run python -m scripts.run_prompt_test_ic \\\n"
        f"  --output reports/prompt_test_ic --start {start} \\\n"
        f"  --calibration-end {calibration_end} --oos-start {oos_start} --end {end}"
    )
    report = [
        "# 正式 18 ETF 池：六因子 Horizon IC 与 Lagged IC 测试",
        "",
        "## 方法与数据口径",
        "",
        "- 数据：`data/market/1d_adj`；18 个标的全部来自公开的 "
        "`ASSET_CLASS_ETF_SYMBOLS`，并应用仓库登记的 ETF 拆分调整。",
        "- 因子：直接复用 Lesson 06 的六个 `CORE_FACTORS` 和 "
        "`FACTOR_SPECS`；按规格中的 `direction` 统一为数值越大越看多。",
        f"- 计算暖启动从 2018-01-02 开始；IC 评价期为 {start} 至 {end}，本地数据在该范围内的最后交易日为 {actual_end}。",
        f"- 分段：全样本 `{start}~{end}`；校准期 `{start}~{calibration_end}`；样本外 `{oos_start}~{end}`。",
        f"- Horizon IC：横截面 Spearman Rank IC，H={HORIZONS}，固定 lag=0。",
        f"- Lagged IC：H={list(LAGGED_HORIZONS)}，lag={LAGS}。",
        f"- 收益对齐：`P[t+{SIGNAL_LAG}+lag+H] / P[t+{SIGNAL_LAG}+lag] - 1`，即 `signal_lag={SIGNAL_LAG}`，以收盘价为收益端点。",
        f"- 每日有效横截面至少 {MIN_CROSS_SECTION} 个标的；每一行摘要使用 `H-1` 阶 Newey-West HAC 标准误、t 值、p 值和 95% 置信区间。",
        "- `effective_dates` 是该分段、因子、期限与延迟组合的有效日度横截面 IC 数量。",
        "",
        "## 全样本 H=5 摘要",
        "",
        _markdown_table(h5),
        "",
        "## 全样本 H=5 延迟衰减切片",
        "",
        _markdown_table(decay),
        "",
        "正 IC 表示因子排序方向与未来收益排序同向；负 IC 表示反向。Horizon IC 改变累计收益窗口，Lagged IC 改变信号等待时间，两者不可互换。",
        "",
        "## 输出文件",
        "",
        "- `horizon_ic_summary.csv`、`lagged_ic_summary.csv`：完整三分段统计摘要。",
        "- `factor_specifications.csv`：六因子的函数、参数、方向与来源。",
        "- `data_coverage.csv`：正式 18 ETF 池逐标的数据覆盖。",
        "- `horizon_ic_{full,calibration,oos}.png`、`lagged_ic_{full,calibration,oos}.png`：Report Skill 生成的图。",
        "",
        "## 复现命令",
        "",
        "```bash",
        reproduce,
        "```",
        "",
        "以上是统计研究结果，不构成投资建议。",
    ]
    (output / "methodology.md").write_text("\n".join(report), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)

    if not (
        pd.Timestamp(args.start)
        <= pd.Timestamp(args.calibration_end)
        < pd.Timestamp(args.oos_start)
        <= pd.Timestamp(args.end)
    ):
        raise ValueError("Expected start <= calibration_end < oos_start <= end")

    panel = _load_panel(args.end)
    factors = _compute_selected_factors(panel)
    prices = panel["close"].unstack("symbol").reindex(
        columns=list(ASSET_CLASS_ETF_SYMBOLS)
    )
    segments = {
        "full": (args.start, args.end),
        "calibration": (args.start, args.calibration_end),
        "oos": (args.oos_start, args.end),
    }

    horizon_result = compute_horizon_ic(
        factors,
        prices,
        horizons=HORIZONS,
        signal_lag=SIGNAL_LAG,
        segments=segments,
        min_cross_section=MIN_CROSS_SECTION,
    )
    lagged_result = compute_lagged_ic(
        factors,
        prices,
        horizons=LAGGED_HORIZONS,
        lags=LAGS,
        signal_lag=SIGNAL_LAG,
        segments=segments,
        min_cross_section=MIN_CROSS_SECTION,
    )

    horizon = horizon_result.summary
    lagged = lagged_result.summary
    horizon.to_csv(output / "horizon_ic_summary.csv", index=False)
    lagged.to_csv(output / "lagged_ic_summary.csv", index=False)
    _factor_table().to_csv(output / "factor_specifications.csv", index=False)
    coverage = _coverage_table(panel, args.start, args.end)
    coverage.to_csv(output / "data_coverage.csv", index=False)

    titles = {
        "full": "Horizon/Lagged IC · full sample",
        "calibration": "Horizon/Lagged IC · calibration",
        "oos": "Horizon/Lagged IC · out-of-sample",
    }
    for segment in segments:
        (output / f"horizon_ic_{segment}.png").write_bytes(
            plot_horizon_ic(
                horizon,
                factors=list(CORE_FACTORS),
                segment=segment,
                title=titles[segment].replace("Horizon/Lagged", "Horizon"),
            )
        )
        (output / f"lagged_ic_{segment}.png").write_bytes(
            plot_lagged_ic(
                lagged,
                factors=list(CORE_FACTORS),
                horizons=LAGGED_HORIZONS,
                segment=segment,
                title=titles[segment].replace("Horizon/Lagged", "Lagged"),
            )
        )

    _write_methodology(
        output,
        horizon=horizon,
        lagged=lagged,
        coverage=coverage,
        start=args.start,
        calibration_end=args.calibration_end,
        oos_start=args.oos_start,
        end=args.end,
    )
    print(output)


if __name__ == "__main__":
    main()
