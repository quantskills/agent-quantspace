"""Tests for the ``qs research`` command adapters."""

from __future__ import annotations

import json
import os
import sys
import types

import numpy as np
import pandas as pd
import pytest

from skills.cli import main
from skills.cli.io import json_safe, read_panel
from skills.compute.wrappers import Factor
from skills.research.factor_screening import batch_evaluate, screen_all_indicators
from skills.research.param_sensitivity import param_sweep
from tests.fixtures.market_data import make_ohlcv, write_symbol_parquet

SYMBOLS = ("S0", "S1", "S2", "S3", "S4", "S5")
INDICATORS = "roc,rsi"


def run(capsys, *argv):
    capsys.readouterr()
    code = main(["research", *argv])
    return code, json.loads(capsys.readouterr().out)


def assert_error(code, body, name, status):
    assert code == status, body
    assert body["ok"] is False
    assert body["error"]["code"] == name, body


@pytest.fixture(autouse=True)
def isolated_roots(monkeypatch, tmp_path):
    """Environment roots under tmp_path; matplotlib untouched unless a test sets it."""
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", str(tmp_path / "env_data"))
    monkeypatch.setenv("QUANTSPACE_REPORTS_ROOT", str(tmp_path / "env_reports"))


def random_panel(symbols=SYMBOLS, periods=150, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for symbol in symbols:
        prices = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, periods)))
        frames.append(make_ohlcv(prices, symbol=symbol))
    return pd.concat(frames).sort_index()


@pytest.fixture
def panel_file(tmp_path):
    panel = random_panel()
    path = tmp_path / "panel.parquet"
    panel.to_parquet(path)
    return panel, path


def screen_files(root):
    return sorted(
        path.relative_to(root).as_posix()
        for path in (root / "factor_test").rglob("*")
        if path.is_file()
    )


def with_env_root(monkeypatch, root):
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", str(root))


# ---------------------------------------------------------------------------
# screen
# ---------------------------------------------------------------------------


def test_screen_equals_screen_all_indicators(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    expected = screen_all_indicators(
        namespace="demo",
        n=3,
        g=3,
        top_k=0,
        indicator_names=["roc", "rsi"],
        persist=False,
        data=panel,
    )
    output = tmp_path / "ranking.parquet"
    code, body = run(
        capsys, "screen", "--panel", str(panel_path), "--namespace", "demo", "--horizon", "3", "--groups", "3",
        "--indicators", INDICATORS, "--output", str(output), "--preview", "100",
    )  # fmt: skip
    assert code == 0, body
    assert len(expected) == 2
    assert body["data"] == {
        "rows": 2,
        "persisted": False,
        "ranking": json_safe(expected.to_dict(orient="records")),
    }
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)
    assert [item["name"] for item in body["artifacts"]] == ["ranking"]
    ics = [row["IC_IR"] for row in body["data"]["ranking"]]
    assert ics == sorted(ics, key=abs, reverse=True)  # ranked by |IC_IR|


