"""Tests for the ``qs analyze`` command adapters.

Each command is run through the runner (``skills.cli.main``) on small synthetic inputs and
compared with a direct call to the library function it wraps.
"""

from __future__ import annotations

import dataclasses
import json
from types import MappingProxyType

import numpy as np
import pandas as pd
import pytest

from skills.analyze.attribution_counterfactual import find_drawdown_episodes, performance_metrics
from skills.analyze.attribution_robustness import (
    block_bootstrap_metric,
    deflated_sharpe_ratio,
    pbo_from_candidate_returns,
    pbo_sensitivity_from_candidate_returns,
    rolling_metric_slices,
)
from skills.analyze.attribution_stat_tests import summarize_stat_tests
from skills.analyze.facade import AnalyzeFacade
from skills.analyze.factor_analysis import full_stat
from skills.analyze.factor_information import compute_ic_information_surface
from skills.analyze.ts_analysis import TimeSeriesAnalyzer
from skills.cli import main
from skills.cli.io import json_safe
from tests.fixtures.market_data import make_ohlcv
from tests.skills.analyze.conftest_phase03 import make_protocol, make_spec

SYMBOLS = ("S0", "S1", "S2", "S3", "S4", "S5")


def run(capsys, *argv):
    capsys.readouterr()  # drop output of earlier direct library calls (some print)
    code = main(["analyze", *argv])
    return code, json.loads(capsys.readouterr().out)


def assert_error(code, body, name, status):
    assert code == status, body
    assert body["ok"] is False
    assert body["error"]["code"] == name, body


@pytest.fixture(autouse=True)
def isolated_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", str(tmp_path / "data_root"))
    monkeypatch.setenv("QUANTSPACE_REPORTS_ROOT", str(tmp_path / "reports_root"))


def random_panel(symbols=SYMBOLS, periods=70, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for symbol in symbols:
        prices = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, periods)))
        frames.append(make_ohlcv(prices, symbol=symbol))
    return pd.concat(frames).sort_index()


def random_values(panel: pd.DataFrame, seed=5) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(size=len(panel)), index=panel.index, name="value")


@pytest.fixture
def panel_file(tmp_path):
    panel = random_panel()
    path = tmp_path / "panel.parquet"
    panel.to_parquet(path)
    return panel, path


def returns_file(tmp_path, name="returns.parquet", periods=160, seed=1):
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-01", periods=periods, name="eob")
    frame = pd.DataFrame({"return": rng.normal(0.0005, 0.01, periods)}, index=index)
    path = tmp_path / name
    frame.to_parquet(path)
    return frame, path


def candidates_file(tmp_path, periods=160, seed=2):
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-01", periods=periods, name="eob")
    frame = pd.DataFrame(
        rng.normal(0.0003, 0.01, (periods, 4)), index=index, columns=["A", "B", "C", "bench"]
    )
    path = tmp_path / "candidates.parquet"
    frame.to_parquet(path)
    return frame, path


# ---------------------------------------------------------------------------
# factor-ic
# ---------------------------------------------------------------------------


def factor_frame(panel, values):
    frame = panel[["close"]].copy()
    frame["fac_val"] = values.reindex(panel.index)
    return frame.reorder_levels(["eob", "symbol"]).sort_index()


@pytest.mark.parametrize("pearson", [False, True])
def test_factor_ic_equals_full_stat(capsys, tmp_path, panel_file, pearson):
    panel, panel_path = panel_file
    values = random_values(panel)
    factor_path = tmp_path / "factor.parquet"
    values.rename("fac_val").to_frame().to_parquet(factor_path)
    stats, ic, groups, turnover = full_stat(
        factor_frame(panel, values), n=3, g=4, rank_IC=not pearson, verbose=False, plot=False
    )
    argv = [
        "factor-ic", "--panel", str(panel_path), "--factor", str(factor_path),
        "--horizon", "3", "--groups", "4", "--out-dir", str(tmp_path / "out"),
    ]  # fmt: skip
    code, body = run(capsys, *argv, *(["--pearson"] if pearson else []))
    assert code == 0, body
    data = body["data"]
    assert data["ic_stats"] == json_safe(stats)
    assert data["group_mean_return"] == json_safe(groups.mean().to_dict())
    assert (data["ic_rows"], data["group_rows"], data["turnover_rows"]) == (
        len(ic),
        len(groups),
        len(turnover),
    )
    out = tmp_path / "out"
    pd.testing.assert_frame_equal(pd.read_parquet(out / "ic_series.parquet"), ic.to_frame("IC"))
    pd.testing.assert_frame_equal(pd.read_parquet(out / "group_return.parquet"), groups)
    pd.testing.assert_frame_equal(pd.read_parquet(out / "turnover.parquet"), turnover)
    assert [item["name"] for item in body["artifacts"]] == ["ic_series", "group_return", "turnover"]


