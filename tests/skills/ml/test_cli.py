"""Tests for the ``qs ml`` command adapters.

``lasso-track``, ``folds``, ``pca-predict``, ``train`` and ``predict`` run for real on small
tables. ``factor-rank`` is mostly tested with a stand-in for ``MLFactorEngine``; two tests run
the real engine.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from skills.cli import main
from skills.cli.io import json_safe
from skills.compute.indicators import discover_indicators
from skills.ml import ml_engine
from skills.ml.lasso_tracker import lasso_track
from skills.ml.ml_engine import MLEngine
from skills.ml.ml_factor import MLFactorEngine
from skills.ml.pca_fold import fit_fold_transform, make_regressor
from skills.ml.walk_forward import expanding_purged_folds
from tests.fixtures.market_data import make_ohlcv, write_symbol_parquet

SYMBOLS = ("S0", "S1", "S2", "S3", "S4")


def run(capsys, *argv):
    capsys.readouterr()  # drop output of earlier direct library calls (some print)
    code = main(["ml", *argv])
    return code, json.loads(capsys.readouterr().out)


def assert_error(code, body, name, status):
    assert code == status, body
    assert body["ok"] is False
    assert body["error"]["code"] == name, body


@pytest.fixture(autouse=True)
def isolated_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", str(tmp_path / "data_root"))
    monkeypatch.setenv("QUANTSPACE_REPORTS_ROOT", str(tmp_path / "reports_root"))


def random_panel(symbols=SYMBOLS, periods=160, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for symbol in symbols:
        prices = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, periods)))
        frames.append(make_ohlcv(prices, symbol=symbol))
    return pd.concat(frames).sort_index()


@pytest.fixture
def panel_file(tmp_path):
    panel = random_panel()
    path = tmp_path / "panel.parquet"
    panel.to_parquet(path)
    return panel, path


def close_returns(panel) -> pd.DataFrame:
    close = panel["close"].unstack("symbol").sort_index()
    return close.pct_change(fill_method=None).iloc[1:]


# ---------------------------------------------------------------------------
# factor-rank (stand-in MLFactorEngine)
# ---------------------------------------------------------------------------


class FakeFactorEngine:
    """Records its construction and returns a deterministic rank table."""

    instances: list[FakeFactorEngine] = []
    importances = True
    categorical_columns = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.oos_start_date = pd.Timestamp("2024-04-01")
        self.feature_importance_df = (
            pd.DataFrame({"feature": ["roc", "rsi"], "importance": [0.7, 0.3]})
            if self.importances
            else None
        )
        FakeFactorEngine.instances.append(self)

    def generate(self):
        close = self.kwargs["data"]["close"].unstack("symbol").sort_index()
        rank = close.rank(axis=1, pct=True)
        if self.categorical_columns:
            # What the real MLFactorEngine returns: symbols as a categorical column index.
            rank.columns = pd.CategoricalIndex(rank.columns, name="symbol")
        return rank

    def get_feature_importance(self):
        return self.feature_importance_df

    def get_eval_summary(self):
        return {
            "out_of_sample": {"ic_mean": np.float64(0.05), "n_dates": 10, "ir": np.nan},
            "cv_metrics_mean": {"R2": 0.1},
        }


class TextMetricsEngine(MLFactorEngine):
    """The real get_eval_summary over holdout metrics that carry a text Model column."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.kwargs = kwargs

    def generate(self):
        self.oos_start_date = None
        self.eval_df = pd.DataFrame(
            {"ic": [0.1, 0.2], "period_type": ["in_sample", "out_of_sample"]}
        )
        self.holdout_metrics_list = [
            pd.DataFrame({"Model": ["Extreme Gradient Boosting"], "MAE": [0.1]})
        ]
        close = self.kwargs["data"]["close"].unstack("symbol").sort_index()
        return close.rank(axis=1, pct=True)


@pytest.fixture
def fake_engine(monkeypatch):
    FakeFactorEngine.instances = []
    FakeFactorEngine.importances = True
    FakeFactorEngine.categorical_columns = False
    monkeypatch.setattr("skills.ml.ml_factor.MLFactorEngine", FakeFactorEngine)
    return FakeFactorEngine


FACTORS = json.dumps(
    [
        {"indicator": "roc", "params": {"period": 3}, "name": "roc3"},
        {"function": "skills.compute.indicators:rsi"},
    ]
)


def rank_argv(panel_path, output, *extra):
    return [
        "factor-rank",
        "--panel",
        str(panel_path),
        "--factors",
        FACTORS,
        "--output",
        str(output),
        *extra,
    ]


