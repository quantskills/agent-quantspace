from __future__ import annotations

import pandas as pd

from skills.store.data_manager import DataManager, validate_ohlcv


def test_data_manager_saves_symbol_and_loads_pool(tmp_path) -> None:
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
    dm.create_pool("demo", ["SHSE.510300"], frequency="1d")

    panel = dm.load_pool_data("demo")

    assert panel.index.names == ["symbol", "eob"]
    assert panel.index.get_level_values("symbol").unique().tolist() == ["SHSE.510300"]
    assert validate_ohlcv(bars).passed


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
