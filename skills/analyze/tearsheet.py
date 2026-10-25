"""Factor tearsheet generator: per-factor 4-panel PNG."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from skills.store.workspace import resolve_workspace_paths  # noqa: E402

logger = logging.getLogger(__name__)

_REPORTS_ROOT = resolve_workspace_paths().reports_root / "factors"


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
    namespace: str,
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
    out_dir = Path(output_dir) if output_dir else _REPORTS_ROOT / namespace
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
        f"namespace: {namespace}",
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
