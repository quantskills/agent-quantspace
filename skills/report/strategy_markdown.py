"""Markdown report helpers for public strategy examples."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from skills.report.charts import plot_backtest_performance


@dataclass
class StrategyReport:
    """Portable strategy report payload."""

    slug: str
    title: str
    domain: str
    strategy_type: str
    label: str
    description: str
    metrics: dict[str, Any]
    result_df: pd.DataFrame
    notes: list[str]


def _fmt(value: Any) -> str:
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return "nan"
        if np.isinf(value):
            return "inf" if value > 0 else "-inf"
        return f"{float(value):.4f}"
    return str(value)


def _metrics_table(metrics: dict[str, Any]) -> str:
    rows = ["| Metric | Value |", "|---|---:|"]
    for key in sorted(metrics):
        rows.append(f"| `{key}` | {_fmt(metrics[key])} |")
    return "\n".join(rows)


def _tail_table(df: pd.DataFrame, columns: list[str], rows: int = 5) -> str:
    available = [column for column in columns if column in df.columns]
    if not available or df.empty:
        return "_No result rows._"
    view = df[available].tail(rows).copy()
    view.index = pd.to_datetime(view.index).strftime("%Y-%m-%d")
    header = "| Date | " + " | ".join(available) + " |"
    divider = "|---|" + "|".join("---:" for _ in available) + "|"
    lines = [header, divider]
    for idx, row in view.iterrows():
        values = " | ".join(_fmt(row[column]) for column in available)
        lines.append(f"| {idx} | {values} |")
    return "\n".join(lines)


def write_strategy_report(report: StrategyReport, output_dir: str | Path) -> Path:
    """Write one strategy Markdown report and its PNG performance chart."""
    path_dir = Path(output_dir)
    path_dir.mkdir(parents=True, exist_ok=True)
    chart_name = f"{report.slug}_performance.png"
    chart_path = path_dir / chart_name
    chart_path.write_bytes(
        plot_backtest_performance(report.result_df, title=f"{report.title} Performance")
    )

    path = path_dir / f"{report.slug}.md"
    content = f"""# {report.title}

## Summary

- Domain: `{report.domain}`
- Type: {report.strategy_type}
- Label: {report.label}

{report.description}

## Performance Chart

![Performance Chart]({chart_name})

## Metrics

{_metrics_table(report.metrics)}

## Notes

{chr(10).join(f"- {note}" for note in report.notes)}

## Recent Result Rows

{_tail_table(report.result_df, ["return", "raw_return", "cum_return", "drawdown", "turnover"])}
"""
    path.write_text(content, encoding="utf-8")
    return path


def write_strategy_index(reports: list[StrategyReport], output_dir: str | Path) -> Path:
    """Write the strategy report index markdown file."""
    path_dir = Path(output_dir)
    path_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        "| Strategy | Domain | Type | Start | Sharpe | Total Return | Max Drawdown |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for report in reports:
        metrics = report.metrics
        start = (
            pd.Timestamp(report.result_df.index.min()).date() if not report.result_df.empty else ""
        )
        rows.append(
            "| "
            + " | ".join(
                [
                    f"[{report.title}]({report.slug}.md)",
                    report.domain,
                    report.strategy_type,
                    str(start),
                    _fmt(metrics.get("sharpe_ratio", np.nan)),
                    _fmt(metrics.get("total_return", np.nan)),
                    _fmt(metrics.get("max_drawdown", np.nan)),
                ]
            )
            + " |"
        )

    path = path_dir / "README.md"
    path.write_text(
        "# Strategy Example Reports\n\n"
        "These reports are generated from PandaData daily futures bars saved under "
        "`data/market/1d/`. They are compact public examples, not proof of "
        "long-term production robustness.\n\n"
        "Run `uv run python scripts/run_strategy_reports.py` after refreshing local "
        "PandaData Parquet files.\n\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    return path


__all__ = ["StrategyReport", "write_strategy_index", "write_strategy_report"]