def test_factor_ic_rank_and_pearson_differ(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    factor_path = tmp_path / "factor.parquet"
    random_values(panel).rename("fac_val").to_frame().to_parquet(factor_path)
    base = ["factor-ic", "--panel", str(panel_path), "--factor", str(factor_path)]
    _, rank = run(capsys, *base)
    _, pearson = run(capsys, *base, "--pearson")
    assert rank["data"]["ic_stats"] != pearson["data"]["ic_stats"]


def test_factor_ic_reads_the_store_and_accepts_a_value_column_name(capsys, tmp_path):
    from tests.fixtures.market_data import write_symbol_parquet

    root = tmp_path / "root"
    panel = random_panel()
    for symbol in SYMBOLS:
        write_symbol_parquet(root, symbol, panel.xs(symbol, level="symbol"))
    values = random_values(panel)
    factor_path = tmp_path / "factor.parquet"
    values.to_frame("value").to_parquet(factor_path)
    code, body = run(
        capsys, "factor-ic", "--symbols", ",".join(SYMBOLS), "--data-root", str(root),
        "--factor", str(factor_path), "--start", "2024-01-10", "--end", "2024-04-01",
    )  # fmt: skip
    assert code == 0, body
    window = panel.loc[
        (slice(None), slice(pd.Timestamp("2024-01-10"), pd.Timestamp("2024-04-01"))), :
    ]
    stats, ic, _, _ = full_stat(
        factor_frame(window, values), n=1, g=5, rank_IC=True, verbose=False, plot=False
    )
    assert body["data"]["ic_stats"] == json_safe(stats)
    assert body["data"]["ic_rows"] == len(ic)


def test_factor_ic_conflict_leaves_existing_outputs_untouched(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    factor_path = tmp_path / "factor.parquet"
    random_values(panel).rename("fac_val").to_frame().to_parquet(factor_path)
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "turnover.parquet"
    existing.write_bytes(b"keep me")
    argv = [
        "factor-ic", "--panel", str(panel_path), "--factor", str(factor_path),
        "--out-dir", str(out),
    ]  # fmt: skip
    code, body = run(capsys, *argv)
    assert_error(code, body, "CONFLICT", 2)
    assert existing.read_bytes() == b"keep me"
    assert sorted(path.name for path in out.iterdir()) == ["turnover.parquet"]
    code, body = run(capsys, *argv, "--overwrite")
    assert code == 0, body
    assert existing.read_bytes() != b"keep me"
    assert len(list(out.iterdir())) == 3


def test_factor_ic_input_errors(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    factor_path = tmp_path / "factor.parquet"
    random_values(panel).rename("fac_val").to_frame().to_parquet(factor_path)
    base = ["--factor", str(factor_path)]
    # Neither or both of a panel file and store symbols.
    code, body = run(capsys, "factor-ic", *base)
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "factor-ic", "--panel", str(panel_path), "--symbols", "S0", *base)
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "factor-ic", "--panel", str(panel_path), "--factor", "nope.parquet")
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, "factor-ic", "--panel", str(tmp_path / "nope.parquet"), *base)
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, "factor-ic", "--panel", str(panel_path), *base, "--groups", "1")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "factor-ic", "--panel", str(panel_path), *base, "--horizon", "0")
    assert_error(code, body, "INVALID_INPUT", 2)
    no_close = tmp_path / "no_close.parquet"
    panel.drop(columns=["close"]).to_parquet(no_close)
    code, body = run(capsys, "factor-ic", "--panel", str(no_close), *base)
    assert_error(code, body, "INVALID_INPUT", 2)
    two_columns = tmp_path / "two.parquet"
    pd.DataFrame({"a": 1.0, "b": 2.0}, index=panel.index).to_parquet(two_columns)
    code, body = run(capsys, "factor-ic", "--panel", str(panel_path), "--factor", str(two_columns))
    assert_error(code, body, "INVALID_INPUT", 2)


# ---------------------------------------------------------------------------
# ic-surface
# ---------------------------------------------------------------------------