def test_factor_rank_builds_the_engine_from_the_inputs_and_writes_the_rank(
    capsys, tmp_path, panel_file, fake_engine
):
    panel, panel_path = panel_file
    output = tmp_path / "rank.parquet"
    importance = tmp_path / "importance.csv"
    code, body = run(
        capsys,
        *rank_argv(
            panel_path, output, "--importance-output", str(importance), "--model", "rf",
            "--target-forward", "3", "--train-mode", "fixed", "--train-ratio", "0.6",
            "--train-window", "50", "--retrain-freq", "10", "--n-folds", "3",
            "--model-params", '{"n_estimators": 50}',
        ),
    )  # fmt: skip
    assert code == 0, body
    (engine,) = fake_engine.instances
    kwargs = engine.kwargs
    pd.testing.assert_frame_equal(kwargs["data"], panel)
    assert {key: kwargs[key] for key in kwargs if key not in {"data", "factor_configs"}} == {
        "model_type": "rf",
        "target_forward": 3,
        "train_mode": "fixed",
        "train_ratio": 0.6,
        "train_window": 50,
        "retrain_freq": 10,
        "n_folds": 3,
        "model_params": {"n_estimators": 50},
    }
    first, second = kwargs["factor_configs"]
    assert first == {"func": discover_indicators()["roc"], "kwargs": {"period": 3}, "name": "roc3"}
    from skills.compute.indicators import rsi

    assert second == {"func": rsi, "kwargs": {}}
    rank = engine.generate()
    pd.testing.assert_frame_equal(pd.read_parquet(output), rank)
    pd.testing.assert_frame_equal(pd.read_csv(importance), engine.feature_importance_df)
    data = body["data"]
    assert data["rows"] == len(rank) and data["columns"] == list(rank.columns)
    assert data["oos_start_date"] == "2024-04-01 00:00:00"
    assert data["evaluation"] == json_safe(engine.get_eval_summary())
    assert data["evaluation"]["out_of_sample"]["ir"] is None
    assert [item["name"] for item in body["artifacts"]] == ["rank", "importance"]
    assert body["warnings"] == []


def test_factor_rank_with_categorical_symbol_labels_reads_back_and_feeds_top_n(
    capsys, tmp_path, panel_file, fake_engine
):
    from skills.cli.io import read_frame
    from skills.strategy.cross_sectional import top_n_weights

    fake_engine.categorical_columns = True
    panel, panel_path = panel_file
    output = tmp_path / "rank.parquet"
    code, body = run(capsys, *rank_argv(panel_path, output))
    assert code == 0, body
    rank = fake_engine.instances[0].generate()
    assert isinstance(rank.columns, pd.CategoricalIndex)
    # The engine's own frame is untouched; the written file has plain labels.
    plain = rank.set_axis(pd.Index(list(rank.columns), name="symbol"), axis=1)
    pd.testing.assert_frame_equal(pd.read_parquet(output), plain)
    assert not isinstance(read_frame(output).columns, pd.CategoricalIndex)
    assert body["data"]["columns"] == list(plain.columns)

    capsys.readouterr()
    targets = tmp_path / "targets.parquet"
    code = main(
        ["strategy", "top-n", "--scores", str(output), "--top-n", "2", "--output", str(targets)]
    )
    assert code == 0, json.loads(capsys.readouterr().out)
    pd.testing.assert_frame_equal(
        pd.read_parquet(targets), top_n_weights(plain, top_n=2), check_freq=False
    )


def test_factor_rank_defaults_and_store_panel_source(capsys, tmp_path, fake_engine):
    root = tmp_path / "root"
    panel = random_panel(("S0", "S1", "S2"))
    for symbol in ("S0", "S1", "S2"):
        write_symbol_parquet(root, symbol, panel.xs(symbol, level="symbol"))
    output = tmp_path / "rank.parquet"
    code, body = run(
        capsys, "factor-rank", "--symbols", "S0,S1,S2", "--data-root", str(root),
        "--factors", '[{"indicator": "roc"}]', "--output", str(output),
    )  # fmt: skip
    assert code == 0, body
    kwargs = fake_engine.instances[0].kwargs
    assert kwargs["model_type"] == "xgboost" and kwargs["train_mode"] == "rolling"
    assert (kwargs["target_forward"], kwargs["train_window"], kwargs["retrain_freq"]) == (
        1,
        120,
        20,
    )
    assert (kwargs["train_ratio"], kwargs["n_folds"], kwargs["model_params"]) == (0.7, 5, {})
    assert list(kwargs["data"].index.get_level_values("symbol").unique()) == ["S0", "S1", "S2"]


def test_factor_rank_evaluation_averages_holdout_metrics_past_the_text_model_column(
    capsys, tmp_path, panel_file, monkeypatch
):
    _, panel_path = panel_file
    monkeypatch.setattr("skills.ml.ml_factor.MLFactorEngine", TextMetricsEngine)
    output = tmp_path / "rank.parquet"
    code, body = run(capsys, *rank_argv(panel_path, output))
    assert code == 0 and body["ok"], body
    assert body["data"]["evaluation"]["holdout_metrics_mean"] == {"MAE": 0.1}
    assert body["warnings"] == []
    assert output.exists() and len(pd.read_parquet(output)) == body["data"]["rows"]


def test_factor_rank_importance_output_without_importances_writes_nothing(
    capsys, tmp_path, panel_file, fake_engine
):
    _, panel_path = panel_file
    fake_engine.importances = False
    output, importance = tmp_path / "rank.parquet", tmp_path / "importance.parquet"
    code, body = run(capsys, *rank_argv(panel_path, output, "--importance-output", str(importance)))
    assert_error(code, body, "INVALID_INPUT", 2)
    assert "importance" in body["error"]["message"]
    assert not output.exists() and not importance.exists()
    # Without --importance-output the same model is fine.
    code, body = run(capsys, *rank_argv(panel_path, output))
    assert code == 0, body
    assert output.exists()


