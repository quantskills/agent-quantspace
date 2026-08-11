"""Thin orchestration harness: evaluate AI-mined ETF factor candidates.

Supervisor-side Phase 02 (compute) + Phase 03 (analyze) entrypoint for the
factor_mining skill. Loads the 18-ETF panel once, then for every candidate
declared in ``strategies.cross_sectional.mined_factors`` computes the factor
via ``skills.compute.wrappers.Factor`` and evaluates Rank IC via
``skills.analyze.factor_analysis.IC_stat``.

Usage::

    uv run python -m scripts.evaluate_mined_factors
    uv run python -m scripts.evaluate_mined_factors --out reports/strategy_examples/mined_factors_eval.csv

This script is thin orchestration only; factor math lives in the mined_factors
modules and IC math lives in skills.analyze.
"""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from skills.analyze.factor_analysis import IC_stat
from skills.compute.wrappers import Factor
from skills.store.data_manager import DataManager
from strategies.cross_sectional.asset_class_rotation import (
    ASSET_CLASS_ETF_UNIVERSE,
    apply_asset_class_split_adjustments,
)

# ---------------------------------------------------------------------------
# Research Brief (frozen by Supervisor)
# ---------------------------------------------------------------------------

BRIEF_ID = "etf18-factor-mining-2019-2026-v2"
UNIVERSE = list(ASSET_CLASS_ETF_UNIVERSE.values())
START = "2019-01-01"
END = "2026-08-04"
FREQUENCY = "1d_adj"
IC_THRESHOLD = 0.03
REBALANCE_N = 5

# Canonical family modules + revision modules (revision generators write to
# ``<family>_revise2`` files but keep the canonical ``family`` classification).
FAMILY_MODULES = (
    "trend_momentum",
    "mean_reversion",
    "volume_liquidity",
    "volatility_risk",
)
REVISION_MODULES = (
    "trend_momentum_revise2",
    "volatility_risk_revise2",
)
ALL_MINED_MODULES = FAMILY_MODULES + REVISION_MODULES


@dataclass
class Candidate:
    factor_id: str
    family: str
    hypothesis: str
    direction: str  # "positive" | "negative"
    func_name: str
    params: dict[str, Any] = field(default_factory=dict)
    module: str = ""  # module name where func_name lives; "" -> use family


def collect_candidates() -> list[Candidate]:
    """Import every mined_factors module (canonical + revision)."""
    import strategies.cross_sectional.mined_factors as pkg

    out: list[Candidate] = []
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        if mod_info.name not in ALL_MINED_MODULES:
            continue
        module = importlib.import_module(f"{pkg.__name__}.{mod_info.name}")
        raw_list = getattr(module, "CANDIDATES", [])
        for entry in raw_list:
            out.append(
                Candidate(
                    factor_id=entry["factor_id"],
                    family=entry.get("family", mod_info.name),
                    hypothesis=entry.get("hypothesis", ""),
                    direction=entry.get("direction", "positive"),
                    func_name=entry["func_name"],
                    params=dict(entry.get("params", {})),
                    module=entry.get("module", ""),
                )
            )
    return out


def load_panel() -> pd.DataFrame:
    dm = DataManager()
    panel = dm.read_symbols(UNIVERSE, frequency=FREQUENCY)
    panel = apply_asset_class_split_adjustments(panel)
    panel = panel.loc[
        (slice(None), slice(pd.Timestamp(START), pd.Timestamp(END))), :
    ]
    return panel


@dataclass
class Evaluation:
    candidate: Candidate
    ic_mean: float
    ic_std: float
    ic_ir: float
    ic_positive_ratio: float
    ic_count: int
    t_stat: float
    p_value: float
    effective_ic: float
    qualified: bool
    error: str | None = None
    values_wide: pd.DataFrame | None = None

    def summary_line(self) -> str:
        if self.error is not None:
            return f"[error] {self.candidate.factor_id:28s} {self.error}"
        flag = "PASS" if self.qualified else "fail"
        return (
            f"[{flag}] {self.candidate.factor_id:28s} "
            f"IC={self.ic_mean:+.4f} eff={self.effective_ic:+.4f} "
            f"IR={self.ic_ir:+.4f} IC>0={self.ic_positive_ratio:.2%} "
            f"t={self.t_stat:+.2f} n={self.ic_count} ({self.candidate.family})"
        )