def surface_inputs(tmp_path):
    panel = random_panel(periods=150, seed=11)
    # An open price that differs from close, so price_field is observable.
    panel["open"] = panel.groupby("symbol")["close"].shift(1).bfill()
    close = panel["close"].unstack("symbol").sort_index()
    rng = np.random.default_rng(12)
    factors = {
        "mom": close.pct_change(5) + rng.normal(0, 0.01, close.shape),
        "rev": -close.pct_change(2) + rng.normal(0, 0.01, close.shape),
    }
    panel_path = tmp_path / "panel.parquet"
    panel.to_parquet(panel_path)
    paths = {}
    for name, frame in factors.items():
        paths[name] = str(tmp_path / f"{name}.parquet")
        frame.to_parquet(paths[name])
    return panel, close, factors, panel_path, paths


def test_ic_surface_equals_the_library_surface(capsys, tmp_path):
    panel, close, factors, panel_path, paths = surface_inputs(tmp_path)
    segments = {"first": ["2024-01-01", "2024-03-01"], "rest": ["2024-03-02", None]}
    expected = compute_ic_information_surface(
        factors,
        close,
        horizons=[1, 5],
        lags=[0, 2],
        signal_lag=1,
        segments={name: tuple(bounds) for name, bounds in segments.items()},
        min_cross_section=3,
    )
    code, body = run(
        capsys, "ic-surface", "--panel", str(panel_path), "--factors", json.dumps(paths),
        "--horizons", "1,5", "--lags", "0,2", "--segments", json.dumps(segments),
        "--min-cross-section", "3", "--out-dir", str(tmp_path / "surface"),
        "--preview", "100",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["summary"] == json_safe(expected.summary.to_dict(orient="records"))
    assert body["data"]["daily_rows"] == len(expected.daily_ic)
    out = tmp_path / "surface"
    pd.testing.assert_frame_equal(pd.read_parquet(out / "summary.parquet"), expected.summary)
    pd.testing.assert_frame_equal(pd.read_parquet(out / "daily_ic.parquet"), expected.daily_ic)
    assert {row["factor"] for row in body["data"]["summary"]} == {"mom", "rev"}


def test_ic_surface_defaults_and_price_field(capsys, tmp_path):
    panel, close, factors, panel_path, paths = surface_inputs(tmp_path)
    expected = compute_ic_information_surface(
        factors, close, horizons=[2], lags=[0], signal_lag=1, min_cross_section=3
    )
    code, body = run(
        capsys, "ic-surface", "--panel", str(panel_path), "--factors", json.dumps(paths),
        "--horizons", "2", "--min-cross-section", "3",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["summary"] == json_safe(expected.summary.to_dict(orient="records"))
    code, body = run(
        capsys, "ic-surface", "--panel", str(panel_path), "--factors", json.dumps(paths),
        "--horizons", "2", "--price-field", "open", "--min-cross-section", "3",
    )  # fmt: skip
    assert code == 0, body
    on_open = compute_ic_information_surface(
        factors,
        panel["open"].unstack("symbol").sort_index(),
        horizons=[2],
        lags=[0],
        signal_lag=1,
        min_cross_section=3,
    )
    assert body["data"]["summary"] == json_safe(on_open.summary.to_dict(orient="records"))
    assert on_open.summary.to_dict(orient="records") != expected.summary.to_dict(orient="records")


def test_ic_surface_errors_and_conflicts(capsys, tmp_path):
    panel, close, factors, panel_path, paths = surface_inputs(tmp_path)
    base = ["ic-surface", "--panel", str(panel_path), "--factors", json.dumps(paths)]
    code, body = run(capsys, *base, "--horizons", "2", "--price-field", "vwap")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base)  # horizons is required
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "ic-surface", "--horizons", "2", "--factors", json.dumps(paths))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "ic-surface", "--panel", str(panel_path), "--horizons", "2",
        "--factors", json.dumps({"mom": str(tmp_path / "missing.parquet")}),
    )  # fmt: skip
    assert_error(code, body, "NOT_FOUND", 3)
    out = tmp_path / "surface"
    out.mkdir()
    (out / "summary.parquet").write_bytes(b"keep me")
    code, body = run(
        capsys, *base, "--horizons", "2", "--min-cross-section", "3", "--out-dir", str(out)
    )
    assert_error(code, body, "CONFLICT", 2)
    assert (out / "summary.parquet").read_bytes() == b"keep me"
    assert not (out / "daily_ic.parquet").exists()


# ---------------------------------------------------------------------------
# perf and drawdowns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("annualization", [252, 365])
def test_perf_equals_performance_metrics(capsys, tmp_path, annualization):
    frame, path = returns_file(tmp_path)
    expected = performance_metrics(frame["return"], annualization=annualization)
    code, body = run(capsys, "perf", "--returns", str(path), "--annualization", str(annualization))
    assert code == 0, body
    assert body["data"] == {"metrics": json_safe(expected), "rows": len(frame)}
    assert set(body["data"]["metrics"]) >= {"ann_return", "max_drawdown", "sharpe", "total_return"}


