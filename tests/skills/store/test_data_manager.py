from __future__ import annotations

import json

import pandas as pd

from skills.store.data_manager import DataManager, validate_ohlcv


def test_data_manager_saves_symbol_and_reads_explicit_panel(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    dates = pd.date_range("2024-01-01", periods=5, name="eob")
    bars = pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5],
            "high": [2, 3, 4, 5, 6],
            "low": [0.5, 1.5, 2.5, 3.5, 4.5],
            "close": [1.5, 2.5, 3.5, 4.5, 5.5],
            "volume": [100, 100, 100, 100, 100],
        },
        index=dates,
    )
    dm.save_symbol("SHSE.510300", bars, frequency="1d")

    panel = dm.read_symbols(["SHSE.510300"], frequency="1d")

    assert panel.index.names == ["symbol", "eob"]
    assert panel.index.get_level_values("symbol").unique().tolist() == ["SHSE.510300"]
    assert validate_ohlcv(bars).passed
    assert not (tmp_path / "pools").exists()


def test_data_manager_does_not_expose_legacy_registry_api(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    removed_names = [
        "create" + "_pool",
        "get" + "_pool_symbols",
        "get" + "_pool_frequency",
        "load" + "_pool_data",
        "check" + "_pool_coverage",
        "add" + "_to_pool",
        "remove" + "_from_pool",
        "list" + "_pools",
        "is" + "_pool_factor_fresh",
        "invalidate" + "_pool_cache",
        "compare_factor_across" + "_pools",
    ]

    assert all(not hasattr(dm, name) for name in removed_names)


def test_data_manager_reads_explicit_symbol_list_as_panel(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    dates = pd.date_range("2024-01-01", periods=3, name="eob")
    for symbol, offset in [("SHSE.510300", 0.0), ("CFFEX.IF99", 10.0)]:
        close = pd.Series([1.0, 2.0, 3.0], index=dates) + offset
        bars = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1000,
            },
            index=dates,
        )
        dm.save_symbol(symbol, bars, frequency="1d")

    panel = dm.read_symbols(["CFFEX.IF99", "SHSE.510300"], frequency="1d")

    assert panel.index.names == ["symbol", "eob"]
    assert panel.index.get_level_values("symbol").unique().tolist() == [
        "CFFEX.IF99",
        "SHSE.510300",
    ]
    assert panel.loc[("CFFEX.IF99", dates[-1]), "close"] == 13.0


def test_artifacts_are_scoped_by_namespace(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    factor = pd.DataFrame(
        {"AAA": [1.0, 2.0]},
        index=pd.date_range("2024-01-01", periods=2, name="eob"),
    )

    dm.save_factor(namespace="macro_weekly", func_name="roc", params={"n": 10}, pivot_df=factor)

    loaded = dm.read_factor(namespace="macro_weekly", func_name="roc", params={"n": 10})
    pd.testing.assert_frame_equal(loaded, factor, check_freq=False)


def test_model_metadata_uses_namespace(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    model_dir = tmp_path / "models" / "macro_weekly" / "model_1"
    model_dir.mkdir(parents=True)
    metadata = {"model_id": "model_1", "namespace": "macro_weekly", "created_at": "2026-07-22"}
    (model_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    assert dm.list_models(namespace="macro_weekly") == [metadata]
    assert dm.read_model_metadata(namespace="macro_weekly", model_id="model_1") == metadata


def test_factor_comparison_returns_namespace_column(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    for namespace, ic_ir in [("macro_weekly", 0.8), ("equity_daily", -0.6)]:
        summary_dir = tmp_path / "factor_test" / namespace
        summary_dir.mkdir(parents=True)
        pd.DataFrame(
            {
                "factor_id": ["roc__10"],
                "IC_mean": [0.02],
                "IC_IR": [ic_ir],
                "t_stat": [2.0],
                "long_short_return": [0.1],
            }
        ).to_parquet(summary_dir / "summary.parquet", index=False)

    result = dm.compare_factor_across_namespaces("roc__10")

    assert result["namespace"].tolist() == ["macro_weekly", "equity_daily"]


def test_invalidate_namespace_cache_removes_only_requested_artifacts(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    for namespace in ["macro_weekly", "equity_daily"]:
        artifact_dir = tmp_path / "factors" / namespace
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "marker.txt").write_text("ok", encoding="utf-8")

    dm.invalidate_namespace_cache("macro_weekly")

    assert not (tmp_path / "factors" / "macro_weekly").exists()
    assert (tmp_path / "factors" / "equity_daily" / "marker.txt").exists()