def test_factor_rank_output_conflicts_leave_files_untouched(
    capsys, tmp_path, panel_file, fake_engine
):
    _, panel_path = panel_file
    output, importance = tmp_path / "rank.parquet", tmp_path / "importance.parquet"
    output.write_bytes(b"keep me")
    code, body = run(capsys, *rank_argv(panel_path, output))
    assert_error(code, body, "CONFLICT", 2)
    assert output.read_bytes() == b"keep me" and fake_engine.instances == []
    output.unlink()
    importance.write_bytes(b"keep me too")
    code, body = run(capsys, *rank_argv(panel_path, output, "--importance-output", str(importance)))
    assert_error(code, body, "CONFLICT", 2)
    assert importance.read_bytes() == b"keep me too" and not output.exists()
    code, body = run(
        capsys,
        *rank_argv(panel_path, output, "--importance-output", str(importance), "--overwrite"),
    )
    assert code == 0, body
    assert importance.read_bytes() != b"keep me too" and output.exists()


@pytest.mark.parametrize(
    "extra",
    [
        ["--factors", "[]"],
        ["--factors", '[{"indicator": "roc", "function": "skills.compute.indicators:rsi"}]'],
        ["--factors", '[{"params": {}}]'],
        ["--factors", '[{"indicator": "no_such_indicator"}]'],
        ["--train-ratio", "1.5"],
        ["--n-folds", "1"],
        ["--target-forward", "0"],
        ["--train-mode", "sliding"],
        ["--model", "lightgbm"],
        ["--model", "gbc"],  # a classification-only id
    ],
)
def test_factor_rank_rejects_invalid_inputs(capsys, tmp_path, panel_file, fake_engine, extra):
    _, panel_path = panel_file
    output = tmp_path / "rank.parquet"
    argv = [
        "factor-rank",
        "--panel",
        str(panel_path),
        "--factors",
        FACTORS,
        "--output",
        str(output),
    ]
    if extra[0] == "--factors":
        argv = ["factor-rank", "--panel", str(panel_path), "--output", str(output), *extra]
    else:
        argv += extra
    code, body = run(capsys, *argv)
    assert body["ok"] is False and code in (2, 3), body
    assert fake_engine.instances == [] and not output.exists()


def test_factor_rank_with_the_real_engine_writes_unit_interval_ranks(capsys, tmp_path, panel_file):
    _, panel_path = panel_file
    output, importance = tmp_path / "rank.parquet", tmp_path / "importance.parquet"
    code, body = run(
        capsys,
        *rank_argv(
            panel_path, output, "--model", "rf", "--train-mode", "fixed", "--n-folds", "2",
            "--model-params", '{"n_estimators": 10, "n_jobs": 1}',
            "--importance-output", str(importance),
        ),
    )  # fmt: skip
    assert code == 0, body
    ranks = pd.read_parquet(output)
    assert set(ranks.columns) == set(SYMBOLS) and len(ranks) == body["data"]["rows"]
    values = ranks.to_numpy(dtype=float)
    assert np.nanmin(values) > 0 and np.nanmax(values) <= 1
    evaluation = body["data"]["evaluation"]
    assert set(evaluation["cv_metrics_mean"]) == {"MAE", "MSE", "RMSE", "R2", "RMSLE", "MAPE"}
    assert set(evaluation["holdout_metrics_mean"]) == set(evaluation["cv_metrics_mean"])
    assert sorted(pd.read_parquet(importance)["feature"]) == ["roc3", "rsi"]


def test_factor_rank_real_engine_rejects_unknown_model_params(capsys, tmp_path, panel_file):
    _, panel_path = panel_file
    output = tmp_path / "rank.parquet"
    code, body = run(capsys, *rank_argv(panel_path, output, "--model-params", '{"depth": 3}'))
    assert_error(code, body, "INVALID_INPUT", 2)
    assert "depth" in body["error"]["message"] and not output.exists()


def test_factor_rank_unknown_function_reference_is_invalid_input(
    capsys, tmp_path, panel_file, fake_engine
):
    _, panel_path = panel_file
    code, body = run(
        capsys, "factor-rank", "--panel", str(panel_path), "--output", str(tmp_path / "rank.parquet"),
        "--factors", '[{"function": "skills.compute.indicators:no_such_function"}]',
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)