def test_perf_custom_column_and_errors(capsys, tmp_path):
    frame, path = returns_file(tmp_path)
    other = tmp_path / "other.parquet"
    frame.rename(columns={"return": "pnl"}).to_parquet(other)
    code, body = run(capsys, "perf", "--returns", str(other), "--column", "pnl")
    assert code == 0, body
    assert body["data"]["metrics"] == json_safe(performance_metrics(frame["return"]))
    code, body = run(capsys, "perf", "--returns", str(other))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "perf", "--returns", str(tmp_path / "missing.parquet"))
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, "perf", "--returns", str(path), "--annualization", "0")
    assert_error(code, body, "INVALID_INPUT", 2)
    bad = tmp_path / "bad.txt"
    bad.write_text("return\n1\n")
    code, body = run(capsys, "perf", "--returns", str(bad))
    assert_error(code, body, "INVALID_INPUT", 2)


def test_perf_reads_csv_with_an_eob_column(capsys, tmp_path):
    frame, _ = returns_file(tmp_path)
    csv = tmp_path / "returns.csv"
    frame.reset_index().to_csv(csv, index=False)
    code, body = run(capsys, "perf", "--returns", str(csv))
    assert code == 0, body
    # CSV floats are not bit-exact after a round trip.
    expected = performance_metrics(frame["return"])
    assert body["data"]["metrics"] == pytest.approx(json_safe(expected), rel=1e-9)


def test_drawdowns_equal_find_drawdown_episodes(capsys, tmp_path):
    frame, path = returns_file(tmp_path)
    expected = find_drawdown_episodes(frame["return"], top_n=3, min_depth=0.01)
    code, body = run(
        capsys, "drawdowns", "--returns", str(path), "--top-n", "3", "--min-depth", "0.01"
    )
    assert code == 0, body
    assert body["data"]["episodes"] == json_safe(expected.to_dict(orient="records"))
    assert body["data"]["rows"] == len(expected) <= 3
    code, body = run(capsys, "drawdowns", "--returns", str(path), "--top-n", "0")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "drawdowns", "--returns", str(tmp_path / "missing.parquet"))
    assert_error(code, body, "NOT_FOUND", 3)


# ---------------------------------------------------------------------------
# overfit
# ---------------------------------------------------------------------------


def test_overfit_defaults_run_dsr_and_pbo(capsys, tmp_path):
    frame, path = candidates_file(tmp_path)
    columns = list(frame)
    code, body = run(capsys, "overfit", "--candidates", str(path))
    assert code == 0, body
    results = body["data"]["results"]
    assert set(results) == {"dsr", "pbo"}
    expected_dsr = {
        column: deflated_sharpe_ratio(
            frame[column], n_trials=len(columns), benchmark_sr=0.0, annualization=252
        )
        for column in columns
    }
    assert results["dsr"] == json_safe(expected_dsr)
    pbo = pbo_from_candidate_returns(frame, n_splits=4, annualization=252)
    details = pbo.pop("details")
    assert results["pbo"] == json_safe(
        {**pbo, "details_rows": len(details), "details": details.head(5).to_dict("records")}
    )


