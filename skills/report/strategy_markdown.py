"""HTML report helpers for public strategy examples."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from skills.report.charts import plot_backtest_performance
from skills.report.renderer import ReportRenderer, relative_catalog_href


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
    sample_start: str | None = None


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


def _sample_start(report: StrategyReport) -> str:
    if report.sample_start:
        return str(report.sample_start)
    if report.result_df.empty:
        return ""
    return str(pd.Timestamp(report.result_df.index.min()).date())


def _tail_html(df: pd.DataFrame, columns: list[str], rows: int = 5) -> str:
    available = [column for column in columns if column in df.columns]
    if not available or df.empty:
        return ""
    view = df[available].tail(rows).copy()
    view.index = pd.to_datetime(view.index).strftime("%Y-%m-%d")
    view.index.name = "Date"
    formatted = view.copy()
    for column in formatted.columns:
        formatted[column] = [_fmt(value) for value in formatted[column].tolist()]
    return formatted.to_html()


def _metric_rows(metrics: dict[str, Any]) -> list[tuple[str, str]]:
    return [(str(key), _fmt(metrics[key])) for key in sorted(metrics)]


def _catalog_href(output_dir: Path) -> str:
    return relative_catalog_href(output_dir, output_dir.parent)


def write_strategy_report(
    report: StrategyReport,
    output_dir: str | Path,
    *,
    chart_png: bytes | None = None,
) -> Path:
    """Write one strategy HTML report and its PNG performance chart."""
    path_dir = Path(output_dir)
    path_dir.mkdir(parents=True, exist_ok=True)
    png = chart_png or plot_backtest_performance(
        report.result_df, title=f"{report.title} Performance"
    )
    chart_path = path_dir / f"{report.slug}_performance.png"
    chart_path.write_bytes(png)

    renderer = ReportRenderer(output_dir=path_dir)
    html = renderer.render(
        "strategy_example",
        {
            "title": report.title,
            "domain": report.domain,
            "strategy_type": report.strategy_type,
            "label": report.label,
            "description": report.description,
            "chart_png": png,
            "metrics": _metric_rows(report.metrics),
            "notes": list(report.notes),
            "tail_html": _tail_html(
                report.result_df,
                ["return", "raw_return", "cum_return", "drawdown", "turnover"],
            ),
            "catalog_href": _catalog_href(path_dir),
        },
    )
    path = renderer.save(html, f"{report.slug}.html")
    stale_md = path_dir / f"{report.slug}.md"
    if stale_md.exists():
        stale_md.unlink()
    return path


def write_strategy_index(reports: list[StrategyReport], output_dir: str | Path) -> Path:
    """Write the strategy example index HTML file."""
    path_dir = Path(output_dir)
    path_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for report in reports:
        metrics = report.metrics
        rows.append(
            {
                "title": report.title,
                "href": f"{report.slug}.html",
                "domain": report.domain,
                "strategy_type": report.strategy_type,
                "start": _sample_start(report),
                "sharpe": _fmt(metrics.get("sharpe_ratio", np.nan)),
                "total_return": _fmt(metrics.get("total_return", np.nan)),
                "max_drawdown": _fmt(metrics.get("max_drawdown", np.nan)),
            }
        )
    renderer = ReportRenderer(output_dir=path_dir)
    html = renderer.render(
        "strategy_index",
        {
            "title": "Strategy Example Reports",
            "intro": (
                "These reports are generated from PandaData daily listed-fund and "
                "futures bars saved under data/market/1d/. They are compact public "
                "examples, not proof of long-term production robustness."
            ),
            "reproduce_command": "uv run python -m scripts.run_strategy_reports",
            "rows": rows,
            "catalog_href": _catalog_href(path_dir),
        },
    )
    path = renderer.save(html, "index.html")
    stale_readme = path_dir / "README.md"
    if stale_readme.exists():
        stale_readme.unlink()
    return path


__all__ = ["StrategyReport", "write_strategy_index", "write_strategy_report"]
