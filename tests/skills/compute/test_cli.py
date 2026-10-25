"""qs compute commands write exactly what the compute APIs return."""

from __future__ import annotations

import json
import textwrap

import numpy as np
import pandas as pd
import pytest

from tests.fixtures.market_data import make_ohlcv, write_symbol_parquet

SYMBOLS = ("SHSE.510300", "SHSE.510500", "SZSE.159915")


def invoke(capsys, *args):
    from skills.cli import main

    code = main(list(args))
    return code, json.loads(capsys.readouterr().out)


def walk(seed: int, periods: int = 120) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, periods)))


@pytest.fixture
def panel():
    return pd.concat(
        [make_ohlcv(walk(index), symbol=symbol) for index, symbol in enumerate(SYMBOLS)]
    ).sort_index()


@pytest.fixture
def panel_path(tmp_path, panel):
    path = tmp_path / "panel.parquet"
    panel.to_parquet(path)
    return path


def test_indicators_list_and_show_mirror_discovery(capsys):
    import inspect

    from skills.compute.indicators import discover_indicators

    registry = discover_indicators()
    code, result = invoke(capsys, "compute", "indicators", "list")
    assert code == 0
    assert [item["name"] for item in result["data"]["indicators"]] == sorted(registry)
    code, result = invoke(capsys, "compute", "indicators", "show", "roc")
    assert code == 0
    assert result["data"]["name"] == "roc"
    assert result["data"]["signature"] == str(inspect.signature(registry["roc"]))
    code, result = invoke(capsys, "compute", "indicators", "show", "no_such_indicator")
    assert code == 2 and "indicators list" in result["error"]["hint"]


@pytest.mark.parametrize("keep_na", [False, True])
def test_factor_long_layout_matches_factor_wrapper(panel, panel_path, tmp_path, capsys, keep_na):
    from skills.compute.indicators import discover_indicators
    from skills.compute.wrappers import Factor

    output = tmp_path / "factor.parquet"
    code, result = invoke(
        capsys,
        *["compute", "factor", "--panel", str(panel_path), "--indicator", "roc", "-p", "period=5"],
        *["--output", str(output), *(["--keep-na"] if keep_na else [])],
    )
    assert code == 0, result
    wrapper = Factor(discover_indicators()["roc"], period=5)
    expected = wrapper.calculate(panel, dropna=not keep_na).rename("value").reset_index()
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)
    assert result["data"]["name"] == wrapper.name
    assert result["data"]["rows"] == len(expected)
    assert result["data"]["symbols"] == sorted(SYMBOLS)


def test_factor_wide_layout_and_function_reference(panel, panel_path, tmp_path, capsys):
    from skills.compute.indicators import discover_indicators
    from skills.compute.wrappers import Factor

    output = tmp_path / "wide.parquet"
    code, result = invoke(
        capsys,
        *["compute", "factor", "--panel", str(panel_path)],
        *["--function", "skills.compute.indicators:roc", "--params", '{"period": 10}'],
        *["--layout", "wide", "--output", str(output)],
    )
    assert code == 0, result
    expected = (
        Factor(discover_indicators()["roc"], period=10)
        .calculate(panel, dropna=True)
        .rename("value")
        .unstack("symbol")
        .sort_index()
    )
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)


def test_factor_panel_call_mode(panel, panel_path, tmp_path, capsys, monkeypatch):
    module = tmp_path / "panel_factors.py"
    module.write_text(
        textwrap.dedent(
            """
            def spread(panel, window=3):
                return panel["close"].groupby(level="symbol").diff(window)

            def broken(panel):
                return panel["close"].iloc[:5]
            """
        )
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    output = tmp_path / "spread.parquet"
    code, result = invoke(
        capsys,
        "compute",
        "factor",
        "--panel",
        str(panel_path),
        "--call",
        "panel",
        "--function",
        "panel_factors:spread",
        "-p",
        "window=2",
        "--output",
        str(output),
    )
    assert code == 0, result
    expected = panel["close"].groupby(level="symbol").diff(2).astype("float64").dropna()
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected.rename("value").reset_index())
    code, result = invoke(
        capsys,
        "compute",
        "factor",
        "--panel",
        str(panel_path),
        "--call",
        "panel",
        "--function",
        "panel_factors:broken",
        "--output",
        str(tmp_path / "broken.parquet"),
    )
    assert code == 2 and "aligned to the panel" in result["error"]["message"]
    assert not (tmp_path / "broken.parquet").exists()


def test_factor_needs_exactly_one_source(panel_path, tmp_path, capsys):
    code, result = invoke(
        capsys,
        "compute",
        "factor",
        "--panel",
        str(panel_path),
        "--indicator",
        "roc",
        "--function",
        "skills.compute.indicators:roc",
        "--output",
        str(tmp_path / "x.parquet"),
    )
    assert code == 2 and "Exactly one" in json.dumps(result["error"])


def test_features_match_make_logdiff_panel_features(panel, panel_path, tmp_path, capsys):
    from skills.compute.features import make_logdiff_panel_features

    output = tmp_path / "features.parquet"
    code, result = invoke(
        capsys,
        *["compute", "features", "--panel", str(panel_path), "--lags", "1", "--lags", "5"],
        *["--shifts", "[0, 1]", "--output", str(output)],
    )
    assert code == 0, result
    expected = make_logdiff_panel_features(panel, lags=[1, 5], shifts=[0, 1])
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)
    assert result["data"]["features"] == expected.shape[1]
    assert result["artifacts"][0]["columns"] == []