def evaluate_candidate(
    candidate: Candidate, panel: pd.DataFrame, *, n: int = REBALANCE_N
) -> Evaluation:
    import strategies.cross_sectional.mined_factors as pkg

    mod_name = candidate.module or candidate.family
    family_module = importlib.import_module(f"{pkg.__name__}.{mod_name}")
    func = getattr(family_module, candidate.func_name)

    try:
        factor = Factor(func, **candidate.params)
        scores = factor.calculate(panel, dropna=True)
    except Exception as exc:  # noqa: BLE001 - research stage tolerates per-factor failures
        return Evaluation(
            candidate=candidate,
            ic_mean=float("nan"),
            ic_std=float("nan"),
            ic_ir=float("nan"),
            ic_positive_ratio=float("nan"),
            ic_count=0,
            t_stat=float("nan"),
            p_value=float("nan"),
            effective_ic=float("nan"),
            qualified=False,
            error=f"compute: {exc}",
        )

    if scores.empty:
        return Evaluation(
            candidate=candidate,
            ic_mean=float("nan"),
            ic_std=float("nan"),
            ic_ir=float("nan"),
            ic_positive_ratio=float("nan"),
            ic_count=0,
            t_stat=float("nan"),
            p_value=float("nan"),
            effective_ic=float("nan"),
            qualified=False,
            error="empty scores",
        )

    values_wide = scores.unstack("symbol").sort_index()

    df = panel[["close"]].copy()
    df["fac_val"] = scores
    df = df.dropna(subset=["close", "fac_val"])
    df = df.reorder_levels(["eob", "symbol"]).sort_index()
    if df.empty:
        return Evaluation(
            candidate=candidate,
            ic_mean=float("nan"),
            ic_std=float("nan"),
            ic_ir=float("nan"),
            ic_positive_ratio=float("nan"),
            ic_count=0,
            t_stat=float("nan"),
            p_value=float("nan"),
            effective_ic=float("nan"),
            qualified=False,
            error="empty aligned frame",
        )

    try:
        ic_stat_dict, _ = IC_stat(df, rank_IC=True, n=n)
    except Exception as exc:  # noqa: BLE001
        return Evaluation(
            candidate=candidate,
            ic_mean=float("nan"),
            ic_std=float("nan"),
            ic_ir=float("nan"),
            ic_positive_ratio=float("nan"),
            ic_count=0,
            t_stat=float("nan"),
            p_value=float("nan"),
            effective_ic=float("nan"),
            qualified=False,
            error=f"ic: {exc}",
        )

    ic_mean = float(ic_stat_dict["IC_mean"])
    effective_ic = ic_mean if candidate.direction == "positive" else -ic_mean
    return Evaluation(
        candidate=candidate,
        ic_mean=ic_mean,
        ic_std=float(ic_stat_dict["IC_std"]),
        ic_ir=float(ic_stat_dict["IC_IR"]),
        ic_positive_ratio=float(ic_stat_dict["IC_>0"]),
        ic_count=int(ic_stat_dict["IC_count"]),
        t_stat=float(ic_stat_dict["t_stat"]),
        p_value=float(ic_stat_dict["p_value"]),
        effective_ic=effective_ic,
        qualified=effective_ic >= IC_THRESHOLD,
        values_wide=values_wide,
    )


def run(out_path: str | None = None) -> list[Evaluation]:
    print("=" * 80)
    print(f"Factor Mining Evaluation Harness — Brief: {BRIEF_ID}")
    print("=" * 80)
    print(f"Universe: {len(UNIVERSE)} ETFs  | Sample: {START} ~ {END} | Freq: {FREQUENCY}")
    print(f"Threshold: Rank IC effective >= {IC_THRESHOLD} | Rebalance N = {REBALANCE_N}")
    print()

    print("[1/2] Loading panel ...")
    panel = load_panel()
    eob_index = panel.index.get_level_values("eob")
    print(
        f"  panel: {panel.shape[0]} rows, "
        f"{eob_index.min().date()} ~ {eob_index.max().date()}"
    )
    print()

    print("[2/2] Collecting candidates and evaluating IC ...")
    candidates = collect_candidates()
    print(f"  collected {len(candidates)} candidates from {len(FAMILY_MODULES)} families")
    print()

    evaluations: list[Evaluation] = []
    for c in candidates:
        ev = evaluate_candidate(c, panel)
        evaluations.append(ev)
        print(f"  {ev.summary_line()}")

    print()
    qualified = [e for e in evaluations if e.qualified]
    print(f"Qualified (effective IC >= {IC_THRESHOLD}): {len(qualified)} / {len(evaluations)}")

    if out_path:
        rows = []
        for e in evaluations:
            rows.append(
                {
                    "factor_id": e.candidate.factor_id,
                    "family": e.candidate.family,
                    "func_name": e.candidate.func_name,
                    "params": json.dumps(e.candidate.params, ensure_ascii=False),
                    "direction": e.candidate.direction,
                    "hypothesis": e.candidate.hypothesis,
                    "IC_mean": round(e.ic_mean, 4) if e.error is None else None,
                    "effective_IC": round(e.effective_ic, 4) if e.error is None else None,
                    "IC_IR": round(e.ic_ir, 4) if e.error is None else None,
                    "IC_pos_ratio": round(e.ic_positive_ratio, 4) if e.error is None else None,
                    "t_stat": round(e.t_stat, 4) if e.error is None else None,
                    "p_value": round(e.p_value, 4) if e.error is None else None,
                    "IC_count": e.ic_count,
                    "qualified": e.qualified,
                    "error": e.error,
                }
            )
        import os

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        pd.DataFrame(rows).to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"  written: {out_path}")

    return evaluations


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        default="reports/strategy_examples/mined_factors_eval.csv",
        help="CSV output path for full evaluation table.",
    )
    args = p.parse_args()
    run(out_path=args.out)