def test_overfit_every_test_equals_the_library(capsys, tmp_path):
    frame, path = candidates_file(tmp_path)
    columns = ["A", "B", "C"]
    code, body = run(
        capsys, "overfit", "--candidates", str(path), "--benchmark-col", "bench",
        "--tests", '["dsr","pbo","pbo-sensitivity","spa","bootstrap","rolling"]',
        "--n-trials", "7", "--benchmark-sr", "0.1", "--n-splits", "6",
        "--split-values", "[4,6]", "--promotion-threshold", "0.3", "--n-bootstrap", "25",
        "--block-size", "5", "--seed", "11", "--windows", "[30,60]", "--annualization", "250",
        "--preview", "3",
    )  # fmt: skip
    assert code == 0, body
    results = body["data"]["results"]
    assert set(results) == {"dsr", "pbo", "pbo_sensitivity", "spa", "bootstrap", "rolling"}
    # The benchmark column is excluded from every candidate test.
    assert (
        set(results["dsr"]) == set(columns) == set(results["bootstrap"]) == set(results["rolling"])
    )
    assert results["dsr"] == json_safe(
        {
            column: deflated_sharpe_ratio(
                frame[column], n_trials=7, benchmark_sr=0.1, annualization=250
            )
            for column in columns
        }
    )
    pbo = pbo_from_candidate_returns(frame[columns], n_splits=6, annualization=250)
    details = pbo.pop("details")
    assert results["pbo"] == json_safe(
        {**pbo, "details_rows": len(details), "details": details.head(3).to_dict("records")}
    )
    assert len(results["pbo"]["details"]) == 3 and results["pbo"]["details_rows"] == len(details)
    assert results["pbo_sensitivity"] == json_safe(
        pbo_sensitivity_from_candidate_returns(
            frame[columns], split_values=[4, 6], annualization=250, promotion_threshold=0.3
        ).to_dict(orient="records")
    )
    assert results["spa"] == json_safe(
        summarize_stat_tests(
            frame, benchmark_col="bench", block_size=5, random_state=11, n_bootstrap=25
        ).to_dict(orient="records")
    )
    assert results["bootstrap"] == json_safe(
        {
            column: block_bootstrap_metric(
                frame[column],
                lambda values: float(values.mean()),
                block_size=5,
                random_state=11,
                n_bootstrap=25,
            )
            for column in columns
        }
    )
    assert results["rolling"] == json_safe(
        {
            column: rolling_metric_slices(
                frame[column], windows=[30, 60], annualization=250
            ).to_dict(orient="records")
            for column in columns
        }
    )


def test_overfit_seed_makes_bootstrap_reproducible(capsys, tmp_path):
    _, path = candidates_file(tmp_path)
    argv = [
        "overfit", "--candidates", str(path), "--tests", '["bootstrap"]',
        "--n-bootstrap", "25", "--seed", "4",
    ]  # fmt: skip
    _, first = run(capsys, *argv)
    _, second = run(capsys, *argv)
    assert first["data"] == second["data"]
    _, third = run(capsys, *argv[:-1], "5")
    assert third["data"] != first["data"]


def test_overfit_errors(capsys, tmp_path):
    frame, path = candidates_file(tmp_path)
    code, body = run(capsys, "overfit", "--candidates", str(path), "--benchmark-col", "nope")
    assert_error(code, body, "INVALID_INPUT", 2)
    assert "nope" in body["error"]["message"]
    code, body = run(capsys, "overfit", "--candidates", str(path), "--tests", '["nope"]')
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "overfit", "--candidates", str(path), "--n-splits", "3")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "overfit", "--candidates", str(tmp_path / "missing.parquet"))
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, "overfit", "--candidates", str(path), "--n-trials", "0")
    assert_error(code, body, "INVALID_INPUT", 2)
    only_benchmark = tmp_path / "only_benchmark.parquet"
    frame[["bench"]].to_parquet(only_benchmark)
    code, body = run(
        capsys, "overfit", "--candidates", str(only_benchmark), "--benchmark-col", "bench"
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    empty = tmp_path / "empty.parquet"
    frame.iloc[0:0].to_parquet(empty)
    code, body = run(capsys, "overfit", "--candidates", str(empty))
    assert_error(code, body, "INVALID_INPUT", 2)


# ---------------------------------------------------------------------------
# stationarity
# ---------------------------------------------------------------------------


def close_file(tmp_path, periods=160, seed=6):
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-01", periods=periods, name="eob")
    frame = pd.DataFrame(
        {"close": 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, periods)))}, index=index
    )
    path = tmp_path / "bars.parquet"
    frame.to_parquet(path)
    return frame, path


def test_stationarity_equals_time_series_analyzer(capsys, tmp_path):
    frame, path = close_file(tmp_path)
    analyzer = TimeSeriesAnalyzer(frame["close"])
    analyzer.analyze_windows([20, 40])
    expected = json_safe({str(window): value for window, value in analyzer.results.items()})
    code, body = run(capsys, "stationarity", "--series", str(path), "--windows", "20,40")
    assert code == 0, body
    assert body["data"]["windows"] == expected and set(expected) == {"20", "40"}
    # The default windows are 20, 40 and 60.
    code, body = run(capsys, "stationarity", "--series", str(path))
    assert code == 0 and set(body["data"]["windows"]) == {"20", "40", "60"}


def test_stationarity_reports_skipped_windows_and_rejects_bad_input(capsys, tmp_path):
    frame, path = close_file(tmp_path)
    code, body = run(capsys, "stationarity", "--series", str(path), "--windows", "500")
    assert code == 0, body
    assert body["data"]["windows"] == {}
    assert any("skipped" in warning and "500" in warning for warning in body["warnings"])
    code, body = run(capsys, "stationarity", "--series", str(path), "--windows", "0")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "stationarity", "--series", str(path), "--column", "volume")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, "stationarity", "--series", str(tmp_path / "missing.parquet"))
    assert_error(code, body, "NOT_FOUND", 3)


