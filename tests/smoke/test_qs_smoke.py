"""Opt-in smoke run of every non-network ``qs`` command on real local ETF data.

Run with ``uv run python -m pytest -m smoke``. The tests read the local data root, copy a
trimmed slice of it to a temporary directory and drive the installed ``qs`` script against
the copy. Assertions are sanity checks only (exit status, non-empty artifacts, finite key
numbers, weights that fit the budget), never equality pins against real data.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests.smoke.conftest import COMBINE_HORIZON, DIRECTIONS, FACTORS, HORIZONS
from tests.smoke.coverage import SKIPPED
from tests.smoke.runner import (
    ADJUSTED_SYMBOLS,
    INDEX_SYMBOL,
    KEEP_ROWS,
    SYMBOLS,
    artifact_paths,
    qs,
    snapshot,
)

pytestmark = pytest.mark.smoke

PNG = b"\x89PNG\r\n\x1a\n"
EPS = 1e-9


def finite_numbers(value) -> bool:
    """Every number nested in a JSON value is finite (nulls are allowed)."""
    if isinstance(value, dict):
        return all(finite_numbers(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(finite_numbers(item) for item in value)
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    return math.isfinite(value)


def assert_file(path: Path) -> Path:
    assert path.is_file() and path.stat().st_size > 0, path
    return path


def assert_png(path: Path) -> None:
    assert assert_file(path).read_bytes().startswith(PNG) and path.stat().st_size > 1000


def read(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(assert_file(path))
    assert not frame.empty, path
    return frame


def assert_weights_fit(weights: pd.DataFrame, budget: float = 1.0) -> None:
    assert (weights.fillna(0.0) >= -EPS).all().all()
    assert (weights.sum(axis=1) <= budget + EPS).all()


# ---------------------------------------------------------------------------
# root commands
# ---------------------------------------------------------------------------


def test_root_commands(work):
    version = qs(work, "version")
    assert version["data"]["version"] and version["data"]["factor_mining_schema_version"]
    catalog = qs(work, "catalog")
    assert len(catalog["data"]["commands"]) > 50
    schema = qs(work, "schema", "store.read", "--part", "input")
    assert "symbols" in schema["data"]["properties"]
    # The generated SKILL.md reference blocks are current.
    docs = qs(work, "docs", "render", "--check")
    assert docs["data"]["checked"] is True and docs["data"]["changed"] == []


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------


def test_store_info_and_list_describe_the_copy(work):
    info = qs(work, "store", "info")
    assert Path(info["data"]["data_root"]).resolve() == work.data_root.resolve()
    assert info["data"]["frequencies"]["1d"] >= len(SYMBOLS) + 1
    listing = qs(work, "store", "list", "--limit", "200")
    assert set(SYMBOLS) | {INDEX_SYMBOL} <= set(listing["data"]["items"])


def test_store_read_writes_the_requested_panel(panel):
    data = panel["envelope"]["data"]
    assert data["rows"] == len(SYMBOLS) * KEEP_ROWS and data["missing"] == []
    frame = read(panel["path"])
    assert set(frame.index.get_level_values("symbol")) == set(SYMBOLS)
    assert np.isfinite(frame["close"]).all() and (frame["close"] > 0).all()


def test_store_validate_and_check_adjusted_pass_on_real_bars(work):
    validated = qs(work, "store", "validate", "--symbols", ",".join(SYMBOLS))
    assert validated["data"]["passed"] is True and validated["data"]["n_rows"] > 0
    checked = qs(
        work, "store", "check-adjusted", "--symbols", ",".join(ADJUSTED_SYMBOLS),
        "--frequency", "1d_adj", "--output", "adjusted_issues.parquet",
    )  # fmt: skip
    assert checked["data"]["issues"] == 0 and checked["data"]["missing"] == []
    assert artifact_paths(checked)["issues"].is_file()


def test_store_import_round_trips_a_csv_exported_from_the_copy(work):
    exported = qs(
        work, "store", "read", "--symbols", "SHSE.510300", "--output", "export.csv", "--preview", "0"
    )  # fmt: skip
    csv = assert_file(artifact_paths(exported)["panel"])
    target = work.data_root / "market" / "1d" / "SHSE.510301.parquet"
    args = ["--file", str(csv), "--layout", "single", "--symbol", "SHSE.510301"]
    dry = qs(work, "store", "import", *args)
    assert dry["data"]["dry_run"] is True and not target.exists()
    written = qs(work, "store", "import", *args, "--write")
    assert written["data"]["dry_run"] is False
    imported = pd.read_parquet(assert_file(target))
    assert len(imported) == KEEP_ROWS and np.isfinite(imported["close"]).all()


# ---------------------------------------------------------------------------
# compute
# ---------------------------------------------------------------------------


def test_compute_indicator_catalog(work):
    listing = qs(work, "compute", "indicators", "list")
    names = {item["name"] for item in listing["data"]["indicators"]}
    assert {"roc", "rsi"} <= names
    shown = qs(work, "compute", "indicators", "show", "roc")
    assert shown["data"]["defaults"] == {"period": 20}


def test_compute_factor_wide_tables(factors):
    for name, envelope in factors["envelopes"].items():
        assert envelope["data"]["rows"] > KEEP_ROWS - 40 and envelope["data"]["nan_ratio"] < 0.1
        frame = read(factors["paths"][name])
        assert set(frame.columns) == set(SYMBOLS)
        assert np.isfinite(frame.to_numpy(dtype=float)).all(), name


def test_compute_factor_long_layout_and_keep_na(work, panel):
    long = qs(
        work, "compute", "factor", "--panel", str(panel["path"]), "--indicator", "roc",
        "-p", "period=10", "--output", "roc10_long.parquet",
    )  # fmt: skip
    frame = read(artifact_paths(long)["factor"])
    assert list(frame.columns) == ["symbol", "eob", "value"]
    kept = qs(
        work, "compute", "factor", "--panel", str(panel["path"]), "--indicator", "roc",
        "-p", "period=10", "--keep-na", "--output", "roc10_values.parquet",
    )  # fmt: skip
    assert kept["data"]["rows"] == len(SYMBOLS) * KEEP_ROWS
    assert 0 < kept["data"]["nan_ratio"] < 0.1


def test_compute_features_for_one_symbol(work, panel):
    one = qs(
        work, "store", "read", "--symbols", "SHSE.510300", "--output", "one_symbol.parquet",
        "--preview", "0",
    )  # fmt: skip
    envelope = qs(
        work, "compute", "features", "--panel", str(artifact_paths(one)["panel"]),
        "--lookback", "3", "--lags", "1", "--output", "features.parquet", "--preview", "0",
    )  # fmt: skip
    frame = read(artifact_paths(envelope)["features"])
    assert envelope["data"]["features"] == frame.shape[1] > 0
    assert np.isfinite(frame.to_numpy(dtype=float)).all()


def test_compute_labels(work, single_bars):
    forward = qs(
        work, "compute", "labels", "forward-return", "--bars", str(single_bars),
        "--horizon", "5", "--output", "forward_labels.parquet",
    )  # fmt: skip
    frame = read(artifact_paths(forward)["labels"])
    assert {"state", "forward_return"} <= set(frame.columns) and len(frame) == KEEP_ROWS
    barrier = qs(
        work, "compute", "labels", "triple-barrier", "--bars", str(single_bars),
        "--output", "barrier_labels.parquet",
    )  # fmt: skip
    frame = read(artifact_paths(barrier)["labels"])
    assert "state" in frame.columns and set(frame["state"].dropna()) <= {-1, 0, 1}


# ---------------------------------------------------------------------------
# strategy
# ---------------------------------------------------------------------------


def test_strategy_top_n_weights(targets):
    weights = read(targets["path"])
    assert (weights.gt(0).sum(axis=1) == 3).all()
    assert np.allclose(weights.sum(axis=1), 1.0)


def test_strategy_signal_weights(work, panel):
    one = qs(
        work, "store", "read", "--symbols", "SHSE.510300", "--output", "signal_panel.parquet",
        "--preview", "0",
    )  # fmt: skip
    signal = qs(
        work, "compute", "factor", "--panel", str(artifact_paths(one)["panel"]),
        "--indicator", "roc", "-p", "period=10", "--output", "signal.parquet",
    )  # fmt: skip
    envelope = qs(
        work, "strategy", "signal-weights", "--signal", str(artifact_paths(signal)["factor"]),
        "--column", "value", "--symbol", "SHSE.510300", "--output", "signal_weights.parquet",
        "--preview", "0",
    )  # fmt: skip
    weights = read(artifact_paths(envelope)["weights"])
    assert list(weights.columns) == ["SHSE.510300"] and weights.abs().max().max() <= 1.0


def test_strategy_hold_calendar_spreads_signal_day_weights(work, panel, targets):
    envelope = qs(
        work, "strategy", "hold-calendar", "--panel", str(panel["path"]),
        "--weights", str(targets["path"]), "--output", "held.parquet", "--preview", "0",
    )  # fmt: skip
    held = read(artifact_paths(envelope)["weights"])
    assert len(held) == KEEP_ROWS
    assert_weights_fit(held)


def test_strategy_combine_chain_on_oriented_inputs(factors, surface, correlation, combined):
    summary = surface["envelope"]["data"]["summary"]
    assert len(summary) == len(FACTORS) * len(HORIZONS) * 3 and finite_numbers(summary)
    daily = read(surface["paths"]["daily_ic"])
    assert set(daily["factor"]) == set(FACTORS) and set(daily["horizon"]) == set(HORIZONS)
    history = read(correlation["paths"]["correlation_history"])
    assert list(history.columns) == ["factor_a", "factor_b", "eob", "correlation"]
    latest = combined["envelope"]["data"]["latest_factor_weights"]
    assert set(latest) == set(FACTORS) and abs(sum(latest.values()) - 1.0) < 1e-6
    assert max(latest.values()) <= 0.6 + 1e-9
    factor_weights = read(combined["paths"]["factor_weights"])
    assert (factor_weights >= -EPS).all().all() and np.allclose(factor_weights.sum(axis=1), 1.0)
    # The window after the IC warm-up is genuinely dynamic, not equal weights.
    assert factor_weights.iloc[-1].nunique() > 1
    targets = read(combined["paths"]["target_weights"])
    assert_weights_fit(targets)
    assert not read(combined["paths"]["composite_scores"]).empty


def test_strategy_combine_equal_rank_needs_no_history(work, factors):
    args = [
        item for name, path in factors["paths"].items() for item in ("--factors", f"{name}={path}")
    ]
    envelope = qs(
        work, "strategy", "combine", *args, "--directions", json.dumps(DIRECTIONS),
        "--method", "equal_rank", "--top-n", "3", "--out-dir", "combined_equal", "--preview", "0",
    )  # fmt: skip
    assert_weights_fit(read(artifact_paths(envelope)["target_weights"]))


def test_strategy_cs_run_factor_voting(work, panel):
    factors = [
        {"indicator": "roc", "params": {"period": 10}, "name": "mom"},
        {"indicator": "rsi", "params": {"period": 14}, "name": "rsi", "direction": -1},
    ]
    envelope = qs(
        work, "strategy", "cs-run", "--panel", str(panel["path"]), "--factors", json.dumps(factors),
        "--slippage-bp", "1", "--top-pct", "0.4", "--rebalance-freq", "W", "--out-dir", "cs_run",
        "--preview", "0",
    )  # fmt: skip
    assert finite_numbers(envelope["data"]["metrics"]) and envelope["data"]["rows"] > 0
    paths = artifact_paths(envelope)
    assert_weights_fit(read(paths["signal_weights"]))
    assert not read(paths["result_df"]).empty and assert_file(paths["metrics"])


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------


def test_backtest_run_reports_finite_metrics(backtest_run):
    metrics = backtest_run["envelope"]["data"]["metrics"]
    assert finite_numbers(metrics) and metrics["total_transaction_cost"] >= 0
    result = read(backtest_run["paths"]["result_df"])
    assert np.isfinite(result["return"]).all() and (result["equity"] > 0).all()
    assert_weights_fit(read(backtest_run["paths"]["executed_weights"]))
    assert assert_file(backtest_run["paths"]["metrics"])


def test_backtest_weigh_equal_and_risk_parity(work, panel, targets):
    equal = qs(
        work, "backtest", "weigh", "--votes", str(targets["path"]), "--output", "weights_equal.parquet",
        "--preview", "0",
    )  # fmt: skip
    assert_weights_fit(read(artifact_paths(equal)["weights"]))
    risk = qs(
        work, "backtest", "weigh", "--votes", str(targets["path"]), "--panel", str(panel["path"]),
        "--method", "risk_parity", "--lookback", "40", "--min-periods", "20",
        "--output", "weights_risk_parity.parquet", "--preview", "0",
    )  # fmt: skip
    assert_weights_fit(read(artifact_paths(risk)["weights"]))


def test_backtest_overlay_only_scales_weights_down(work, panel, targets, index_close):
    original = read(targets["path"])
    trend = qs(
        work, "backtest", "overlay", "--weights", str(targets["path"]), "--panel", str(panel["path"]),
        "--index-close", str(index_close), "--index-trend",
        json.dumps({"scale_downtrend": 0.5, "ma_period": 60}), "--output", "overlay_trend.parquet",
        "--preview", "0",
    )  # fmt: skip
    breadth = qs(
        work, "backtest", "overlay", "--weights", str(targets["path"]), "--panel", str(panel["path"]),
        "--market-breadth", json.dumps({"breadth_threshold": 0.3, "scale_below": 0.5, "ma_period": 20}),
        "--output", "overlay_breadth.parquet", "--preview", "0",
    )  # fmt: skip
    for envelope in (trend, breadth):
        scaled = read(artifact_paths(envelope)["weights"])
        assert_weights_fit(scaled)
        assert (scaled.sum(axis=1) <= original.sum(axis=1).reindex(scaled.index) + EPS).all()


def test_backtest_combine_blends_two_real_backtests(work, candidates):
    envelope = qs(
        work, "backtest", "combine", "--returns", str(candidates), "--method", "equal",
        "--output", "blend.parquet",
    )  # fmt: skip
    data = envelope["data"]
    assert abs(sum(data["weights"].values()) - 1.0) < 1e-9 and finite_numbers(data["metrics"])
    assert read(artifact_paths(envelope)["combined"]).shape[0] == data["rows"]


def test_backtest_cost_layer_for_a_real_close(work, single_bars):
    bars = pd.read_parquet(single_bars)
    last = bars.index[-1].strftime("%Y-%m-%d")
    envelope = qs(
        work, "backtest", "cost", "--time", f"{last} 14:50",
        "--sell-price", str(float(bars["close"].iloc[-1])),
        "--buyback-price", str(float(bars["close"].iloc[-2])),
    )  # fmt: skip
    assert finite_numbers(envelope["data"]) and envelope["data"]["cost_bp"] >= 0


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------


def test_analyze_factor_ic_with_tearsheet(work, panel):
    long = qs(
        work, "compute", "factor", "--panel", str(panel["path"]), "--indicator", "roc",
        "-p", "period=10", "--output", "ic_input.parquet",
    )  # fmt: skip
    envelope = qs(
        work, "analyze", "factor-ic", "--panel", str(panel["path"]),
        "--factor", str(artifact_paths(long)["factor"]), "--horizon", "5", "--groups", "4",
        "--out-dir", "factor_ic", "--tearsheet", "factor_ic/tearsheet.png", "--name", "roc10",
        "--namespace", "smoke",
    )  # fmt: skip
    data = envelope["data"]
    assert finite_numbers(data["ic_stats"]) and data["ic_rows"] > 100
    assert finite_numbers(data["group_mean_return"]) and len(data["group_mean_return"]) == 4
    paths = artifact_paths(envelope)
    for name in ("ic_series", "group_return", "turnover"):
        read(paths[name])
    assert_png(paths["tearsheet"])


def test_analyze_factor_correlation_matrices(correlation):
    data = correlation["envelope"]["data"]
    assert data["pairs"] == [["mom", "rev"], ["mom", "rsi"], ["rev", "rsi"]]
    matrix = pd.DataFrame(data["correlation"]["full"])
    overlap = pd.DataFrame(data["top_n_overlap"]["full"])
    assert np.isfinite(matrix.to_numpy(dtype=float)).all() and np.allclose(np.diag(matrix), 1.0)
    assert matrix.abs().max().max() <= 1.0 + EPS
    assert ((overlap >= 0) & (overlap <= 1)).all().all()
    assert data["history_rows"] > 0
    for name in ("correlation_full", "top_n_overlap_full", "correlation_history"):
        read(correlation["paths"][name])


def test_analyze_perf_and_drawdowns_of_a_real_backtest(work, backtest_run):
    result = str(backtest_run["paths"]["result_df"])
    perf = qs(work, "analyze", "perf", "--returns", result)
    assert finite_numbers(perf["data"]["metrics"]) and perf["data"]["rows"] > 100
    drawdowns = qs(work, "analyze", "drawdowns", "--returns", result, "--top-n", "3")
    episodes = drawdowns["data"]["episodes"]
    assert 0 < len(episodes) <= 3 and all(item["maxdd"] >= 0 for item in episodes)


def test_analyze_overfit_diagnostics(work, candidates):
    envelope = qs(
        work, "analyze", "overfit", "--candidates", str(candidates), "--tests", "dsr,pbo",
        "--n-splits", "4",
    )  # fmt: skip
    results = envelope["data"]["results"]
    assert set(results) == {"dsr", "pbo"} and finite_numbers(results["dsr"])
    assert 0.0 <= results["pbo"]["pbo"] <= 1.0


def test_analyze_stationarity_of_a_real_close(work, single_bars):
    envelope = qs(
        work, "analyze", "stationarity", "--series", str(single_bars), "--column", "close",
        "--windows", "60,120",
    )  # fmt: skip
    windows = envelope["data"]["windows"]
    assert set(windows) == {"60", "120"}
    assert all(math.isfinite(item["hurst"]) for item in windows.values())


SPEC = {
    "factor_id": "roc10",
    "formula_kind": "function_ref",
    "function_module": "skills.compute.indicators",
    "function_name": "roc",
    "expression": None,
    "params": {"period": 10},
    "required_fields": ["close"],
    "window": 10,
    "lag": 0,
    "warmup": 10,
    "missing_policy": "keep_nan",
    "output_dtype": "float64",
    "expected_direction": "long_high",
    "content_hash": "a" * 64,
    "formula_fingerprint": "b" * 64,
}
PROTOCOL = {
    "horizon_bars": 5,
    "direction": "long_high",
    "n_groups": 4,
    "tie_rule": "average",
    "rebalance": "daily",
    "commission": 0.0,
    "slippage": 0.0,
    "parameter_neighborhood": {},
    "regimes": [],
    "time_subsamples": [],
    "random_seed": 7,
    "multiple_testing_budget": 5,
    "thresholds": {},
    "symbol_level": "symbol",
    "datetime_level": "eob",
    "timezone": "naive",
    "required_fields": ["close"],
    "min_cross_section": 5,
    "min_ic_samples": 20,
    "bootstrap_samples": 20,
    "bootstrap_block_size": 5,
    "ic_decay_horizons": [1],
    "trade_at": "close",
    "signal_lag": 1,
    "return_mode": "forward",
    "allow_short": True,
    "require_prefix_recompute": False,
    "universe": [],
}


def test_analyze_preflight_and_evaluate_on_a_real_factor(work, panel):
    spec, protocol = work.dir / "spec.json", work.dir / "protocol.json"
    spec.write_text(json.dumps(SPEC))
    protocol.write_text(json.dumps(PROTOCOL))
    files = ["--spec-json", str(spec), "--protocol-json", str(protocol)]
    preflight = qs(work, "analyze", "preflight", "--panel", str(panel["path"]), *files)
    assert preflight["data"]["hard_failed"] is False
    values = qs(
        work, "compute", "factor", "--panel", str(panel["path"]), "--indicator", "roc",
        "-p", "period=10", "--keep-na", "--output", "evaluate_values.parquet",
    )  # fmt: skip
    evaluated = qs(
        work, "analyze", "evaluate", "--panel", str(panel["path"]), *files,
        "--values", str(artifact_paths(values)["factor"]), "--output", "evaluation.json",
    )  # fmt: skip
    data = evaluated["data"]
    assert data["hard_failed"] is False and data["sections"]["predictive"] != "not_run"
    assert finite_numbers(data["metrics"])
    assert json.loads(assert_file(artifact_paths(evaluated)["analyze_result"]).read_text())


# ---------------------------------------------------------------------------
# ml
# ---------------------------------------------------------------------------


def test_ml_folds_split_the_real_calendar(work, panel):
    envelope = qs(
        work, "ml", "folds", "--panel", str(panel["path"]), "--min-train", "200",
        "--retrain-step", "100", "--purge", "5",
    )  # fmt: skip
    folds = envelope["data"]["folds"]
    assert envelope["data"]["dates"] == KEEP_ROWS and len(folds) >= 3
    assert all(item["train_end"] < item["pred_start"] for item in folds)


def test_ml_lasso_track_against_a_real_index(work, panel):
    envelope = qs(
        work, "ml", "lasso-track", "--panel", str(panel["path"]), "--index-symbol", INDEX_SYMBOL,
        "--lookback", "100", "--min-periods", "50", "--output", "lasso_weights.parquet",
        "--preview", "0",
    )  # fmt: skip
    weights = read(artifact_paths(envelope)["weights"])
    assert np.isfinite(weights.to_numpy(dtype=float)).all()
    # The library caps raw coefficients before renormalising, so only the budget is checked.
    assert (weights >= -EPS).all().all()
    assert (weights.sum(axis=1) <= 1.0 + 1e-6).all()


@pytest.fixture(scope="module")
def model_tables(work, panel):
    """Real single-symbol features joined to real forward-return labels, split in time."""
    one = qs(
        work, "store", "read", "--symbols", "SHSE.510300", "--output", "ml_panel.parquet",
        "--preview", "0",
    )  # fmt: skip
    features = qs(
        work, "compute", "features", "--panel", str(artifact_paths(one)["panel"]),
        "--lookback", "3", "--lags", "1", "--output", "ml_features.parquet", "--preview", "0",
    )  # fmt: skip
    labels = qs(
        work, "compute", "labels", "forward-return", "--bars",
        str(work.data_root / "market" / "1d" / "SHSE.510300.parquet"), "--horizon", "5",
        "--output", "ml_labels.parquet",
    )  # fmt: skip
    frame = pd.read_parquet(artifact_paths(features)["features"]).droplevel("symbol")
    labelled = pd.read_parquet(artifact_paths(labels)["labels"])[["forward_return", "state"]]
    joined = frame.join(labelled, how="inner").dropna()
    columns = list(frame.columns[:12])
    cut = int(len(joined) * 0.7)
    paths = {
        name: work.dir / f"ml_{name}.parquet" for name in ("reg_train", "cls_train", "predict")
    }
    joined[columns + ["forward_return"]].iloc[:cut].to_parquet(paths["reg_train"])
    joined[columns + ["state"]].iloc[:cut].to_parquet(paths["cls_train"])
    joined[columns].iloc[cut:].to_parquet(paths["predict"])
    return {"paths": paths, "rows": len(joined) - cut}


def test_ml_pca_predict_on_real_features(work, model_tables):
    paths = model_tables["paths"]
    envelope = qs(
        work, "ml", "pca-predict", "--train", str(paths["reg_train"]),
        "--predict", str(paths["predict"]), "--target-col", "forward_return", "--model", "ols",
        "--n-pca", "5", "--output", "pca_predictions.parquet", "--preview", "0",
    )  # fmt: skip
    predictions = read(artifact_paths(envelope)["predictions"])
    assert len(predictions) == model_tables["rows"]
    assert np.isfinite(predictions["prediction"]).all()
    assert 0 < envelope["data"]["pca_explained_variance_sum"] <= 1.0 + EPS


def test_ml_train_and_predict_through_the_registry(work, model_tables):
    paths = model_tables["paths"]
    plan = qs(
        work, "ml", "train", "--train", str(paths["cls_train"]), "--target", "state",
        "--model-name", "lr", "--namespace", "smoke",
    )  # fmt: skip
    assert plan["data"]["dry_run"] is True
    trained = qs(
        work, "ml", "train", "--train", str(paths["cls_train"]), "--target", "state",
        "--model-name", "lr", "--namespace", "smoke", "--write",
    )  # fmt: skip
    data = trained["data"]
    assert finite_numbers(data["cv_metrics_mean"]) and data["features"]
    registry = Path(data["registry_dir"])
    assert registry.resolve().is_relative_to(work.data_root.resolve())
    assert_file(registry / data["model_id"] / "model.pkl")
    predicted = qs(
        work, "ml", "predict", "--data", str(paths["predict"]), "--namespace", "smoke",
        "--model-id", data["model_id"], "--output", "ml_predictions.parquet", "--preview", "0",
    )  # fmt: skip
    table = read(artifact_paths(predicted)["predictions"])
    assert len(table) == model_tables["rows"] and "prediction_label" in table.columns


@pytest.fixture(scope="module")
def factor_rank(work, panel):
    envelope = qs(
        work, "ml", "factor-rank", "--panel", str(panel["path"]), "--factors",
        json.dumps(
            [
                {"indicator": "roc", "params": {"period": 5}, "name": "roc5"},
                {"indicator": "rsi", "params": {"period": 14}, "name": "rsi"},
            ]
        ),
        "--model", "rf", "--train-mode", "fixed", "--n-folds", "2", "--output", "ml_rank.parquet",
        "--importance-output", "ml_importance.parquet", "--preview", "0",
    )  # fmt: skip
    return {"envelope": envelope, "paths": artifact_paths(envelope)}


def test_ml_factor_rank_writes_unit_interval_ranks(factor_rank):
    data = factor_rank["envelope"]["data"]
    assert data["rows"] > 100 and set(data["columns"]) == set(SYMBOLS)
    assert finite_numbers(data["evaluation"])
    ranks = read(factor_rank["paths"]["rank"])
    assert len(ranks) == data["rows"] and set(ranks.columns) == set(SYMBOLS)
    values = ranks.to_numpy(dtype=float)
    assert np.nanmin(values) >= 0.0 and np.nanmax(values) <= 1.0
    importance = read(factor_rank["paths"]["importance"])
    assert importance["importance"].ge(0).all()


def test_ml_factor_rank_output_can_feed_downstream_commands(work, factor_rank):
    envelope = qs(
        work, "strategy", "top-n", "--scores", str(factor_rank["paths"]["rank"]), "--top-n", "2",
        "--output", "rank_targets.parquet", "--preview", "0",
    )  # fmt: skip
    weights = read(artifact_paths(envelope)["weights"])
    assert (weights.gt(0).sum(axis=1) == 2).all()
    assert_weights_fit(weights)


# ---------------------------------------------------------------------------
# factor-mining
# ---------------------------------------------------------------------------


def test_factor_mining_contract_commands(work, panel):
    types = qs(work, "factor-mining", "types")
    assert {"SplitWindow", "FactorSpec", "ResearchBrief"} <= set(types["data"]["types"])
    schema = qs(work, "factor-mining", "schema", "SplitWindow", "--preview", "0")
    assert {"split_id", "start", "end"} <= set(schema["data"]["json_schema"]["properties"])
    template = qs(
        work, "factor-mining", "template", "SplitWindow", "--output", "split_template.json"
    )
    skeleton = json.loads(assert_file(artifact_paths(template)["template"]).read_text())
    # Fill the skeleton with the real sample dates of the copy.
    dates = pd.read_parquet(panel["path"]).index.get_level_values("eob")
    contract = {
        **skeleton,
        "split_id": "smoke_train",
        "start": str(dates.min().date()),
        "end": str(dates.max().date()),
    }
    filled = work.dir / "split_filled.json"
    filled.write_text(json.dumps(contract))
    validated = qs(
        work, "factor-mining", "validate", "SplitWindow", "--file", str(filled),
        "--output", "split_valid.json",
    )  # fmt: skip
    assert validated["data"]["value"]["split_id"] == "smoke_train"
    assert_file(artifact_paths(validated)["contract"])


def test_factor_mining_check_function_is_causal_on_real_bars(work, panel):
    envelope = qs(
        work, "factor-mining", "check-function", "--panel", str(panel["path"]),
        "--function", "skills.compute.indicators:roc", "-p", "period=10",
        "--required-fields", "close",
    )  # fmt: skip
    assert envelope["data"]["checked_prefixes"] > 0 and envelope["data"]["required_fields"] == [
        "close"
    ]


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def chart_tables(work, surface):
    """Chart inputs derived from real command outputs."""
    summary = read(surface["paths"]["summary"])
    base = summary[(summary["lag"] == 0) & (summary["horizon"] == COMBINE_HORIZON)]
    ranking = base.rename(columns={"factor": "indicator", "icir": "IC_IR"})[["indicator", "IC_IR"]]
    heatmap = summary[summary["lag"] == 0].pivot(
        index="factor", columns="horizon", values="ic_mean"
    )
    heatmap.columns = [f"h{value}" for value in heatmap.columns]
    paths = {"ranking": work.dir / "ranking.parquet", "heatmap": work.dir / "heatmap.parquet"}
    ranking.to_parquet(paths["ranking"])
    heatmap.to_parquet(paths["heatmap"])
    return paths


def test_report_charts_render_valid_pngs(work, backtest_run, surface, combined, chart_tables):
    result = str(backtest_run["paths"]["result_df"])
    summary = str(surface["paths"]["summary"])
    cases = {
        "equity": ["--kind", "equity-curve", "--table", result, "--column", "return"],
        "performance": ["--kind", "backtest-performance", "--table", result],
        "ranking": [
            "--kind", "factor-ranking", "--table", str(chart_tables["ranking"]),
            "--params", json.dumps({"value_col": "IC_IR"}),
        ],
        "heatmap": ["--kind", "ic-heatmap", "--table", str(chart_tables["heatmap"])],
        "horizon": ["--kind", "horizon-ic", "--table", summary, "--params", json.dumps({"factors": list(FACTORS)})],
        "lagged": ["--kind", "lagged-ic", "--table", summary, "--params", json.dumps({"factors": list(FACTORS)})],
        "weights": [
            "--kind", "factor-weight-history", "--table", str(combined["paths"]["factor_weights"]),
            "-p", "method=max_ic",
        ],
    }  # fmt: skip
    for name, args in cases.items():
        envelope = qs(work, "report", "chart", *args, "--output", f"charts/{name}.png")
        assert envelope["data"]["bytes"] > 1000
        assert_png(artifact_paths(envelope)["chart"])


def test_report_bundle_list_and_catalog(work, backtest_run, panel):
    chart = qs(
        work, "report", "chart", "--kind", "equity-curve",
        "--table", str(backtest_run["paths"]["result_df"]), "--column", "return",
        "--output", "bundle_equity.png",
    )  # fmt: skip
    metrics = backtest_run["envelope"]["data"]["metrics"]
    payload = {
        "namespace": "smoke",
        "slug": "etf_top3",
        "title": "ETF top-3 smoke study",
        "question": "Does the smoke chain run end to end on local ETF data?",
        "universe": list(SYMBOLS),
        "frequency": "1d",
        "sample_start": "2024-02-07",
        "sample_end": "2026-08-04",
        "hypothesis": "Momentum top-3 earns a positive return before costs.",
        "method_notes": ["ROC(10) ranks, top 3 equal weight, one bar signal lag."],
        "execution": {"trade_at": "close", "signal_lag": 1, "commission": 0.0002, "slippage_bp": 1},
        "metrics": metrics,
        "metrics_source": "qs backtest run metrics",
        "figures": [
            {
                "name": "equity",
                "caption": "Equity curve",
                "source_path": str(artifact_paths(chart)["chart"]),
            }
        ],
        "tables": [],
        "caveats": ["Smoke data only; not evidence of an edge."],
        "next_steps": ["Run the full study on the complete history."],
        "reproduce_command": "uv run python -m pytest -m smoke",
        "tags": ["smoke"],
    }
    (work.dir / "study.json").write_text(json.dumps(payload))
    bundle = qs(
        work, "report", "bundle", "--input-json", "study.json", "--reports-root", str(work.reports_root),
        "--catalog",
    )  # fmt: skip
    study = Path(bundle["data"]["study_dir"])
    assert study.resolve().is_relative_to(work.reports_root.resolve())
    assert "index.html" in bundle["data"]["files"] and assert_file(study / "index.html")
    assert json.loads((study / "params.json").read_text())["metrics"] == metrics
    listing = qs(work, "report", "list", "--reports-root", str(work.reports_root))
    assert listing["data"]["count"] == 1 and listing["data"]["studies"][0]["slug"] == "etf_top3"
    catalog = qs(work, "report", "catalog", "--reports-root", str(work.reports_root))
    assert assert_file(work.reports_root / "catalog.html")
    assert len(json.loads((work.reports_root / "catalog.json").read_text())) == 1
    assert catalog["ok"]


# ---------------------------------------------------------------------------
# skipped commands and the read-only guarantee
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command", sorted(SKIPPED))
def test_commands_without_a_suitable_local_input_are_skipped(command):
    pytest.skip(f"{command}: {SKIPPED[command]}")


def test_source_data_root_is_untouched(source_root, source_snapshot, work):
    assert work.data_root.resolve() != source_root.resolve()
    assert snapshot(source_root) == source_snapshot
