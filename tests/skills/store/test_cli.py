"""qs store commands mirror DataManager and never create a store they only read."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from tests.fixtures.market_data import make_ohlcv, write_symbol_parquet


def invoke(capsys, *args):
    from skills.cli import main

    code = main(list(args))
    return code, json.loads(capsys.readouterr().out)


def bars(seed: int, periods: int = 60, start: str = "2024-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, periods)))
    return make_ohlcv(prices, start=start)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "data"
    for index, symbol in enumerate(("SHSE.510300", "SHSE.510500", "SZSE.159915")):
        write_symbol_parquet(root, symbol, bars(index))
    write_symbol_parquet(root, "SHSE.510300", bars(9), frequency="1d_adj")
    return root


def tree(path):
    return sorted(str(item.relative_to(path)) for item in path.rglob("*"))


def test_info_counts_the_inventory_without_creating_folders(root, capsys):
    (root / "adj_factor").mkdir()
    pd.DataFrame({"ex_cum_factor": [1.0]}).to_parquet(root / "adj_factor" / "SHSE.600000.parquet")
    (root / "factors" / "demo").mkdir(parents=True)
    pd.DataFrame({"a": [1.0]}).to_parquet(root / "factors" / "demo" / "f.parquet")
    before = tree(root)
    code, result = invoke(capsys, "store", "info", "--data-root", str(root))
    assert code == 0
    assert result["data"] == {
        "data_root": str(root),
        "exists": True,
        "frequencies": {"1d": 3, "1d_adj": 1},
        "adj_factors": 1,
        "namespaces": {"factors": {"demo": 1}, "backtest": {}},
    }
    assert tree(root) == before


def test_info_on_an_absent_root(tmp_path, capsys):
    code, result = invoke(capsys, "store", "info", "--data-root", str(tmp_path / "none"))
    assert code == 0 and result["data"]["exists"] is False
    assert result["data"]["frequencies"] == {} and not (tmp_path / "none").exists()


def test_list_pages_market_symbols(root, capsys):
    code, result = invoke(capsys, "store", "list", "--data-root", str(root), "--limit", "2")
    assert code == 0
    assert result["data"] == {
        "kind": "market",
        "items": ["SHSE.510300", "SHSE.510500"],
        "count": 3,
        "truncated": True,
        "next_offset": 2,
    }
    code, result = invoke(
        capsys, "store", "list", "--data-root", str(root), "--limit", "2", "--offset", "2"
    )
    assert result["data"]["items"] == ["SZSE.159915"] and result["data"]["next_offset"] is None
    code, result = invoke(capsys, "store", "list", "--data-root", str(root), "--prefix", "SHSE")
    assert result["data"]["items"] == ["SHSE.510300", "SHSE.510500"]
    code, result = invoke(
        capsys, "store", "list", "--data-root", str(root), "--frequency", "1d_adj"
    )
    assert result["data"]["items"] == ["SHSE.510300"]


def test_list_models_needs_a_namespace_and_returns_newest_first(root, capsys):
    from skills.store.data_manager import DataManager

    code, result = invoke(capsys, "store", "list", "--kind", "models", "--data-root", str(root))
    assert code == 2 and "namespace" in result["error"]["message"]
    for model_id, created in (("old", "2024-01-01T00:00:00"), ("new", "2024-06-01T00:00:00")):
        folder = root / "models" / "demo" / model_id
        folder.mkdir(parents=True)
        (folder / "metadata.json").write_text(
            json.dumps({"model_id": model_id, "created_at": created})
        )
    code, result = invoke(
        capsys, "store", "list", "--kind", "models", "--namespace", "demo", "--data-root", str(root)
    )
    expected = [meta["model_id"] for meta in DataManager(data_root=str(root)).list_models("demo")]
    assert code == 0 and result["data"]["items"] == expected == ["new", "old"]


def test_read_writes_the_same_panel_as_data_manager(root, tmp_path, capsys):
    from skills.store.data_manager import DataManager

    output = tmp_path / "out" / "panel.parquet"
    code, result = invoke(
        capsys,
        *["store", "read", "--data-root", str(root), "--symbols", "SHSE.510300,SZSE.159915"],
        *[
            "--start",
            "2024-01-10",
            "--end",
            "2024-02-05",
            "--fields",
            "close",
            "--fields",
            "volume",
        ],
        *["--output", str(output), "--preview", "1"],
    )
    assert code == 0, result
    expected = DataManager(data_root=str(root)).read_symbols(
        ["SHSE.510300", "SZSE.159915"], frequency="1d"
    )
    dates = expected.index.get_level_values("eob")
    expected = expected.loc[(dates >= "2024-01-10") & (dates <= "2024-02-05"), ["close", "volume"]]
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)
    assert result["data"]["rows"] == len(expected)
    assert result["data"]["columns"] == ["close", "volume"]
    assert len(result["data"]["preview"]) == 1
    assert result["artifacts"][0]["path"] == str(output.resolve())


def test_read_reports_missing_symbols_and_guards_outputs(root, tmp_path, capsys):
    code, result = invoke(
        capsys, "store", "read", "--data-root", str(root), "--symbols", "SHSE.510300,SHSE.999999"
    )
    assert code == 3
    assert result["error"]["code"] == "NOT_FOUND"
    assert result["error"]["details"] == ["SHSE.999999"]
    managed = root / "market" / "1d" / "copy.parquet"
    code, result = invoke(
        capsys,
        "store",
        "read",
        "--data-root",
        str(root),
        "--symbols",
        "SHSE.510300",
        "--output",
        str(managed),
    )
    assert code == 2 and "managed store namespace" in result["error"]["message"]
    assert not managed.exists()
    existing = tmp_path / "taken.parquet"
    existing.write_bytes(b"keep")
    code, result = invoke(
        capsys,
        "store",
        "read",
        "--data-root",
        str(root),
        "--symbols",
        "SHSE.510300",
        "--output",
        str(existing),
    )
    assert code == 2 and result["error"]["code"] == "CONFLICT"
    assert existing.read_bytes() == b"keep"


def _csv(path, frame):
    frame.reset_index().to_csv(path, index=False)
    return path


def test_import_is_a_dry_run_without_write(tmp_path, capsys):
    csv = _csv(tmp_path / "bars.csv", bars(1))
    store = tmp_path / "store"
    code, result = invoke(
        capsys,
        "store",
        "import",
        "--file",
        str(csv),
        "--symbol",
        "SHSE.510300",
        "--data-root",
        str(store),
    )
    assert code == 0
    assert result["data"]["dry_run"] is True and result["data"]["saved"] is False
    assert result["data"]["planned_paths"] == [
        str((store / "market" / "1d" / "SHSE.510300.parquet").resolve())
    ]
    assert not store.exists()


def test_import_single_matches_data_manager(tmp_path, capsys):
    from skills.store.data_manager import DataManager

    csv = _csv(tmp_path / "bars.csv", bars(2))
    store, reference = tmp_path / "store", tmp_path / "reference"
    code, result = invoke(
        capsys,
        "store",
        "import",
        "--file",
        str(csv),
        "--symbol",
        "SHSE.510300",
        "--data-root",
        str(store),
        "--write",
    )
    assert code == 0 and result["data"]["saved"] is True
    DataManager(data_root=str(reference)).import_symbol_csv(str(csv), "SHSE.510300")
    path = ("market", "1d", "SHSE.510300.parquet")
    pd.testing.assert_frame_equal(
        pd.read_parquet(store.joinpath(*path)), pd.read_parquet(reference.joinpath(*path))
    )
    code, result = invoke(
        capsys,
        "store",
        "import",
        "--file",
        str(csv),
        "--symbol",
        "SHSE.510300",
        "--data-root",
        str(store),
        "--write",
    )
    assert code == 2 and result["error"]["code"] == "CONFLICT"
    assert result["error"]["details"] == ["SHSE.510300"]


def test_import_combined_matches_data_manager(tmp_path, capsys):
    from skills.store.data_manager import DataManager

    frames = [bars(i).reset_index().assign(symbol=s) for i, s in enumerate(("SHSE.A1", "SZSE.B2"))]
    csv = tmp_path / "combined.csv"
    pd.concat(frames).to_csv(csv, index=False)
    store, reference = tmp_path / "store", tmp_path / "reference"
    code, result = invoke(
        capsys,
        "store",
        "import",
        "--file",
        str(csv),
        "--layout",
        "combined",
        "--data-root",
        str(store),
        "--write",
    )
    assert code == 0 and result["data"]["symbols"] == ["SHSE.A1", "SZSE.B2"]
    DataManager(data_root=str(reference)).import_combined_csv(str(csv))
    for symbol in ("SHSE.A1", "SZSE.B2"):
        path = ("market", "1d", f"{symbol}.parquet")
        pd.testing.assert_frame_equal(
            pd.read_parquet(store.joinpath(*path)), pd.read_parquet(reference.joinpath(*path))
        )


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ([], "symbol is required"),
        (["--layout", "combined", "--symbol", "X"], "single layout"),
        (["--symbol", "../escape"], "Invalid symbol"),
    ],
)
def test_import_rejects_bad_requests(tmp_path, capsys, extra, message):
    csv = _csv(tmp_path / "bars.csv", bars(3))
    code, result = invoke(capsys, "store", "import", "--file", str(csv), *extra)
    assert code == 2 and message in result["error"]["message"]


def test_validate_file_and_symbols(root, tmp_path, capsys):
    from dataclasses import asdict

    from skills.store.data_manager import DataManager, validate_ohlcv

    good = bars(4)
    good_path = tmp_path / "good.parquet"
    good.to_parquet(good_path)
    code, result = invoke(capsys, "store", "validate", "--file", str(good_path))
    assert code == 0 and result["data"] == asdict(validate_ohlcv(good))
    bad = good.copy()
    bad.iloc[3, bad.columns.get_loc("high")] = 1.0
    bad_path = tmp_path / "bad.parquet"
    bad.to_parquet(bad_path)
    code, result = invoke(capsys, "store", "validate", "--file", str(bad_path))
    assert code == 1 and result["ok"] is False
    assert result["error"]["code"] == "CHECK_FAILED"
    assert result["data"]["high_lt_low_count"] == 1
    code, result = invoke(
        capsys,
        "store",
        "validate",
        "--symbols",
        "SHSE.510300,SHSE.510500",
        "--data-root",
        str(root),
    )
    dm = DataManager(data_root=str(root))
    reports = {s: validate_ohlcv(dm.read_symbol(s, "1d")) for s in ("SHSE.510300", "SHSE.510500")}
    assert code == 0
    assert result["data"]["n_rows"] == sum(report.n_rows for report in reports.values())
    assert result["data"]["details"]["by_symbol"] == {s: asdict(r) for s, r in reports.items()}
    code, result = invoke(capsys, "store", "validate")
    assert code == 2 and "Exactly one" in result["error"]["message"]


def test_check_adjusted_matches_the_store_scan(root, tmp_path, capsys):
    from skills.store.adjusted_quality import scan_adjusted_market_data

    jumpy = bars(5)
    jumpy.iloc[20, jumpy.columns.get_loc("volume")] = 0.0
    jumpy.iloc[20:, jumpy.columns.get_loc("close")] *= 1.6
    write_symbol_parquet(root, "SHSE.510500", jumpy, frequency="1d_adj")
    output = tmp_path / "issues.parquet"
    code, result = invoke(
        capsys,
        "store",
        "check-adjusted",
        "--data-root",
        str(root),
        "--symbols",
        "SHSE.510300,SHSE.510500,SHSE.000000",
        "--output",
        str(output),
    )
    expected = scan_adjusted_market_data(
        ["SHSE.510300", "SHSE.510500", "SHSE.000000"], data_root=root
    )
    assert code == 1 and result["error"]["code"] == "CHECK_FAILED"
    assert result["data"]["issues"] == len(expected) > 0
    assert result["data"]["missing"] == ["SHSE.000000"]
    pd.testing.assert_frame_equal(pd.read_parquet(output), expected)


def test_check_adjusted_clean_data_passes(root, capsys):
    code, result = invoke(
        capsys, "store", "check-adjusted", "--data-root", str(root), "--symbols", "SHSE.510300"
    )
    assert code == 0 and result["data"]["issues"] == 0 and result["data"]["missing"] == []


def test_query_matches_data_manager(root, capsys):
    pytest.importorskip("duckdb")
    from skills.store.data_manager import DataManager

    sql = "SELECT count(*) AS n FROM read_parquet('{data}/market/1d/*.parquet') WHERE close > $1"
    code, result = invoke(
        capsys, "store", "query", "--data-root", str(root), "--sql", sql, "--params", "[100]"
    )
    expected = DataManager(data_root=str(root)).query(sql, [100])
    assert code == 0
    assert result["data"]["rows"] == 1
    assert result["data"]["preview"][0]["n"] == int(expected["n"].iloc[0])
