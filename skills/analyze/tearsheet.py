"""Factor tearsheet generators: per-factor 4-panel PNG + per-pool HTML summary."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

logger = logging.getLogger(__name__)

_REPORTS_ROOT = Path(__file__).resolve().parent.parent.parent / "reports" / "factors"


def _sanitize(name: str) -> str:
    return (
        name.replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "_")
        .replace("=", "")
    )


def generate_factor_tearsheet(
    factor_id: str,
    pool_id: str,
    ic_series: pd.Series,
    group_return: pd.DataFrame,
    turnover: pd.DataFrame | None,
    ic_stat: dict,
    n: int = 5,
    output_dir: str | Path | None = None,
) -> str:
    """Render a 4-panel PNG tearsheet for a single factor.

    Panels: cumulative IC, layered cumulative returns, long-short excess,
    group turnover. Returns the written file path.
    """
    out_dir = Path(output_dir) if output_dir else _REPORTS_ROOT / pool_id
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{_sanitize(factor_id)}__n{n}.png"
    path = out_dir / filename

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    ax1 = axes[0, 0]
    if ic_series is not None and not ic_series.empty:
        ic_series.cumsum().plot(
            ax=ax1, title="Cumulative IC", grid=True, linewidth=1.5, color="steelblue"
        )
        ax1.axhline(y=0, color="r", linestyle="--", linewidth=1, alpha=0.5)
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Cumulative IC")

    ax2 = axes[0, 1]
    if group_return is not None and not group_return.empty:
        gr = group_return.copy()
        gr["Benchmark"] = group_return.mean(axis=1)
        (1 + gr).cumprod().plot(ax=ax2, title="Layered Effect Test", linewidth=1.5)
        ax2.legend(loc="best")
    ax2.grid(True, alpha=0.3)
    ax2.set_xlabel("Date")
    ax2.set_ylabel("Cumulative Return")

    ax3 = axes[1, 0]
    if group_return is not None and not group_return.empty and group_return.shape[1] >= 2:
        cum = (1 + group_return).cumprod()
        benchmark = cum.mean(axis=1)
        g = group_return.shape[1]
        top = cum.iloc[:, -1] - benchmark
        bot = -(cum.iloc[:, 0] - benchmark)
        tbd = pd.concat([bot, top, top + bot], axis=1)
        tbd.columns = ["Down_Benchmark", "Top_Benchmark", "Top_Down"]
        tbd.plot(ax=ax3, title=f"Long-Short (g={g})", linewidth=1.5)
        ax3.legend(loc="best")
    ax3.grid(True, alpha=0.3)
    ax3.set_xlabel("Date")
    ax3.set_ylabel("Excess Return")

    ax4 = axes[1, 1]
    if turnover is not None and not turnover.empty:
        turnover.plot(ax=ax4, title="Group Turnover", linewidth=1.5)
        mean_text = "\n".join(f"{k}: {v:.4f}" for k, v in turnover.mean().items())
        ax4.text(
            0.02,
            0.98,
            f"Mean Turnover:\n{mean_text}",
            transform=ax4.transAxes,
            verticalalignment="top",
            fontsize=9,
            bbox={"boxstyle": "round", "facecolor": "wheat", "alpha": 0.5},
        )
        ax4.legend(loc="best")
    ax4.grid(True, alpha=0.3)
    ax4.set_xlabel("Date")
    ax4.set_ylabel("Turnover")

    summary_lines = [
        f"factor_id: {factor_id}",
        f"pool: {pool_id}",
        f"n: {n}",
    ]
    for key in ("IC_mean", "IC_IR", "t_stat", "IC_count"):
        if key in ic_stat:
            summary_lines.append(f"{key}: {ic_stat[key]}")
    fig.suptitle(" | ".join(summary_lines), fontsize=11)

    plt.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, dpi=110)
    plt.close(fig)

    return str(path)


def generate_pool_summary_report(
    pool_id: str,
    output_path: str | Path | None = None,
    top_n_tearsheets: int = 0,
) -> str:
    """Render an HTML summary report for a pool from data/factor_test/{pool}/summary.parquet.

    The HTML contains a sortable ranking table (by |IC_IR|) plus any already-generated
    tearsheet thumbnails for the top factors (if `top_n_tearsheets > 0` and PNGs exist).
    """
    from skills.store.data_manager import DataManager

    dm = DataManager()
    summary = dm.read_factor_test_summary(pool_id)
    if summary.empty:
        raise ValueError(
            f"No factor test summary for pool {pool_id!r}; run screen_all_indicators first."
        )

    ordered = summary.reindex(
        summary["IC_IR"].abs().sort_values(ascending=False).index
    ).reset_index(drop=True)

    out_path = Path(output_path) if output_path else _REPORTS_ROOT / pool_id / "summary.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    table_html = ordered.to_html(
        index=False,
        float_format=lambda v: f"{v:.4f}" if isinstance(v, float) else v,
        classes="factor-summary",
        border=0,
    )

    thumbnails_html = ""
    if top_n_tearsheets > 0:
        factor_dir = _REPORTS_ROOT / pool_id
        imgs = []
        for _, row in ordered.head(top_n_tearsheets).iterrows():
            candidate = factor_dir / f"{_sanitize(row['factor_id'])}__n{int(row['n'])}.png"
            if candidate.exists():
                imgs.append(
                    f'<figure><img src="{candidate.name}" style="max-width:720px"/>'
                    f"<figcaption>{row['factor_id']} (n={int(row['n'])})</figcaption></figure>"
                )
        if imgs:
            thumbnails_html = "<h2>Top Factors</h2>\n" + "\n".join(imgs)

    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\"/>
<title>Factor Summary — {pool_id}</title>
<style>
body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 24px; }}
h1 {{ font-size: 20px; }}
table.factor-summary {{ border-collapse: collapse; font-size: 12px; }}
table.factor-summary th, table.factor-summary td {{ padding: 6px 10px; border-bottom: 1px solid #eee; text-align: right; }}
table.factor-summary th {{ background: #f7f7f7; text-align: center; }}
table.factor-summary td:first-child, table.factor-summary td:nth-child(2) {{ text-align: left; font-family: monospace; }}
figure {{ margin: 16px 0; }}
</style>
</head>
<body>
<h1>Factor Summary — {pool_id}</h1>
<p>Factors: {len(ordered)} | sorted by |IC_IR| desc.</p>
{table_html}
{thumbnails_html}
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
