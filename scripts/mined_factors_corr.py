"""Thin orchestration: correlation matrix among qualified mined factor candidates.

Computes the stacked cross-sectional correlation between every qualified
candidate's factor values (after direction adjustment) so the PoolSynthesizer
can do diversity-aware dedup. Thin orchestration only; factor math lives in
the mined_factors modules.
"""

from __future__ import annotations

import importlib
import json
from itertools import combinations

import pandas as pd

from skills.compute.wrappers import Factor
from skills.store.data_manager import DataManager
from strategies.cross_sectional.asset_class_rotation import (
    ASSET_CLASS_ETF_UNIVERSE,
    apply_asset_class_split_adjustments,
)

START = "2019-01-01"
END = "2026-08-04"
FREQUENCY = "1d_adj"
UNIVERSE = list(ASSET_CLASS_ETF_UNIVERSE.values())
EVAL_CSV = "reports/strategy_examples/mined_factors_eval.csv"


def load_qualified() -> dict[str, dict]:
    """Load qualified candidates from the eval CSV (func_name/module/params/direction)."""
    df = pd.read_csv(EVAL_CSV)
    df = df[df["qualified"] == True]  # noqa: E712
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        out[r["factor_id"]] = {
            "module": r.get("module") or None,  # CSV may not carry module; fall back below
            "func_name": r["func_name"],
            "params": json.loads(r["params"]) if isinstance(r["params"], str) else {},
            "direction": r["direction"],
            "family": r["family"],
            "eff_ic": float(r["effective_IC"]),
        }
    # The eval CSV does not carry the module field; resolve via collect_candidates.
    from scripts.evaluate_mined_factors import collect_candidates

    cand_module = {c.factor_id: (c.module or c.family) for c in collect_candidates()}
    for fid, meta in out.items():
        meta["module"] = cand_module.get(fid, meta["family"])
    return out


def load_panel() -> pd.DataFrame:
    dm = DataManager()
    panel = dm.read_symbols(UNIVERSE, frequency=FREQUENCY)
    panel = apply_asset_class_split_adjustments(panel)
    return panel.loc[(slice(None), slice(pd.Timestamp(START), pd.Timestamp(END))), :]


def compute_wide(factor_id: str, panel: pd.DataFrame, qualified: dict) -> pd.Series:
    meta = qualified[factor_id]
    import strategies.cross_sectional.mined_factors as pkg

    mod = importlib.import_module(f"{pkg.__name__}.{meta['module']}")
    func = getattr(mod, meta["func_name"])
    scores = Factor(func, **meta["params"]).calculate(panel, dropna=True)
    sign = 1.0 if meta["direction"] == "positive" else -1.0
    return sign * scores


def main() -> None:
    print("Loading panel ...")
    panel = load_panel()
    print(f"  panel: {panel.shape[0]} rows")

    qualified = load_qualified()
    print(f"  qualified: {len(qualified)} candidates")

    wide: dict[str, pd.Series] = {}
    for fid in qualified:
        try:
            wide[fid] = compute_wide(fid, panel, qualified)
            print(f"  computed {fid}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [error] {fid}: {exc}")

    # Pairwise stacked cross-sectional correlation
    fids = list(wide)
    print("\nPairwise cross-sectional correlation (direction-adjusted):")
    corr_rows = []
    for a, b in combinations(fids, 2):
        sa, sb = wide[a], wide[b]
        joined = pd.concat([sa.rename("a"), sb.rename("b")], axis=1).dropna()
        if len(joined) < 30:
            continue
        c = float(joined["a"].corr(joined["b"]))
        corr_rows.append({"a": a, "b": b, "corr": round(c, 3), "abs": round(abs(c), 3)})
        flag = "  <<<" if abs(c) > 0.7 else ""
        print(f"  {a:34s} ~ {b:34s}  corr={c:+.3f}{flag}")

    # Correlation matrix
    mat = pd.DataFrame(index=fids, columns=fids, dtype=float)
    for fid in fids:
        mat.loc[fid, fid] = 1.0
    for r in corr_rows:
        mat.loc[r["a"], r["b"]] = r["corr"]
        mat.loc[r["b"], r["a"]] = r["corr"]
    print("\nCorrelation matrix:")
    print(mat.round(3).to_string())

    family_of = {fid: qualified[fid]["family"] for fid in fids}
    print("\nFamily distribution of qualified:")
    for fam in sorted(set(family_of.values())):
        members = [f for f, ff in family_of.items() if ff == fam]
        print(f"  {fam}: {members}")

    # Greedy diverse top-5: order by eff IC desc, add if |corr|<0.7 with all picked & family<2
    order = sorted(fids, key=lambda f: qualified[f]["eff_ic"], reverse=True)
    picked: list[str] = []
    fam_count: dict[str, int] = {}
    for fid in order:
        fam = family_of[fid]
        if fam_count.get(fam, 0) >= 2:
            continue
        ok = True
        for p in picked:
            joined = pd.concat([wide[fid].rename("a"), wide[p].rename("b")], axis=1).dropna()
            if len(joined) >= 30:
                c = float(joined["a"].corr(joined["b"]))
                if abs(c) > 0.7:
                    ok = False
                    break
        if ok:
            picked.append(fid)
            fam_count[fam] = fam_count.get(fam, 0) + 1
        if len(picked) >= 5:
            break
    print("\nSuggested diverse top-5 (eff IC desc, |corr|<0.7, family<=2):")
    for i, fid in enumerate(picked, 1):
        m = qualified[fid]
        print(
            f"  {i}. {fid:34s} family={m['family']:16s} "
            f"dir={m['direction']:8s} eff_IC={m['eff_ic']:+.4f}"
        )

    import os

    out = "reports/strategy_examples/mined_factors_corr.csv"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    mat.to_csv(out)
    print(f"\nCorrelation matrix written: {out}")


if __name__ == "__main__":
    main()
