"""Opt-in smoke run of the course and research reproduction scripts on real local data.

Each script runs unchanged, at its defaults, as ``python -m <module>`` from a scratch
directory with PYTHONPATH set to the repository root, a throwaway data root holding the
full 1d_adj history of the 18 asset-class ETFs, and a throwaway reports root. Scripts whose
default output sits under the repository ``reports/`` get an explicit ``--output`` (or
``--output-dir``) inside the scratch directory; the rest write to relative paths that land
in the scratch directory. Guards fail the run if the source data root or the repository
``reports/`` tree changes.

Assertions are sanity checks only: exit status, expected files that exist and are
non-empty, non-empty key tables, finite headline numbers.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests.smoke.coverage import RESEARCH_SCRIPTS
from tests.smoke.runner import run_module

pytestmark = [pytest.mark.smoke, pytest.mark.research]

PNG = b"\x89PNG\r\n\x1a\n"


def run_script(research, key: str, *args: str) -> Path:
    """Run one registered script; returns its output directory (relative outputs: cwd)."""
    work = research.work
    run_module(work, key, RESEARCH_SCRIPTS[key], *args)
    return work.dir / "out" / key


def with_output(research, key: str, flag: str = "--output") -> tuple[str, ...]:
    return flag, str(research.work.dir / "out" / key)


def assert_files(directory: Path, names) -> None:
    for name in names:
        path = directory / name
        assert path.is_file() and path.stat().st_size > 0, path
        if path.suffix == ".png":
            assert path.read_bytes().startswith(PNG)


def csv(path: Path, **kwargs) -> pd.DataFrame:
    frame = pd.read_csv(path, **kwargs)
    assert not frame.empty, path
    return frame


def assert_finite(frame: pd.DataFrame, columns) -> None:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
        assert np.isfinite(values).all(), column


def json_file(path: Path) -> dict:
    assert path.is_file() and path.stat().st_size > 0, path
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# strategies/ workflows
# ---------------------------------------------------------------------------


def test_lesson06_multifactor(research):
    out = run_script(
        research, "lesson06_multifactor", *with_output(research, "lesson06_multifactor")
    )
    assert_files(
        out,
        [
            "experiment_config.json", "experiment_report.md", "ic_information_surface.csv",
            "daily_ic.parquet", "factor_correlation_full.csv", "factor_rolling_correlation.csv",
            "combination_performance.csv", "rebalance_comparison.csv", "factor_weights.csv",
            "target_weights.csv", "equity_curves_full.png", "ic_information_surface.png",
            "factor_weights.png",
        ],
    )  # fmt: skip
    performance = csv(out / "combination_performance.csv")
    assert_finite(performance, ["total_return", "max_drawdown", "ann_return", "sharpe_ratio"])
    assert {"full", "calibration"} <= set(performance["segment"])
    weights = csv(out / "factor_weights.csv")
    assert (weights["weight"] >= -1e-9).all() and weights["weight"].notna().all()
    assert not pd.read_parquet(out / "daily_ic.parquet").empty
    assert json_file(out / "experiment_config.json")


def test_lesson07_pca_ml(research):
    out = run_script(research, "lesson07_pca_ml", *with_output(research, "lesson07_pca_ml"))
    models = ["ols", "lasso", "rf", "xgboost"]
    assert_files(
        out,
        ["params.json", "README.md", "comparison.csv", "overall_metrics.csv"]
        + ["performance_comparison.png", "performance_comparison_drawdown.png"]
        + [f"{kind}_{model}.{suffix}" for model in models
           for kind, suffix in (("scores", "parquet"), ("target_weights", "parquet"),
                                ("fold_metrics", "csv"), ("performance", "parquet"))],
    )  # fmt: skip
    comparison = csv(out / "comparison.csv")
    assert set(comparison["model"]) == set(models)
    assert_finite(comparison, ["total_return", "max_drawdown", "ann_return", "sharpe_ratio"])
    assert json_file(out / "params.json")
    for model in models:
        weights = pd.read_parquet(out / f"target_weights_{model}.parquet")
        assert (weights.fillna(0.0).sum(axis=1) <= 1.0 + 1e-9).all()


def test_lesson07_horizon_sensitivity(research):
    out = run_script(
        research,
        "lesson07_horizon_sensitivity",
        *with_output(research, "lesson07_horizon_sensitivity"),
    )
    assert_files(
        out,
        ["params.json", "README.md", "comparison.csv", "ml_overall_metrics.csv"]
        + ["equities_long.parquet", "performance_by_horizon.png", "performance_by_model.png"]
        + ["heatmap_ann_return.png", "heatmap_sharpe.png", "heatmap_rank_ic.png"],
    )  # fmt: skip
    comparison = csv(out / "comparison.csv")
    assert set(comparison["horizon"]) == {1, 5, 10, 22}
    assert len(comparison) == 16
    assert_finite(comparison, ["total_return", "max_drawdown", "ann_return", "sharpe_ratio"])
    metrics = csv(out / "ml_overall_metrics.csv")
    assert_finite(metrics, ["mse", "rank_ic"])
    assert not pd.read_parquet(out / "equities_long.parquet").empty


def test_prompt_test_correlation(research):
    out = run_script(
        research, "prompt_test_correlation", *with_output(research, "prompt_test_correlation")
    )
    assert_files(
        out,
        [
            "report.md", "experiment_config.json", "factor_definitions.csv", "universe.csv",
            "mean_daily_spearman_correlation.csv", "rolling_252d_spearman_correlation.csv",
            "top3_jaccard_overlap.csv", "pair_summary.csv", "mean_daily_spearman_correlation.png",
            "rolling_252d_spearman_correlation.png", "top3_jaccard_overlap.png",
        ],
    )  # fmt: skip
    matrix = csv(out / "mean_daily_spearman_correlation.csv", index_col=0)
    assert matrix.shape[0] == matrix.shape[1] > 1
    assert np.allclose(np.diag(matrix.to_numpy(dtype=float)), 1.0)
    assert (matrix.abs() <= 1.0 + 1e-9).all().all()
    summary = csv(out / "pair_summary.csv")
    assert_finite(summary, ["mean_spearman", "mean_top3_jaccard", "rolling_mean"])
    assert len(csv(out / "universe.csv")) == 18


def test_ma_cross_report(research):
    work = research.work
    completed = run_module(work, "ma_cross_report", RESEARCH_SCRIPTS["ma_cross_report"])
    assert completed.stdout.strip()
    study = work.reports_root / "ma_cross" / "shse510300_ma10_ma60"
    assert_files(study, ["index.html", "params.json", "artifacts/metrics.csv"])
    metrics = json_file(study / "params.json")["metrics"]
    assert metrics and all(
        math.isfinite(value) for value in metrics.values() if isinstance(value, (int, float))
    )
    assert_files(work.reports_root, ["catalog.html", "catalog.json"])
    catalog = json_file(work.reports_root / "catalog.json")
    assert any(item.get("slug") == "shse510300_ma10_ma60" for item in catalog)
    assert not csv(study / "artifacts" / "metrics.csv").empty


# ---------------------------------------------------------------------------
# scripts/
# ---------------------------------------------------------------------------


def test_mine_etf18_factors_prints_its_summary(research):
    completed = run_module(
        research.work, "mine_etf18_factors", RESEARCH_SCRIPTS["mine_etf18_factors"]
    )
    assert "Summary Table:" in completed.stdout
    assert "Appendix: All candidates ranked" in completed.stdout


@pytest.fixture(scope="module")
def governed_screening(research):
    out = run_script(
        research, "mine_etf18_factors_governed", "--phase", "screening",
        *with_output(research, "mine_etf18_factors_governed", "--output-dir"),
    )  # fmt: skip
    return out


def test_governed_mining_screening_phase(governed_screening):
    assert_files(governed_screening, ["screening_results.csv", "screening_manifest.json"])
    screening = csv(governed_screening / "screening_results.csv")
    assert screening["factor_id"].is_unique and len(screening) >= 3
    assert screening["compute_failure"].isna().all()
    assert_finite(screening, ["train_rank_ic_mean", "train_rank_ic_ir"])
    assert json_file(governed_screening / "screening_manifest.json")


def test_governed_mining_final_phase_opens_the_sealed_window_once(research, governed_screening):
    run_module(
        research.work, "mine_etf18_factors_governed (final)",
        RESEARCH_SCRIPTS["mine_etf18_factors_governed"], "--phase", "final",
        "--output-dir", str(governed_screening),
    )  # fmt: skip
    assert_files(governed_screening, ["selected_factors.csv", "final_manifest.json"])
    selected = csv(governed_screening / "selected_factors.csv")
    assert_finite(selected, ["sealed_rank_ic_mean", "full_rank_ic_mean"])
    assert json_file(governed_screening / "final_manifest.json")["sealed_opened_once"] is True
    formal = sorted((governed_screening / "formal_analyze").glob("*.json"))
    assert len(formal) == len(selected) and all(json_file(path) for path in formal)
    # Governed artifacts went into the throwaway data root, not the real one.
    assert any((research.work.data_root / "factors").rglob("*"))


def test_evaluate_then_correlate_mined_factors(research):
    work = research.work
    run_module(work, "evaluate_mined_factors", RESEARCH_SCRIPTS["evaluate_mined_factors"])
    evaluation = work.dir / "reports" / "strategy_examples" / "mined_factors_eval.csv"
    assert_files(evaluation.parent, ["mined_factors_eval.csv"])
    table = csv(evaluation, encoding="utf-8-sig")
    # The script records a per-factor evaluation error instead of stopping (a saturated
    # factor has no cross-sectional variation, hence no valid IC); most factors must evaluate.
    failed = table[table["error"].notna()]
    assert len(failed) < len(table) / 2 and (failed["IC_count"] == 0).all()
    evaluated = table[table["error"].isna()]
    assert (evaluated["IC_count"] > 0).all()
    assert_finite(evaluated, ["IC_mean", "IC_IR"])
    # mined_factors_corr reads that CSV by its relative path, so it runs from the same cwd.
    run_module(work, "mined_factors_corr", RESEARCH_SCRIPTS["mined_factors_corr"])
    matrix = csv(evaluation.parent / "mined_factors_corr.csv", index_col=0)
    assert matrix.shape[0] == matrix.shape[1] > 1
    assert np.allclose(np.diag(matrix.to_numpy(dtype=float)), 1.0)
    assert (matrix.abs() <= 1.0 + 1e-9).all().all()


def test_prompt_test_ic(research):
    out = run_script(research, "prompt_test_ic", *with_output(research, "prompt_test_ic"))
    assert_files(
        out,
        [
            "methodology.md", "horizon_ic_summary.csv", "lagged_ic_summary.csv",
            "factor_specifications.csv", "data_coverage.csv", "horizon_ic_full.png",
            "lagged_ic_full.png",
        ],
    )  # fmt: skip
    horizon = csv(out / "horizon_ic_summary.csv")
    assert_finite(horizon, ["ic_mean", "icir"])
    assert len(csv(out / "data_coverage.csv")) == 18


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


def test_scripts_left_the_source_data_and_repository_reports_untouched(research):
    research.assert_untouched()
    assert research.work.data_root.resolve() != research.source_root.resolve()