def test_factor_rank_panel_source_and_output_errors(capsys, tmp_path, panel_file, fake_engine):
    _, panel_path = panel_file
    output = tmp_path / "rank.parquet"
    code, body = run(capsys, "factor-rank", "--factors", FACTORS, "--output", str(output))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "factor-rank", "--panel", str(panel_path), "--symbols", "S0",
        "--factors", FACTORS, "--output", str(output),
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *rank_argv(tmp_path / "missing.parquet", output))
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, *rank_argv(panel_path, output, "--importance-output", str(output)))
    assert_error(code, body, "INVALID_INPUT", 2)
    managed = tmp_path / "data_root" / "market" / "1d" / "rank.parquet"
    code, body = run(
        capsys, *rank_argv(panel_path, managed, "--data-root", str(tmp_path / "data_root"))
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    assert fake_engine.instances == [] and not output.exists() and not managed.exists()


# ---------------------------------------------------------------------------
# lasso-track
# ---------------------------------------------------------------------------

LASSO = ["--lookback", "40", "--min-periods", "20", "--alpha", "1e-5", "--max-weight", "0.5"]


def lasso_inputs(tmp_path, periods=160):
    panel = random_panel(("T0", "T1", "T2", "T3", "IDX"), periods=periods, seed=9)
    returns = close_returns(panel)
    candidates, index = returns[["T0", "T1", "T2", "T3"]], returns["IDX"]
    return panel, candidates, index


@pytest.mark.parametrize("rebalance", ["D", "W", "M"])
def test_lasso_track_with_files_equals_lasso_track(capsys, tmp_path, rebalance):
    _, candidates, index = lasso_inputs(tmp_path)
    returns_path, index_path = tmp_path / "returns.parquet", tmp_path / "index.parquet"
    candidates.to_parquet(returns_path)
    index.to_frame("return").to_parquet(index_path)
    expected = lasso_track(
        candidates, index, lookback=40, alpha=1e-5, min_periods=20, rebalance_freq=rebalance,
        max_weight=0.5,
    )  # fmt: skip
    output = tmp_path / "weights.parquet"
    code, body = run(
        capsys, "lasso-track", "--returns", str(returns_path), "--index-returns", str(index_path),
        "--rebalance-freq", rebalance, "--output", str(output), *LASSO,
    )  # fmt: skip
    assert code == 0, body
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)
    data = body["data"]
    assert data["rows"] == len(expected) and data["columns"] == list(expected.columns)
    assert data["start"] == str(expected.index.min()) and data["end"] == str(expected.index.max())
    assert len(data["preview"]) == min(5, len(expected))
    assert body["artifacts"][0]["name"] == "weights"


def test_lasso_track_from_the_panel_and_a_stored_index_symbol(capsys, tmp_path):
    panel, candidates, index = lasso_inputs(tmp_path)
    panel_path = tmp_path / "panel.parquet"
    panel[panel.index.get_level_values("symbol") != "IDX"].to_parquet(panel_path)
    root = tmp_path / "root"
    write_symbol_parquet(root, "IDX", panel.xs("IDX", level="symbol"))
    expected = lasso_track(
        candidates, index, lookback=40, alpha=1e-5, min_periods=20, rebalance_freq="W",
        max_weight=0.5,
    )  # fmt: skip
    output = tmp_path / "weights.csv"
    code, body = run(
        capsys, "lasso-track", "--panel", str(panel_path), "--index-symbol", "IDX",
        "--data-root", str(root), "--rebalance-freq", "W", "--output", str(output), *LASSO,
    )  # fmt: skip
    assert code == 0, body
    written = pd.read_csv(output, index_col=0, parse_dates=True)
    pd.testing.assert_frame_equal(written, expected, check_freq=False, check_names=False, atol=1e-9)
    assert body["data"]["rows"] == len(expected)


def test_lasso_track_candidates_from_the_store(capsys, tmp_path):
    panel, candidates, index = lasso_inputs(tmp_path)
    root = tmp_path / "root"
    for symbol in ("T0", "T1", "T2", "T3", "IDX"):
        write_symbol_parquet(root, symbol, panel.xs(symbol, level="symbol"))
    expected = lasso_track(
        candidates, index, lookback=40, alpha=1e-5, min_periods=20, rebalance_freq="M",
        max_weight=0.5,
    )  # fmt: skip
    output = tmp_path / "weights.parquet"
    code, body = run(
        capsys, "lasso-track", "--symbols", "T0,T1,T2,T3", "--index-symbol", "IDX",
        "--data-root", str(root), "--output", str(output), *LASSO,
    )  # fmt: skip
    assert code == 0, body
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)


