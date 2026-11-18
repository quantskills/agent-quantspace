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
import os
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


# ---------------------------------------------------------------------------
# strategies/factor_mining workflow: every phase through its command line
# ---------------------------------------------------------------------------

MINING = "factor_mining_workflow"
MINING_JOBS = str(min(8, os.cpu_count() or 1))


def mining(research, label: str, *args: str) -> dict:
    """Run one workflow phase; returns the JSON summary it prints."""
    out = research.work.dir / "out" / MINING
    completed = run_module(
        research.work, f"{MINING} ({label})", RESEARCH_SCRIPTS[MINING],
        "--brief", str(out / "brief.json"), "--output-dir", str(out), *args,
    )  # fmt: skip
    return json.loads(completed.stdout[completed.stdout.index("{") :])


@pytest.fixture(scope="module")
def mining_screening(research):
    out = research.work.dir / "out" / MINING
    out.mkdir(parents=True)
    brief = mining(research, "init", "--phase", "init")
    screening = mining(research, "screening", "--phase", "screening", "--jobs", MINING_JOBS)
    assert screening["contains_sealed_rows"] is False
    return out, brief


def test_factor_mining_screening_phase(mining_screening):
    out, _brief = mining_screening
    assert_files(out, ["brief.json", "screening_index.json", "screening_results.csv"])
    screening = csv(out / "screening_results.csv")
    assert screening["factor_id"].is_unique and len(screening) == 19
    # A candidate may fail the preflight (a causality hard failure is a valid research
    # outcome); the ones that pass must carry finite statistics.
    passed = screening[~screening["preflight_failed"]]
    assert len(passed) >= 2
    assert_finite(passed, ["train_rank_ic_mean", "validation_rank_ic_mean"])


def test_factor_mining_pool_freeze_and_sealed_test(research, mining_screening):
    """Two factors enter the pool in turn, both are frozen, and the sealed split opens."""
    out, brief = mining_screening
    namespace = f"factor_mining.{brief['brief_id']}"
    index = json_file(out / "screening_index.json")
    clean = [
        row
        for row in index["candidates"]
        if not row["preflight_failed"] and not row["splits"]["validation"]["failed"]
    ]
    chosen = sorted(clean, key=lambda row: -row["splits"]["validation"]["rank_ic_mean"])[:2]
    assert len(chosen) == 2

    def draft(factor_id: str, role_id: str) -> tuple[Path, dict, list[dict]]:
        """The skeleton the workflow writes for a role, and the evidence it may cite."""
        result = mining(
            research, f"draft {factor_id} {role_id}",
            "--phase", "draft", "--factor", factor_id, "--role", role_id,
        )  # fmt: skip
        path, evidence = (Path(item) for item in result["files"])
        return path, json_file(path), json_file(evidence)["choices"]

    def record(type_name: str, path: Path, payload: dict) -> dict:
        """Fill in the judgement, fill the hash with the contract command, then record."""
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        final = path.with_suffix(".final.json")
        run_module(
            research.work, f"validate {path.stem}", "skills", "factor-mining", "validate",
            type_name, "--file", str(path), "--fill-hash", "--output", str(final),
        )  # fmt: skip
        return mining(research, f"record {path.stem}", "--phase", "record", "--object", str(final))

    for position, row in enumerate(chosen):
        factor_id = row["factor_id"]
        for role_id in ("methodology_critic", "leakage_and_code_reviewer"):
            path, payload, _ = draft(factor_id, role_id)
            record("ReviewReport", path, {**payload, "conclusion": "pass"})
        compared = mining(research, f"compare {position}", "--phase", "compare", "--factor", factor_id)  # fmt: skip
        assert len(compared["pool_factor_ids"]) == position
        assert json_file(out / f"compare.{factor_id}.p{position}.json")["hard_failed"] is False
        path, payload, choices = draft(factor_id, "pool_synthesizer")
        if position == 0:
            cited = next(c for c in choices if c.get("check") == "POOL_UNAVAILABLE")
        else:
            cited = next(c for c in choices if c.get("fact") == "pool_spearman_corr_max_abs")
            assert math.isfinite(cited["value"])
        accepted = record(
            "PoolDecision",
            path,
            {
                **payload,
                "decision": "accept",
                "incremental_evidence": [cited["evidence"]],
                "residual_risks": ["POOL_INCREMENTAL_UNAVAILABLE"] if position == 0 else [],
            },
        )
        assert len(accepted["pool_factor_ids"]) == position + 1

    approved = [row["factor_id"] for row in chosen]
    frozen = mining(research, "freeze", "--phase", "freeze", "--approve", ",".join(approved))
    assert len(frozen["manifest_hashes"]) == 2
    final = mining(research, "final", "--phase", "final", "--write")
    assert final["factor_ids"] == approved and final["contains_sealed_rows"] is True
    sealed = json_file(out / "final_summary.json")["sealed"]
    assert [row["factor_id"] for row in sealed] == approved
    assert all(not row["failed"] and math.isfinite(row["rank_ic_ir"]) for row in sealed)
    # Formal objects went into the throwaway data root, not the real one.
    assert any((research.work.data_root / "factors" / namespace).rglob("*.json"))


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