def test_forward_return_labels_match_label_maker(tmp_path, capsys):
    from skills.compute.label_maker import ForwardReturnLabelMaker

    bars = make_ohlcv(walk(3))
    source, output = tmp_path / "bars.parquet", tmp_path / "labels.parquet"
    bars.to_parquet(source)
    code, result = invoke(
        capsys,
        "compute",
        "labels",
        "forward-return",
        "--bars",
        str(source),
        "--horizon",
        "3",
        "--up-threshold",
        "0.01",
        "--down-threshold",
        "0.01",
        "--output",
        str(output),
    )
    assert code == 0, result
    expected = ForwardReturnLabelMaker(
        data=bars, horizon=3, up_threshold=0.01, down_threshold=0.01
    ).generate_labels()
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected, check_freq=False)


def test_triple_barrier_labels_match_label_maker(tmp_path, capsys):
    from skills.compute.label_maker import TripleBarrierLabelMaker

    bars = make_ohlcv(walk(4))
    source, output = tmp_path / "bars.csv", tmp_path / "labels.parquet"
    bars.reset_index().to_csv(source, index=False)
    code, result = invoke(
        capsys,
        "compute",
        "labels",
        "triple-barrier",
        "--bars",
        str(source),
        "--lookback",
        "7",
        "--pt-sl",
        "1.5",
        "--t-limit",
        "8",
        "--output",
        str(output),
    )
    assert code == 0, result
    expected = TripleBarrierLabelMaker(data=bars, L=7, pt_sl=1.5, t_limit=8).generate_labels()
    pd.testing.assert_frame_equal(
        pd.read_parquet(output), expected, check_freq=False, check_index_type=False
    )


def test_resample_matches_resample_to_5m(tmp_path, capsys):
    from skills.compute.resample import resample_to_5m

    minutes = pd.date_range("2024-01-02 09:31", "2024-01-02 11:30", freq="1min").append(
        pd.date_range("2024-01-02 13:01", "2024-01-02 15:00", freq="1min")
    )
    bars = make_ohlcv(walk(5, len(minutes)))
    bars.index = minutes.rename("eob")
    source, output = tmp_path / "1m.parquet", tmp_path / "5m.parquet"
    bars.to_parquet(source)
    code, result = invoke(
        capsys, "compute", "resample", "--input", str(source), "--output", str(output)
    )
    assert code == 0, result
    expected = resample_to_5m(bars)
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected, check_freq=False)
    assert result["data"]["rows"] == 48


@pytest.fixture
def raw_store(tmp_path):
    root = tmp_path / "data"
    for index, symbol in enumerate(("SHSE.600000", "SHSE.600036")):
        write_symbol_parquet(root, symbol, make_ohlcv(walk(index, 40)))
    (root / "adj_factor").mkdir()
    pd.DataFrame(
        {"ex_cum_factor": [1.5], "ex_factor": [1.5]},
        index=pd.DatetimeIndex(["2024-01-20"], name="ex_date"),
    ).to_parquet(root / "adj_factor" / "SHSE.600000.parquet")
    return root


def test_adjust_dry_run_writes_nothing(raw_store, capsys):
    before = sorted(str(path) for path in raw_store.rglob("*"))
    code, result = invoke(
        capsys,
        "compute",
        "adjust",
        "--symbols",
        "SHSE.600000,SHSE.600036",
        "--data-root",
        str(raw_store),
    )
    assert code == 0
    assert result["data"]["dry_run"] is True and result["data"]["target_frequency"] == "1d_adj"
    assert result["data"]["unadjusted"] == ["SHSE.600036"]
    assert result["warnings"] and "SHSE.600036" in result["warnings"][0]
    assert sorted(str(path) for path in raw_store.rglob("*")) == before


def test_adjust_output_and_write_match_load_adjusted(raw_store, tmp_path, capsys):
    from skills.compute.adjust import load_adjusted

    output = tmp_path / "adjusted.parquet"
    code, result = invoke(
        capsys,
        "compute",
        "adjust",
        "--symbols",
        "SHSE.600000",
        "--data-root",
        str(raw_store),
        "--output",
        str(output),
    )
    assert code == 0, result
    expected = load_adjusted("SHSE.600000", data_root=str(raw_store))
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)
    code, result = invoke(
        capsys,
        "compute",
        "adjust",
        "--symbols",
        "SHSE.600000,SHSE.600036",
        "--data-root",
        str(raw_store),
        "--write",
    )
    assert code == 0 and result["data"]["saved"] is True
    for symbol in ("SHSE.600000", "SHSE.600036"):
        stored = pd.read_parquet(raw_store / "market" / "1d_adj" / f"{symbol}.parquet")
        pd.testing.assert_frame_equal(
            stored, load_adjusted(symbol, data_root=str(raw_store)), check_freq=False
        )
    code, result = invoke(
        capsys,
        "compute",
        "adjust",
        "--symbols",
        "SHSE.600000",
        "--data-root",
        str(raw_store),
        "--write",
    )
    assert code == 2 and result["error"]["code"] == "CONFLICT"


@pytest.mark.parametrize(
    ("extra", "code", "message"),
    [
        (["--symbols", "SHSE.000001"], 3, "Missing 1d raw bars"),
        (["--symbols", "SHSE.600000,SHSE.600036", "--output", "OUT"], 2, "exactly one symbol"),
        (["--symbols", "SHSE.600000", "--output", "OUT", "--write"], 2, "not both"),
    ],
)
def test_adjust_rejects_bad_requests(raw_store, tmp_path, capsys, extra, code, message):
    extra = [str(tmp_path / "out.parquet") if item == "OUT" else item for item in extra]
    status, result = invoke(capsys, "compute", "adjust", "--data-root", str(raw_store), *extra)
    assert status == code and message in result["error"]["message"]