def test_lasso_track_input_errors_and_conflicts(capsys, tmp_path):
    _, candidates, index = lasso_inputs(tmp_path)
    returns_path, index_path = tmp_path / "returns.parquet", tmp_path / "index.parquet"
    candidates.to_parquet(returns_path)
    index.to_frame("return").to_parquet(index_path)
    output = tmp_path / "weights.parquet"
    base = ["lasso-track", "--output", str(output), *LASSO]
    # Exactly one index source.
    code, body = run(capsys, *base, "--returns", str(returns_path))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, *base, "--returns", str(returns_path), "--index-returns", str(index_path),
        "--index-symbol", "IDX",
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    # Candidates need --returns or a panel source.
    code, body = run(capsys, *base, "--index-returns", str(index_path))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, *base, "--returns", str(returns_path), "--index-returns", str(index_path),
        "--index-column", "nope",
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, *base, "--returns", str(tmp_path / "missing.parquet"),
        "--index-returns", str(index_path),
    )  # fmt: skip
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(
        capsys, *base, "--returns", str(returns_path), "--index-returns", str(index_path),
        "--rebalance-freq", "Y",
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, *base, "--returns", str(returns_path), "--index-returns", str(index_path),
        "--max-weight", "1.5",
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    assert not output.exists()
    output.write_bytes(b"keep me")
    code, body = run(
        capsys, *base, "--returns", str(returns_path), "--index-returns", str(index_path)
    )
    assert_error(code, body, "CONFLICT", 2)
    assert output.read_bytes() == b"keep me"
    code, body = run(
        capsys, *base, "--returns", str(returns_path), "--index-returns", str(index_path),
        "--overwrite",
    )  # fmt: skip
    assert code == 0, body
    assert output.read_bytes() != b"keep me"


# ---------------------------------------------------------------------------
# folds
# ---------------------------------------------------------------------------


def expected_folds(dates, **kwargs):
    folds = expanding_purged_folds(dates, **kwargs)
    return json_safe(
        [
            {
                "fold_id": fold.fold_id,
                "retrain_idx": fold.retrain_idx,
                "purge": fold.purge,
                "train_start": fold.train_dates[0],
                "train_end": fold.train_dates[-1],
                "train_dates": len(fold.train_dates),
                "pred_start": fold.pred_dates[0],
                "pred_end": fold.pred_dates[-1],
                "pred_dates": len(fold.pred_dates),
            }
            for fold in folds
        ]
    )


def test_folds_from_a_table_equal_expanding_purged_folds(capsys, tmp_path):
    dates = pd.bdate_range("2023-01-02", periods=300, name="eob")
    table = tmp_path / "table.parquet"
    pd.DataFrame({"x": np.arange(300.0)}, index=dates).to_parquet(table)
    code, body = run(
        capsys, "folds", "--table", str(table), "--min-train", "100", "--retrain-step", "60",
        "--purge", "5", "--preview", "100",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["dates"] == 300
    assert body["data"]["folds"] == expected_folds(dates, min_train=100, retrain_step=60, purge=5)
    assert len(body["data"]["folds"]) == 4


def test_folds_from_a_long_table_and_a_panel_use_the_unique_sorted_dates(capsys, tmp_path):
    panel = random_panel(periods=200)
    dates = panel.index.get_level_values("eob").unique().sort_values()
    path = tmp_path / "panel.parquet"
    panel.to_parquet(path)
    expected = expected_folds(dates, min_train=80, retrain_step=50, purge=10)
    for source in (["--panel", str(path)], ["--table", str(path)]):
        code, body = run(
            capsys, "folds", *source, "--min-train", "80", "--retrain-step", "50", "--purge", "10"
        )
        assert code == 0, body
        assert body["data"]["dates"] == len(dates)
        assert body["data"]["folds"] == expected
    root = tmp_path / "root"
    for symbol in SYMBOLS:
        write_symbol_parquet(root, symbol, panel.xs(symbol, level="symbol"))
    code, body = run(
        capsys, "folds", "--symbols", ",".join(SYMBOLS), "--data-root", str(root),
        "--min-train", "80", "--retrain-step", "50", "--purge", "10",
    )  # fmt: skip
    assert code == 0 and body["data"]["folds"] == expected


def test_folds_defaults_and_input_errors(capsys, tmp_path):
    dates = pd.bdate_range("2020-01-01", periods=600, name="eob")
    table = tmp_path / "table.parquet"
    pd.DataFrame({"x": np.arange(600.0)}, index=dates).to_parquet(table)
    code, body = run(capsys, "folds", "--table", str(table))
    assert code == 0, body
    assert body["data"]["folds"] == expected_folds(dates)
    short = tmp_path / "short.parquet"
    pd.DataFrame({"x": np.arange(10.0)}, index=dates[:10]).to_parquet(short)
    code, body = run(capsys, "folds", "--table", str(short))
    assert code == 0 and body["data"] == {"dates": 10, "folds": []}
    code, body = run(capsys, "folds")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "folds", "--table", str(tmp_path / "missing.parquet"))
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, "folds", "--table", str(table), "--min-train", "0")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "folds", "--table", str(table), "--purge", "-1")
    assert_error(code, body, "INVALID_INPUT", 2)


# ---------------------------------------------------------------------------
# pca-predict
# ---------------------------------------------------------------------------


def pca_tables(tmp_path, rows=80, features=6, seed=4):
    rng = np.random.default_rng(seed)
    names = [f"f{i}" for i in range(features)]
    x = rng.normal(size=(rows, features))
    target = x @ rng.normal(size=features) + rng.normal(0, 0.1, rows)
    train = pd.DataFrame(x, columns=names)
    train["label"] = target
    fresh = pd.DataFrame(rng.normal(size=(20, features)), columns=names)
    train.to_parquet(tmp_path / "train.parquet")
    fresh.to_parquet(tmp_path / "predict.parquet")
    return train, fresh, names