# ---------------------------------------------------------------------------
# preflight and evaluate
# ---------------------------------------------------------------------------


def plain(value):
    """Dataclass snapshots as plain JSON: mappingproxy to dict, tuples to lists."""
    if dataclasses.is_dataclass(value):
        return {item.name: plain(getattr(value, item.name)) for item in dataclasses.fields(value)}
    if isinstance(value, (dict, MappingProxyType)):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def snapshot_files(tmp_path, spec=None, protocol=None):
    spec_path, protocol_path = tmp_path / "spec.json", tmp_path / "protocol.json"
    spec_path.write_text(json.dumps(plain(spec or make_spec())))
    protocol_path.write_text(json.dumps(plain(protocol or make_protocol())))
    return ["--spec-json", str(spec_path), "--protocol-json", str(protocol_path)]


def summary_of(result) -> dict:
    public = result.to_public_dict()
    return {
        "completion_status": public["completion_status"],
        "hard_failed": result.hard_failed,
        "sections": {item["name"]: item["status"] for item in public["sections"]},
        "failed_findings": json_safe(
            [item for item in public["findings"] if not item.get("passed", True)]
        ),
        "metrics": json_safe(
            {
                item["name"]: item["value"]
                for item in public["metrics"]
                if item.get("unavailable_reason") is None
            }
        ),
    }


def test_preflight_equals_the_facade(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    expected = AnalyzeFacade().preflight(
        panel=panel, spec=make_spec(), protocol=make_protocol(), allowed_fields=None
    )
    code, body = run(capsys, "preflight", "--panel", str(panel_path), *snapshot_files(tmp_path))
    assert code == 0 and body["ok"], body
    assert body["data"] == json_safe(summary_of(expected))
    assert body["data"]["hard_failed"] is False


def test_preflight_hard_failure_is_exit_one_with_data(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    expected = AnalyzeFacade().preflight(
        panel=panel, spec=make_spec(), protocol=make_protocol(), allowed_fields=["volume"]
    )
    assert expected.hard_failed
    code, body = run(
        capsys, "preflight", "--panel", str(panel_path), *snapshot_files(tmp_path),
        "--allowed-fields", "volume",
    )  # fmt: skip
    assert code == 1 and body["ok"] is False, body
    assert body["data"] == json_safe(summary_of(expected))
    assert body["data"]["hard_failed"] is True
    assert "INPUT_FIELD_NOT_ALLOWED" in {item["name"] for item in body["data"]["failed_findings"]}
    assert body["error"]["code"] == "CHECK_FAILED"


def test_preflight_input_errors(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    files = snapshot_files(tmp_path)
    code, body = run(capsys, "preflight", *files)
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "preflight", "--panel", str(panel_path), "--spec-json", "missing.json",
        "--protocol-json", files[3],
    )  # fmt: skip
    assert_error(code, body, "NOT_FOUND", 3)
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"factor_id": "x"}))
    code, body = run(
        capsys, "preflight", "--panel", str(panel_path), "--spec-json", str(broken),
        "--protocol-json", files[3],
    )  # fmt: skip
    assert code == 2 and body["ok"] is False
    listed = tmp_path / "list.json"
    listed.write_text("[1]")
    code, body = run(
        capsys, "preflight", "--panel", str(panel_path), "--spec-json", str(listed),
        "--protocol-json", files[3],
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)