def test_screen_top_k_and_unknown_indicators(capsys, panel_file):
    panel, panel_path = panel_file
    expected = screen_all_indicators(
        namespace="demo",
        n=5,
        g=3,
        top_k=1,
        indicator_names=["roc", "rsi"],
        persist=False,
        data=panel,
    )
    code, body = run(
        capsys, "screen", "--panel", str(panel_path), "--namespace", "demo", "--groups", "3",
        "--top-k", "1", "--indicators", INDICATORS,
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["rows"] == 1
    assert body["data"]["ranking"] == json_safe(expected.to_dict(orient="records"))
    # Unknown names are skipped; with nothing left the ranking is empty and nothing is persisted.
    code, body = run(
        capsys, "screen", "--panel", str(panel_path), "--namespace", "demo",
        "--indicators", "no_such_indicator", "--write",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"] == {"rows": 0, "persisted": False, "ranking": []}
    assert body["warnings"] == [
        "No indicator produced a ranking row; skipped or failed indicators are logged on stderr."
    ]


def test_screen_reads_the_store_window(capsys, tmp_path):
    root = tmp_path / "root"
    panel = random_panel()
    for symbol in SYMBOLS:
        write_symbol_parquet(root, symbol, panel.xs(symbol, level="symbol"))
    window = panel.loc[
        (slice(None), slice(pd.Timestamp("2024-01-20"), pd.Timestamp("2024-05-01"))), :
    ]
    expected = screen_all_indicators(
        namespace="demo", n=5, g=3, indicator_names=["roc", "rsi"], persist=False, data=window
    )
    code, body = run(
        capsys, "screen", "--symbols", ",".join(SYMBOLS), "--data-root", str(root),
        "--start", "2024-01-20", "--end", "2024-05-01", "--namespace", "demo", "--groups", "3",
        "--indicators", INDICATORS, "--preview", "100",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["ranking"] == json_safe(expected.to_dict(orient="records"))


def test_screen_without_write_leaves_the_store_untouched(capsys, tmp_path, panel_file):
    _, panel_path = panel_file
    root = tmp_path / "root"
    assert not root.exists()
    code, body = run(
        capsys, "screen", "--panel", str(panel_path), "--namespace", "demo", "--groups", "3",
        "--indicators", INDICATORS, "--data-root", str(root),
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["persisted"] is False and body["data"]["rows"] == 2
    assert not root.exists()
    assert not (tmp_path / "env_data").exists()


def test_screen_write_persists_the_factor_tests_under_the_data_root(
    capsys, monkeypatch, tmp_path, panel_file
):
    panel, panel_path = panel_file
    root = tmp_path / "root"
    code, body = run(
        capsys, "screen", "--panel", str(panel_path), "--namespace", "demo", "--groups", "3",
        "--indicators", INDICATORS, "--data-root", str(root), "--write",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["persisted"] is True
    assert screen_files(root) == [
        "factor_test/demo/group_return/roc__n5_g3.parquet",
        "factor_test/demo/group_return/rsi__n5_g3.parquet",
        "factor_test/demo/ic/roc__n5.parquet",
        "factor_test/demo/ic/rsi__n5.parquet",
        "factor_test/demo/summary.parquet",
        "factor_test/demo/turnover/roc__n5_g3.parquet",
        "factor_test/demo/turnover/rsi__n5_g3.parquet",
    ]
    # Nothing leaks into the environment's own data root.
    assert not (tmp_path / "env_data").exists()
    # The stored files equal what the library persists for the same call.
    direct_root = tmp_path / "direct"
    with_env_root(monkeypatch, direct_root)
    screen_all_indicators(
        namespace="demo", n=5, g=3, indicator_names=["roc", "rsi"], persist=True, data=panel
    )
    assert screen_files(direct_root) == screen_files(root)
    for name in screen_files(root):
        # summary rows carry a wall-clock ``tested_at`` stamp; everything else must match.
        pd.testing.assert_frame_equal(
            pd.read_parquet(root / name).drop(columns=["tested_at"], errors="ignore"),
            pd.read_parquet(direct_root / name).drop(columns=["tested_at"], errors="ignore"),
            check_exact=False,
        )


def test_screen_write_reports_persist_failures_the_library_swallows(
    capsys, monkeypatch, tmp_path, panel_file
):
    from skills.store.data_manager import DataManager

    def fail(self, **kwargs):
        raise OSError("disk full")

    # screen_all_indicators logs a failed save_factor_test and carries on.
    monkeypatch.setattr(DataManager, "save_factor_test", fail)
    _, panel_path = panel_file
    code, body = run(
        capsys, "screen", "--panel", str(panel_path), "--namespace", "demo", "--groups", "3",
        "--indicators", INDICATORS, "--data-root", str(tmp_path / "root"), "--write",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["rows"] == 2 and body["data"]["persisted"] is False
    assert body["warnings"] == [
        "--write was given but no factor-test file was written; persist failures are logged "
        "on stderr."
    ]
    assert screen_files(tmp_path / "root") == []


def test_screen_write_without_data_root_uses_the_environment_root(capsys, tmp_path, panel_file):
    _, panel_path = panel_file
    code, body = run(
        capsys, "screen", "--panel", str(panel_path), "--namespace", "demo", "--groups", "3",
        "--indicators", "roc", "--write",
    )  # fmt: skip
    assert code == 0, body
    assert screen_files(tmp_path / "env_data") == [
        "factor_test/demo/group_return/roc__n5_g3.parquet",
        "factor_test/demo/ic/roc__n5.parquet",
        "factor_test/demo/summary.parquet",
        "factor_test/demo/turnover/roc__n5_g3.parquet",
    ]


def test_data_root_is_scoped_to_the_call_and_the_environment_is_restored(
    capsys, monkeypatch, tmp_path, panel_file
):
    _, panel_path = panel_file
    sentinel = str(tmp_path / "sentinel_root")
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", sentinel)
    argv = [
        "screen", "--panel", str(panel_path), "--namespace", "demo", "--groups", "3",
        "--indicators", "roc", "--data-root", str(tmp_path / "root"),
    ]  # fmt: skip
    seen = []

    def spy(**kwargs):
        seen.append(os.environ.get("QUANTSPACE_DATA_ROOT"))
        return pd.DataFrame()

    code, body = run(capsys, *argv)
    assert code == 0, body
    assert os.environ["QUANTSPACE_DATA_ROOT"] == sentinel
    # During the call the template's DataManager() sees the command's root.
    monkeypatch.setattr("skills.research.factor_screening.screen_all_indicators", spy)
    code, body = run(capsys, *argv)
    assert code == 0, body
    assert seen == [str((tmp_path / "root").resolve())] or seen == [str(tmp_path / "root")]
    assert os.environ["QUANTSPACE_DATA_ROOT"] == sentinel
    # Also restored when the library call fails, and removed again when it was unset.
    monkeypatch.setattr(
        "skills.research.factor_screening.screen_all_indicators",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    code, body = run(capsys, *argv)
    assert code == 1 and body["ok"] is False
    assert os.environ["QUANTSPACE_DATA_ROOT"] == sentinel
    monkeypatch.delenv("QUANTSPACE_DATA_ROOT")
    code, body = run(capsys, *argv)
    assert code == 1 and "QUANTSPACE_DATA_ROOT" not in os.environ


def test_screen_input_errors_create_and_persist_nothing(capsys, tmp_path, panel_file):
    panel, panel_path = panel_file
    root = tmp_path / "root"
    base = ["screen", "--data-root", str(root), "--indicators", "roc", "--write"]
    code, body = run(capsys, *base, "--namespace", "demo")  # no panel source
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, *base, "--namespace", "demo", "--panel", str(panel_path), "--symbols", "S0"
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    for namespace in ("a/b", "..", ""):
        code, body = run(capsys, *base, "--panel", str(panel_path), "--namespace", namespace)
        assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--panel", str(panel_path))  # namespace is required
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, *base, "--panel", str(tmp_path / "missing.parquet"), "--namespace", "demo"
    )
    assert_error(code, body, "NOT_FOUND", 3)
    for flag, value in (("--horizon", "0"), ("--groups", "1"), ("--top-k", "-1")):
        code, body = run(
            capsys, *base, "--panel", str(panel_path), "--namespace", "demo", flag, value
        )
        assert_error(code, body, "INVALID_INPUT", 2)
    no_close = tmp_path / "no_close.parquet"
    panel.drop(columns=["close"]).to_parquet(no_close)
    code, body = run(capsys, *base, "--panel", str(no_close), "--namespace", "demo")
    # The library logs and skips an indicator that fails (here: no ``close`` column), so the
    # call succeeds with an empty ranking, a warning, and nothing persisted.
    assert code == 0, body
    assert body["data"] == {"rows": 0, "persisted": False, "ranking": []}
    assert "No indicator produced a ranking row" in body["warnings"][0]
    assert screen_files(root) == []


def test_screen_output_conflict_stops_before_screening_or_persisting(capsys, tmp_path, panel_file):
    _, panel_path = panel_file
    root = tmp_path / "root"
    output = tmp_path / "ranking.parquet"
    output.write_bytes(b"keep me")
    argv = [
        "screen", "--panel", str(panel_path), "--namespace", "demo", "--groups", "3",
        "--indicators", "roc", "--data-root", str(root), "--write", "--output", str(output),
    ]  # fmt: skip
    code, body = run(capsys, *argv)
    assert_error(code, body, "CONFLICT", 2)
    assert output.read_bytes() == b"keep me"
    assert not root.exists()  # no store was constructed, nothing persisted
    code, body = run(capsys, *argv, "--overwrite")
    assert code == 0, body
    assert output.read_bytes() != b"keep me" and len(screen_files(root)) == 4
    managed = tmp_path / "root" / "factor_test" / "ranking.parquet"
    code, body = run(
        capsys, "screen", "--panel", str(panel_path), "--namespace", "demo",
        "--indicators", "roc", "--data-root", str(root), "--output", str(managed),
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)


# ---------------------------------------------------------------------------
# batch-screen
# ---------------------------------------------------------------------------


@pytest.fixture
def batch_files(tmp_path):
    files = {}
    for index, name in enumerate(("alpha", "beta")):
        panel = random_panel(periods=120, seed=20 + index)
        path = tmp_path / f"{name}.parquet"
        panel.to_parquet(path)
        files[name] = path
    return files


def test_batch_screen_equals_batch_evaluate(capsys, tmp_path, batch_files):
    panels = {name: read_panel(path) for name, path in batch_files.items()}
    expected = batch_evaluate(
        namespaces=list(panels), n_list=[1, 5], g=3, indicator_names=["roc", "rsi"],
        persist=False, data_by_namespace=panels,
    )  # fmt: skip
    assert len(expected) == 8
    output = tmp_path / "combined.parquet"
    code, body = run(
        capsys, "batch-screen", "--panels", json.dumps({k: str(v) for k, v in batch_files.items()}),
        "--n-list", "1,5", "--groups", "3", "--indicators", INDICATORS, "--output", str(output),
        "--preview", "100",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"] == {
        "rows": 8,
        "persisted": False,
        "ranking": json_safe(expected.to_dict(orient="records")),
    }
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)
    assert {row["namespace"] for row in body["data"]["ranking"]} == {"alpha", "beta"}
    assert {row["n"] for row in body["data"]["ranking"]} == {1, 5}


def test_batch_screen_skips_panels_with_fewer_than_three_symbols(capsys, tmp_path, batch_files):
    tiny = tmp_path / "tiny.parquet"
    random_panel(("S0", "S1"), periods=120).to_parquet(tiny)
    panels = {"alpha": read_panel(batch_files["alpha"])}
    expected = batch_evaluate(
        namespaces=["alpha"], n_list=[5], g=3, indicator_names=["roc"], persist=False,
        data_by_namespace=panels,
    )  # fmt: skip
    code, body = run(
        capsys, "batch-screen", "--panels",
        json.dumps({"alpha": str(batch_files["alpha"]), "tiny": str(tiny)}),
        "--n-list", "5", "--groups", "3", "--indicators", "roc", "--preview", "100",
    )  # fmt: skip
    assert code == 0, body
    assert {row["namespace"] for row in body["data"]["ranking"]} == {"alpha"}
    assert body["data"]["ranking"] == json_safe(expected.to_dict(orient="records"))


def test_batch_screen_persists_per_namespace_only_with_write(capsys, tmp_path, batch_files):
    root = tmp_path / "root"
    argv = [
        "batch-screen", "--panels", json.dumps({k: str(v) for k, v in batch_files.items()}),
        "--n-list", "5", "--groups", "3", "--indicators", "roc", "--data-root", str(root),
    ]  # fmt: skip
    code, body = run(capsys, *argv)
    assert code == 0, body
    assert body["data"]["persisted"] is False and body["data"]["rows"] == 2
    assert not root.exists()
    code, body = run(capsys, *argv, "--write")
    assert code == 0, body
    assert body["data"]["persisted"] is True
    files = screen_files(root)
    for name in ("alpha", "beta"):
        assert f"factor_test/{name}/ic/roc__n5.parquet" in files
        assert f"factor_test/{name}/summary.parquet" in files
    assert not (tmp_path / "env_data").exists()


def test_batch_screen_input_errors_and_conflicts(capsys, tmp_path, batch_files):
    root = tmp_path / "root"
    panels = json.dumps({k: str(v) for k, v in batch_files.items()})
    base = ["batch-screen", "--data-root", str(root), "--indicators", "roc", "--write"]
    code, body = run(capsys, *base)  # panels is required
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--panels", "{}")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--panels", json.dumps({"a/b": str(batch_files["alpha"])}))
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--panels", panels, "--n-list", "0")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--panels", panels, "--groups", "1")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, *base, "--panels", json.dumps({"alpha": str(tmp_path / "missing.parquet")})
    )
    assert_error(code, body, "NOT_FOUND", 3)
    assert not root.exists()
    output = tmp_path / "combined.csv"
    output.write_text("keep me")
    code, body = run(capsys, *base, "--panels", panels, "--output", str(output))
    assert_error(code, body, "CONFLICT", 2)
    assert output.read_text() == "keep me" and not root.exists()


# ---------------------------------------------------------------------------
# param-sweep
# ---------------------------------------------------------------------------


def scaled_momentum(frame, period=5, scale=1.0):
    return frame["close"].pct_change(period) * scale


def panel_momentum(panel, period=5, scale=1.0):
    return panel["close"].groupby(level="symbol").pct_change(period) * scale


@pytest.fixture
def factor_module(monkeypatch):
    module = types.ModuleType("research_fake_factors")
    for function in (scaled_momentum, panel_momentum):
        setattr(module, function.__name__, function)
    monkeypatch.setitem(sys.modules, "research_fake_factors", module)
    return module


def per_symbol(func):
    def factor(panel, **kwargs):
        return Factor(func, **kwargs).calculate(panel, dropna=False)

    return factor


def test_param_sweep_indicator_equals_param_sweep(capsys, panel_file):
    from skills.compute.indicators import roc

    panel, panel_path = panel_file
    expected = param_sweep(per_symbol(roc), "period", [3, 10], n=3, data=panel)
    code, body = run(
        capsys, "param-sweep", "--panel", str(panel_path), "--indicator", "roc",
        "--param-name", "period", "--param-range", "3", "--param-range", "10", "--horizon", "3",
        "--preview", "10",
    )  # fmt: skip
    assert code == 0, body
    assert len(expected) == 2
    assert body["data"] == {"rows": json_safe(expected.to_dict(orient="records")), "failed": []}
    assert body["warnings"] == []


def test_param_sweep_decodes_flag_values_as_json(capsys, panel_file, factor_module):
    panel, panel_path = panel_file
    base = [
        "param-sweep", "--panel", str(panel_path), "--function",
        "research_fake_factors:scaled_momentum", "--param-name", "period",
    ]  # fmt: skip
    # "20" becomes the integer 20, "2.5" the float 2.5, and a non-JSON word stays a string.
    code, body = run(capsys, *base, "--param-range", "20", "--param-range", "abc", "--horizon", "3")
    assert code == 0, body
    assert [row["param_value"] for row in body["data"]["rows"]] == [20]
    assert isinstance(body["data"]["rows"][0]["param_value"], int)
    assert body["data"]["failed"] == ["abc"]
    assert any("abc" in warning for warning in body["warnings"])
    expected = param_sweep(per_symbol(scaled_momentum), "period", [20], n=3, data=panel)
    assert body["data"]["rows"] == json_safe(expected.to_dict(orient="records"))
    # A float value that the factor cannot use fails like any other bad value.
    code, body = run(capsys, *base, "--param-range", "2.5", "--param-range", "7", "--horizon", "3")
    assert code == 0, body
    assert body["data"]["failed"] == [2.5]
    assert [row["param_value"] for row in body["data"]["rows"]] == [7]
    # JSON input keeps its own types, and flag values override it.
    options = json.dumps({"param_range": [4, "5"], "param_name": "period", "horizon": 3})
    options_path = panel_path.parent / "options.json"
    options_path.write_text(options)
    code, body = run(
        capsys, "param-sweep", "--input-json", str(options_path), "--panel", str(panel_path),
        "--function", "research_fake_factors:scaled_momentum",
    )  # fmt: skip
    assert code == 0, body
    assert [row["param_value"] for row in body["data"]["rows"]] == [4, 5]


def test_param_sweep_params_feed_base_kwargs(capsys, panel_file, factor_module):
    panel, panel_path = panel_file
    base = [
        "param-sweep", "--panel", str(panel_path), "--function",
        "research_fake_factors:scaled_momentum", "--param-name", "period",
        "--param-range", "3", "--param-range", "8", "--horizon", "3", "--preview", "10",
    ]  # fmt: skip
    code, plain = run(capsys, *base)
    assert code == 0, plain
    code, flipped = run(capsys, *base, "-p", "scale=-1")
    assert code == 0, flipped
    expected = param_sweep(
        per_symbol(scaled_momentum), "period", [3, 8], n=3, base_kwargs={"scale": -1}, data=panel
    )
    assert flipped["data"]["rows"] == json_safe(expected.to_dict(orient="records"))
    # Negating the factor negates its IC.
    for before, after in zip(plain["data"]["rows"], flipped["data"]["rows"], strict=True):
        assert after["IC_mean"] == pytest.approx(-before["IC_mean"], abs=1e-3)
    code, json_params = run(capsys, *base, "--params", '{"scale": -1}')
    assert code == 0 and json_params["data"] == flipped["data"]


def test_param_sweep_panel_call_style(capsys, panel_file, factor_module):
    panel, panel_path = panel_file
    expected = param_sweep(panel_momentum, "period", [3, 8], n=2, data=panel)
    code, body = run(
        capsys, "param-sweep", "--panel", str(panel_path), "--function",
        "research_fake_factors:panel_momentum", "--call", "panel", "--param-name", "period",
        "--param-range", "3", "--param-range", "8", "--horizon", "2", "--preview", "10",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["rows"] == json_safe(expected.to_dict(orient="records"))
    # The same function called per symbol sees one symbol's frame, not the panel, and fails.
    code, body = run(
        capsys, "param-sweep", "--panel", str(panel_path), "--function",
        "research_fake_factors:panel_momentum", "--param-name", "period",
        "--param-range", "3", "--horizon", "2",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["failed"] == [3]


def test_param_sweep_reads_the_store(capsys, tmp_path):
    from skills.compute.indicators import roc

    root = tmp_path / "root"
    panel = random_panel()
    for symbol in SYMBOLS:
        write_symbol_parquet(root, symbol, panel.xs(symbol, level="symbol"))
    expected = param_sweep(per_symbol(roc), "period", [4], n=5, data=panel)
    code, body = run(
        capsys, "param-sweep", "--symbols", ",".join(SYMBOLS), "--data-root", str(root),
        "--indicator", "roc", "--param-name", "period", "--param-range", "4",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"]["rows"] == json_safe(expected.to_dict(orient="records"))


def test_the_runner_defaults_matplotlib_to_the_headless_backend(
    capsys, monkeypatch, panel_file, factor_module
):
    _, panel_path = panel_file
    monkeypatch.setenv("MPLBACKEND", "placeholder")  # restored by monkeypatch afterwards
    monkeypatch.delenv("MPLBACKEND")
    argv = [
        "param-sweep", "--panel", str(panel_path), "--function",
        "research_fake_factors:scaled_momentum", "--param-name", "period",
        "--param-range", "3", "--horizon", "3",
    ]  # fmt: skip
    code, body = run(capsys, *argv)
    assert code == 0 and body["ok"], body
    # param_sweep calls full_stat with plotting on; the runner made that headless.
    assert os.environ["MPLBACKEND"] == "Agg"
    # An explicit choice is respected.
    monkeypatch.setenv("MPLBACKEND", "svg")
    code, body = run(capsys, *argv)
    assert code == 0, body
    assert os.environ["MPLBACKEND"] == "svg"


def test_param_sweep_input_errors(capsys, panel_file, factor_module):
    panel, panel_path = panel_file
    base = [
        "param-sweep",
        "--panel",
        str(panel_path),
        "--param-name",
        "period",
        "--param-range",
        "3",
    ]
    code, body = run(capsys, *base)  # neither indicator nor function
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, *base, "--indicator", "roc", "--function", "research_fake_factors:scaled_momentum"
    )
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--indicator", "no_such_indicator")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "param-sweep", "--panel", str(panel_path), "--indicator", "roc",
        "--param-name", "period",
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)  # param-range is required
    code, body = run(
        capsys, "param-sweep", "--panel", str(panel_path), "--indicator", "roc",
        "--param-range", "3",
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)  # param-name is required
    code, body = run(capsys, *base, "--indicator", "roc", "--horizon", "0")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(capsys, *base, "--indicator", "roc", "--call", "vectorised")
    assert_error(code, body, "INVALID_INPUT", 2)
    code, body = run(
        capsys, "param-sweep", "--indicator", "roc", "--param-name", "period",
        "--param-range", "3",
    )  # fmt: skip
    assert_error(code, body, "INVALID_INPUT", 2)  # no panel source
    code, body = run(
        capsys, "param-sweep", "--panel", str(panel_path.parent / "missing.parquet"),
        "--indicator", "roc", "--param-name", "period", "--param-range", "3",
    )  # fmt: skip
    assert_error(code, body, "NOT_FOUND", 3)
    # A parameter the factor does not have makes every value fail: reported, not raised.
    code, body = run(
        capsys, "param-sweep", "--panel", str(panel_path), "--indicator", "roc",
        "--param-name", "bogus", "--param-range", "3",
    )  # fmt: skip
    assert code == 0, body
    assert body["data"] == {"rows": [], "failed": [3]}
    assert body["warnings"]