@pytest.mark.parametrize("model", ["ols", "lasso", "rf", "xgboost"])
def test_pca_predict_equals_fit_fold_transform_and_the_regressor(capsys, tmp_path, model):
    train, fresh, names = pca_tables(tmp_path)
    transform = fit_fold_transform(
        train[names].to_numpy(dtype=np.float64),
        fresh[names].to_numpy(dtype=np.float64),
        n_pca=4,
        random_state=7,
    )
    regressor = make_regressor(model, random_state=7, rf_n_jobs=1)
    regressor.fit(transform.train_X, train["label"].to_numpy(dtype=np.float64))
    expected = pd.DataFrame({"prediction": regressor.predict(transform.pred_X)}, index=fresh.index)
    output = tmp_path / "predictions.parquet"
    code, body = run(
        capsys, "pca-predict", "--train", str(tmp_path / "train.parquet"),
        "--predict", str(tmp_path / "predict.parquet"), "--target-col", "label",
        "--model", model, "--n-pca", "4", "--random-state", "7", "--rf-n-jobs", "1",
        "--output", str(output),
    )  # fmt: skip
    assert code == 0, body
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)
    assert body["data"] == {
        "rows": 20,
        "features": 6,
        "components": 4,
        "pca_explained_variance_sum": pytest.approx(transform.pca_explained_variance_sum),
    }


def test_pca_predict_feature_columns_and_defaults(capsys, tmp_path):
    train, fresh, names = pca_tables(tmp_path)
    chosen = ["f3", "f1", "f0"]
    transform = fit_fold_transform(
        train[chosen].to_numpy(dtype=np.float64), fresh[chosen].to_numpy(dtype=np.float64)
    )
    regressor = make_regressor("ols")
    regressor.fit(transform.train_X, train["label"].to_numpy(dtype=np.float64))
    expected = pd.DataFrame({"prediction": regressor.predict(transform.pred_X)}, index=fresh.index)
    output = tmp_path / "predictions.csv"
    code, body = run(
        capsys, "pca-predict", "--train", str(tmp_path / "train.parquet"),
        "--predict", str(tmp_path / "predict.parquet"), "--target-col", "label",
        "--model", "ols", "--feature-cols", "f3,f1,f0", "--output", str(output),
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["features"] == 3 and body["data"]["components"] == 3
    # A RangeIndex is not written to CSV.
    written = pd.read_csv(output)
    pd.testing.assert_frame_equal(written, expected, rtol=1e-9)


def test_pca_predict_input_errors_and_conflicts(capsys, tmp_path):
    train, fresh, names = pca_tables(tmp_path)
    base = [
        "pca-predict", "--train", str(tmp_path / "train.parquet"),
        "--predict", str(tmp_path / "predict.parquet"), "--target-col", "label", "--model", "ols",
    ]  # fmt: skip
    output = tmp_path / "predictions.parquet"
    code, body = run(
        capsys, *base[:-4], "--target-col", "missing", "--model", "ols", "--output", str(output)
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--feature-cols", "f0,nope", "--output", str(output))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--feature-cols", "f0,f0", "--output", str(output))
    assert_error(code, body, "INVALID_INPUT", 2)
    fresh.drop(columns=["f5"]).to_parquet(tmp_path / "predict_short.parquet")
    code, body = run(
        capsys, *base[:4], "--predict", str(tmp_path / "predict_short.parquet"), *base[6:],
        "--output", str(output),
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, *base[:2], str(tmp_path / "missing.parquet"), *base[3:], "--output", str(output)
    )
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, *base[:-1], "svm", "--output", str(output))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--n-pca", "0", "--output", str(output))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base)  # output is required
    assert_error(code, body, "INVALID_INPUT", 2)
    assert not output.exists()
    output.write_bytes(b"keep me")
    code, body = run(capsys, *base, "--output", str(output))
    assert_error(code, body, "CONFLICT", 2)
    assert output.read_bytes() == b"keep me"
    code, body = run(capsys, *base, "--output", str(output), "--overwrite")
    assert code == 0, body


# ---------------------------------------------------------------------------
# train and predict (real MLEngine on small tables)
# ---------------------------------------------------------------------------


def training_table(tmp_path, rows=40, labels=(0, 1)):
    rng = np.random.default_rng(8)
    frame = pd.DataFrame({"feature_a": rng.normal(size=rows), "feature_b": rng.normal(size=rows)})
    frame["label"] = np.where(frame["feature_a"] > 0, labels[1], labels[0])
    path = tmp_path / "train.parquet"
    frame.to_parquet(path)
    return frame, path