def test_evaluate_equals_the_facade_and_writes_the_public_result(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    values = random_values(panel)
    values_path = tmp_path / "values.parquet"
    values.to_frame().to_parquet(values_path)
    expected = AnalyzeFacade().evaluate(
        panel=panel, spec=make_spec(), protocol=make_protocol(), values=values,
        valid_mask=values.notna(), allowed_fields=None, include_backtest=True, regime_masks=None,
    )  # fmt: skip
    out = tmp_path / "evaluation.json"
    code, body = run(
        capsys, "evaluate", "--panel", str(panel_path), *snapshot_files(tmp_path),
        "--values", str(values_path), "--output", str(out),
    )  # fmt: skip
    assert code == 0 and body["ok"], body
    assert body["data"] == json_safe(summary_of(expected))
    assert body["data"]["completion_status"] == "partial"
    assert any(name.startswith("backtest_") for name in body["data"]["metrics"])
    assert json.loads(out.read_text()) == json.loads(
        json.dumps(json_safe(expected.to_public_dict()))
    )
    assert body["artifacts"][0]["name"] == "analyze_result"
    assert body["artifacts"][0]["path"] == str(out.resolve())


def no_backtest_options(tmp_path):
    """Skip the backtest through JSON input; the --no-backtest flag is tested below."""
    path = tmp_path / "no_backtest.json"
    path.write_text(json.dumps({"backtest": False}))
    return ["--input-json", str(path)]


def no_backtest_expected(panel, values):
    return AnalyzeFacade().evaluate(
        panel=panel, spec=make_spec(), protocol=make_protocol(), values=values,
        valid_mask=values.notna(), allowed_fields=None, include_backtest=False, regime_masks=None,
    )  # fmt: skip


def test_evaluate_no_backtest_through_input_json_skips_the_backtest(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    values = random_values(panel)
    values_path = tmp_path / "values.parquet"
    values.to_frame().to_parquet(values_path)
    spec_flag, spec_path, protocol_flag, protocol_path = snapshot_files(tmp_path)
    options = tmp_path / "options.json"
    options.write_text(
        json.dumps(
            {
                "panel": str(panel_path),
                "spec_json": spec_path,
                "protocol_json": protocol_path,
                "values": str(values_path),
                "backtest": False,
            }
        )
    )
    code, body = run(capsys, "evaluate", "--input-json", str(options))
    assert code == 0, body
    assert body["data"] == json_safe(summary_of(no_backtest_expected(panel, values)))
    assert not any(name.startswith("backtest_") for name in body["data"]["metrics"])
    assert body["artifacts"] == []


def test_evaluate_no_backtest_flag_skips_the_backtest(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    values = random_values(panel)
    values_path = tmp_path / "values.parquet"
    values.to_frame().to_parquet(values_path)
    code, body = run(
        capsys, "evaluate", "--panel", str(panel_path), *snapshot_files(tmp_path),
        "--values", str(values_path), "--no-backtest",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"] == json_safe(summary_of(no_backtest_expected(panel, values)))


def values_with_warmup_gaps(panel):
    """Factor values that are NaN for the first two bars of every symbol (the spec's warmup)."""
    values = random_values(panel)
    position = values.groupby(level="symbol").cumcount()
    return values.where(position >= 2)


def test_evaluate_valid_mask_file_is_used(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    values = values_with_warmup_gaps(panel)
    values_path = tmp_path / "values.parquet"
    values.to_frame().to_parquet(values_path)
    argv = [
        "evaluate", "--panel", str(panel_path), *snapshot_files(tmp_path),
        "--values", str(values_path), *no_backtest_options(tmp_path),
    ]  # fmt: skip
    # Default validity is "value is not missing" and agrees with the values.
    code, body = run(capsys, *argv)
    assert code == 0, body
    assert body["data"] == json_safe(summary_of(no_backtest_expected(panel, values)))
    explicit = tmp_path / "valid.parquet"
    values.notna().rename("valid_mask").to_frame().to_parquet(explicit)
    code, same = run(capsys, *argv, "--valid-mask", str(explicit))
    assert code == 0, same
    assert same["data"] == body["data"]
    # A mask that disagrees with the finite values is a hard alignment failure.
    wrong = tmp_path / "wrong.parquet"
    pd.Series(True, index=panel.index, name="valid_mask").to_frame().to_parquet(wrong)
    expected = AnalyzeFacade().evaluate(
        panel=panel, spec=make_spec(), protocol=make_protocol(), values=values,
        valid_mask=pd.Series(True, index=panel.index), allowed_fields=None,
        include_backtest=False, regime_masks=None,
    )  # fmt: skip
    code, body = run(capsys, *argv, "--valid-mask", str(wrong))
    assert code == 1 and body["ok"] is False, body
    assert body["data"] == json_safe(summary_of(expected))
    assert "ALIGNMENT_MASK_VALUE_AGREEMENT" in {
        item["name"] for item in body["data"]["failed_findings"]
    }


def test_evaluate_regime_masks_file_supplies_declared_regimes(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    values = random_values(panel)
    values_path = tmp_path / "values.parquet"
    values.to_frame().to_parquet(values_path)
    late = pd.Series(
        values.index.get_level_values("eob") > panel.index.levels[1][35], index=panel.index
    )
    mask_path = tmp_path / "late.parquet"
    late.rename("value").to_frame().to_parquet(mask_path)
    regimes = tmp_path / "regimes.json"
    regimes.write_text(json.dumps({"late": str(mask_path)}))
    protocol = make_protocol(regimes=("late",))
    expected = AnalyzeFacade().evaluate(
        panel=panel, spec=make_spec(), protocol=protocol, values=values, valid_mask=values.notna(),
        allowed_fields=None, include_backtest=False, regime_masks={"late": late},
    )  # fmt: skip
    argv = [
        "evaluate", "--panel", str(panel_path), *snapshot_files(tmp_path, protocol=protocol),
        "--values", str(values_path), *no_backtest_options(tmp_path),
    ]  # fmt: skip
    code, body = run(capsys, *argv, "--regime-masks-json", str(regimes))
    assert code == 0, body
    assert body["data"] == json_safe(summary_of(expected))
    assert "robustness_regime_late_rank_ic_mean" in body["data"]["metrics"]
    # Without the mask file the declared regime is unavailable.
    code, body = run(capsys, *argv)
    assert code == 0, body
    assert "ROBUSTNESS_REGIME_UNAVAILABLE" in {
        item["name"] for item in body["data"]["failed_findings"]
    }
    listed = tmp_path / "listed.json"
    listed.write_text("[]")
    code, body = run(capsys, *argv, "--regime-masks-json", str(listed))
    assert_error(code, body, "INVALID_INPUT", 2)


def test_evaluate_requires_values_on_exactly_the_panel_index(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    values = random_values(panel)
    dropped = values.iloc[5:]  # what a dropna'd factor looks like
    values_path = tmp_path / "values.parquet"
    dropped.to_frame().to_parquet(values_path)
    out = tmp_path / "evaluation.json"
    expected = AnalyzeFacade().evaluate(
        panel=panel, spec=make_spec(), protocol=make_protocol(), values=dropped,
        valid_mask=dropped.notna(), allowed_fields=None, include_backtest=True, regime_masks=None,
    )  # fmt: skip
    code, body = run(
        capsys, "evaluate", "--panel", str(panel_path), *snapshot_files(tmp_path),
        "--values", str(values_path), "--output", str(out),
    )  # fmt: skip
    assert code == 1 and body["ok"] is False, body
    assert body["data"]["hard_failed"] is True
    assert body["data"]["completion_status"] == "hard_failed"
    assert "ALIGNMENT_INDEX_VALUES" in {item["name"] for item in body["data"]["failed_findings"]}
    assert body["data"] == json_safe(summary_of(expected))
    # The failed result is still written, with the hard failure recorded.
    assert out.exists() and json.loads(out.read_text())["hard_failed"] is True


def test_evaluate_refuses_prefix_recompute_protocols(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    values_path = tmp_path / "values.parquet"
    random_values(panel).to_frame().to_parquet(values_path)
    code, body = run(
        capsys, "evaluate", "--panel", str(panel_path),
        *snapshot_files(tmp_path, protocol=make_protocol(require_prefix_recompute=True)),
        "--values", str(values_path),
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    assert "factor-mining" in body["error"]["message"]


def test_evaluate_conflict_and_input_errors(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    values_path = tmp_path / "values.parquet"
    random_values(panel).to_frame().to_parquet(values_path)
    files = snapshot_files(tmp_path)
    out = tmp_path / "evaluation.json"
    out.write_text("keep me")
    argv = [
        "evaluate", "--panel", str(panel_path), *files, "--values", str(values_path),
        "--output", str(out),
    ]  # fmt: skip
    code, body = run(capsys, *argv)
    assert_error(code, body, "CONFLICT", 2)
    assert out.read_text() == "keep me"
    code, body = run(capsys, *argv, "--overwrite")
    assert code == 0, body
    assert out.read_text() != "keep me"
    code, body = run(
        capsys, "evaluate", "--panel", str(panel_path), *files, "--values", "missing.parquet"
    )
    assert_error(code, body, "NOT_FOUND", 3)
    code, body = run(capsys, "evaluate", "--panel", str(panel_path), *files)
    assert_error(code, body, "INVALID_INPUT", 2)
    ambiguous = tmp_path / "ambiguous.parquet"
    pd.DataFrame({"a": 1.0, "b": 2.0}, index=panel.index).to_parquet(ambiguous)
    code, body = run(
        capsys, "evaluate", "--panel", str(panel_path), *files, "--values", str(ambiguous)
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    # Output may not point into a managed store namespace.
    managed = tmp_path / "data_root" / "market" / "1d" / "x.json"
    code, body = run(
        capsys, "evaluate", "--panel", str(panel_path), *files, "--values", str(values_path),
        "--output", str(managed), "--data-root", str(tmp_path / "data_root"),
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)
    assert not managed.exists()