def test_train_without_write_is_a_plan_and_writes_nothing(capsys, tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a plan must not train")

    monkeypatch.setattr(MLEngine, "setup_and_train", refuse)
    frame, path = training_table(tmp_path)
    root = tmp_path / "root"
    code, body = run(
        capsys, "train", "--train", str(path), "--namespace", "demo", "--data-root", str(root)
    )
    assert code == 0, body
    assert body["data"] == {
        "dry_run": True,
        "namespace": "demo",
        "registry_dir": str(root / "models" / "demo"),
        "model_id": None,
        "rows": len(frame),
        "features": ["feature_a", "feature_b"],
        "cv_metrics_mean": {},
    }
    assert not root.exists() and body["artifacts"] == []


def test_train_write_saves_the_model_with_metadata(capsys, tmp_path):
    frame, path = training_table(tmp_path)
    root = tmp_path / "root"
    direct = MLEngine(task="classification", model_name="xgboost", normalize="zscore")
    _, cv_metrics = direct.setup_and_train(frame, target="label")
    code, body = run(
        capsys, "train", "--train", str(path), "--namespace", "demo", "--data-root", str(root),
        "--write",
    )  # fmt: skip
    assert code == 0, body
    data = body["data"]
    assert data["dry_run"] is False
    assert list(cv_metrics.index) == [str(i) for i in range(10)] + ["Mean", "Std"]
    assert data["cv_metrics_mean"] == json_safe(cv_metrics.loc["Mean"].to_dict())
    assert list(data["cv_metrics_mean"]) == [
        "Accuracy",
        "AUC",
        "Recall",
        "Prec.",
        "F1",
        "Kappa",
        "MCC",
    ]
    model_dir = root / "models" / "demo" / data["model_id"]
    assert data["model_id"].startswith("classification_xgboost_")
    meta = json.loads((model_dir / "metadata.json").read_text())
    assert meta["features"] == ["feature_a", "feature_b"]
    assert meta["metrics"] == data["cv_metrics_mean"] and meta["target"] == "label"
    assert meta["task"] == "classification" and meta["normalize"] == "zscore"
    assert meta["format"] == ml_engine.MODEL_FORMAT and "pycaret_version" not in meta
    assert (meta["session_id"], meta["folds"], meta["model_params"]) == (369, 10, {})
    assert meta["scikit_learn_version"] and meta["xgboost_version"]
    assert (model_dir / "model.pkl").exists()
    assert body["artifacts"] == [
        {
            "name": "model",
            "path": str(model_dir),
            "format": "directory",
            "rows": None,
            "columns": [],
        }
    ]
    assert [item["model_id"] for item in MLEngine.list_models("demo", data_root=str(root))] == [
        data["model_id"]
    ]


def test_train_options_reach_the_engine(capsys, tmp_path):
    frame, path = training_table(tmp_path)
    root = tmp_path / "root"
    params = {"fit_intercept": False}
    code, body = run(
        capsys, "train", "--train", str(path), "--namespace", "demo", "--write",
        "--data-root", str(root), "--task", "regression", "--model-name", "lr",
        "--normalize", "minmax", "--pca-components", "2", "--session-id", "5", "--n-jobs", "2",
        "--folds", "3", "--model-params", json.dumps(params),
    )  # fmt: skip
    assert code == 0, body
    data = body["data"]
    assert data["model_id"].startswith("regression_lr_")
    direct = MLEngine(task="regression", model_name="lr", normalize="minmax")
    _, cv_metrics = direct.setup_and_train(
        frame, target="label", pca_components=2, session_id=5, n_jobs=2, folds=3,
        model_params=params,
    )  # fmt: skip
    assert len(cv_metrics) == 3 + 2
    assert data["cv_metrics_mean"] == json_safe(cv_metrics.loc["Mean"].to_dict())
    loaded = MLEngine(task="regression", model_name="lr")
    model = loaded.load_from_registry("demo", data["model_id"], data_root=str(root))
    steps = dict(model.pipeline.steps)
    assert list(steps) == ["imputer", "scaler", "pca", "model"]
    assert type(steps["scaler"]).__name__ == "MinMaxScaler" and steps["pca"].n_components == 2
    assert steps["model"].get_params()["fit_intercept"] is False
    assert steps["model"].get_params()["n_jobs"] == 2
    meta = MLEngine.list_models("demo", data_root=str(root))[0]
    assert (meta["normalize"], meta["pca_components"], meta["session_id"]) == ("minmax", 2, 5)
    assert (meta["folds"], meta["model_params"]) == (3, params)


@pytest.mark.parametrize(
    "extra",
    [
        ["--target", "missing"],
        ["--pca-components", "0"],
        ["--task", "ranking"],
        ["--model-name", "lightgbm"],
        ["--model-name", "lasso"],  # a regression-only id with the default classification task
        ["--normalize", "zscored"],
        ["--folds", "1"],
        ["--model-params", '{"no_such_param": 1}'],
    ],
)
def test_train_input_errors_do_not_train(capsys, tmp_path, extra):
    _, path = training_table(tmp_path)
    root = tmp_path / "root"
    base = ["train", "--train", str(path), "--data-root", str(root), "--namespace", "demo"]
    for write in ([], ["--write"]):
        code, body = run(capsys, *base, *write, *extra)
        assert_error(code, body, "INVALID_INPUT", 2)
    assert not root.exists()


def test_train_namespace_text_features_and_missing_table_errors(capsys, tmp_path):
    frame, path = training_table(tmp_path)
    root = tmp_path / "root"
    base = ["train", "--train", str(path), "--data-root", str(root), "--write"]
    for namespace in ("a/b", "..", ""):
        code, body = run(capsys, *base, "--namespace", namespace)
        assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base)  # namespace is required
    assert_error(code, body, "INVALID_INPUT", 2)
    text = tmp_path / "text.parquet"
    frame.assign(sector="bank").to_parquet(text)
    code, body = run(capsys, "train", "--train", str(text), "--namespace", "demo")
    assert_error(code, body, "INVALID_INPUT", 2)
    assert "sector" in body["error"]["message"]
    code, body = run(
        capsys, "train", "--train", str(tmp_path / "missing.parquet"), "--namespace", "demo"
    )
    assert_error(code, body, "NOT_FOUND", 3)
    assert not root.exists()


@pytest.mark.parametrize(
    ("task", "model", "labels", "columns"),
    [
        ("classification", "xgboost", (-1, 1), ["prediction_label", "prediction_score"]),
        ("classification", "ridge", (0, 1), ["prediction_label"]),  # no probabilities
        ("regression", "rf", (0, 1), ["prediction_label"]),
    ],
)
def test_predict_equals_the_registry_models_prediction(
    capsys, tmp_path, task, model, labels, columns
):
    frame, path = training_table(tmp_path, labels=labels)
    root = tmp_path / "root"
    code, body = run(
        capsys, "train", "--train", str(path), "--namespace", "demo", "--write",
        "--data-root", str(root), "--task", task, "--model-name", model,
    )  # fmt: skip
    assert code == 0, body
    model_id = body["data"]["model_id"]
    rows = frame.drop(columns=["label"]).head(7)
    data_path = tmp_path / "rows.parquet"
    rows.to_parquet(data_path)
    direct = MLEngine(task=task, model_name=model)
    direct.load_from_registry("demo", model_id, data_root=str(root))
    expected = direct.predict(rows)
    output = tmp_path / "predictions.parquet"
    code, body = run(
        capsys, "predict", "--data", str(data_path), "--namespace", "demo",
        "--model-id", model_id, "--data-root", str(root), "--output", str(output),
    )  # fmt: skip
    assert code == 0, body
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)
    assert body["data"] == {"rows": 7, "task": task, "columns": columns}
    assert body["artifacts"][0]["name"] == "predictions"
    if task == "classification":
        assert set(expected["prediction_label"]) <= set(labels)
    # Conflict leaves the existing predictions alone.
    output.write_bytes(b"keep me")
    code, body = run(
        capsys, "predict", "--data", str(data_path), "--namespace", "demo",
        "--model-id", model_id, "--data-root", str(root), "--output", str(output),
    )  # fmt: skip
    assert_error(code, body, "CONFLICT", 2)
    assert output.read_bytes() == b"keep me"


def test_predict_errors(capsys, tmp_path):
    frame, path = training_table(tmp_path)
    root = tmp_path / "root"
    output = tmp_path / "predictions.parquet"
    base = ["predict", "--data", str(path), "--data-root", str(root), "--output", str(output)]
    code, body = run(capsys, *base, "--namespace", "demo", "--model-id", "classification_xgboost_0")
    assert_error(code, body, "NOT_FOUND", 3)
    assert "Model not found" in body["error"]["message"]
    for namespace in ("a/b", ".."):
        code, body = run(capsys, *base, "--namespace", namespace, "--model-id", "x")
        assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--namespace", "demo")  # model-id is required
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "train", "--train", str(path), "--namespace", "demo", "--write",
        "--data-root", str(root),
    )  # fmt: skip
    model_id = body["data"]["model_id"]
    code, body = run(
        capsys, "predict", "--data", str(tmp_path / "missing.parquet"), "--namespace", "demo",
        "--model-id", model_id, "--data-root", str(root), "--output", str(output),
    )  # fmt: skip
    assert_error(code, body, "NOT_FOUND", 3)
    rows = tmp_path / "rows.parquet"
    frame[["feature_a"]].to_parquet(rows)  # feature_b is missing
    code, body = run(
        capsys, "predict", "--data", str(rows), "--namespace", "demo",
        "--model-id", model_id, "--data-root", str(root), "--output", str(output),
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    assert "feature_b" in body["error"]["message"]
    assert not output.exists()


def test_predict_refuses_a_pycaret_model_and_asks_for_retraining(capsys, tmp_path):
    frame, path = training_table(tmp_path)
    root = tmp_path / "root"
    model_dir = root / "models" / "demo" / "classification_xgboost_20250101_000000"
    model_dir.mkdir(parents=True)
    (model_dir / "model.pkl").write_bytes(b"a PyCaret pipeline")
    meta = {
        "model_id": model_dir.name,
        "namespace": "demo",
        "task": "classification",
        "model_name": "catboost",
        "normalize": "zscore",
        "created_at": "2025-01-01T00:00:00",
        "pycaret_version": "3.3.2",
    }
    (model_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    output = tmp_path / "predictions.parquet"
    code, body = run(
        capsys, "predict", "--data", str(path), "--namespace", "demo", "--model-id", model_dir.name,
        "--data-root", str(root), "--output", str(output),
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    assert "PyCaret 3.3.2" in body["error"]["message"]
    assert "qs ml train" in body["error"]["hint"] and "--namespace demo" in body["error"]["hint"]
    assert not output.exists()
