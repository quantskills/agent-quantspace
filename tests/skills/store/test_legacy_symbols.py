from __future__ import annotations

import pandas as pd
import pytest

from skills.store.data_manager import DataManager
from skills.store.legacy_symbols import (
    apply_symbol_migration,
    legacy_to_panda_data,
    plan_symbol_migration,
)


@pytest.mark.parametrize(
    ("legacy", "native"),
    [
        ("SHSE.510300", "510300.SH"),
        ("SZSE.159915", "159915.SZ"),
        ("SHSE.000300", "000300.SH"),
        ("SHFE.RB99", "RB_DOMINANT.SHF"),
        ("CFFEX.IF99", "IF_DOMINANT.CFE"),
        ("CZCE.MA99", "MA_DOMINANT.CZC"),
        ("DCE.I99", "I_DOMINANT.DCE"),
        ("INE.SC99", "SC_DOMINANT.INE"),
        ("GFEX.SI99", "SI_DOMINANT.GFE"),
        ("SHFE.RB2601", "RB2601.SHF"),
        ("CZCE.CF509", "CF509.CZC"),
        ("HKEX.00700", "00700.HK"),
        ("NASDAQ.AAPL", "AAPL.NB"),
    ],
)
def test_legacy_symbols_map_to_panda_data_codes(legacy, native) -> None:
    assert legacy_to_panda_data(legacy) == native


@pytest.mark.parametrize(
    "symbol", ["510300.SH", "RB_DOMINANT.SHF", "932365.CSI", "000001.OF", "AAPL", "SHSE.", "XYZ.1"]
)
def test_non_legacy_names_are_left_alone(symbol) -> None:
    assert legacy_to_panda_data(symbol) is None


def _bars(value: float) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=2, name="eob")
    return pd.DataFrame(
        {c: [value, value] for c in ["open", "high", "low", "close", "volume"]}, index=index
    )


def test_migration_renames_market_and_adj_files_and_is_idempotent(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    dm.save_symbol("SHSE.510300", _bars(1.0), frequency="1d")
    dm.save_symbol("SHSE.510300", _bars(2.0), frequency="1d_adj")
    dm.save_symbol("SHFE.RB99", _bars(3.0), frequency="1m")
    dm.save_symbol("932365.CSI", _bars(4.0), frequency="1d")
    dm.save_adj_factor("SHSE.600000", _bars(5.0))

    plan = plan_symbol_migration(tmp_path)
    assert sorted((p.source.parent.name, p.source.stem, p.target.stem) for p in plan) == [
        ("1d", "SHSE.510300", "510300.SH"),
        ("1d_adj", "SHSE.510300", "510300.SH"),
        ("1m", "SHFE.RB99", "RB_DOMINANT.SHF"),
        ("adj_factor", "SHSE.600000", "600000.SH"),
    ]
    assert not any(p.conflict for p in plan)
    assert len(apply_symbol_migration(plan)) == 4

    assert dm.list_symbols("1d") == ["510300.SH", "932365.CSI"]
    assert dm.read_symbol("510300.SH", "1d_adj")["close"].iloc[0] == 2.0
    assert dm.list_symbols("1m") == ["RB_DOMINANT.SHF"]
    assert dm.list_adj_factors() == ["600000.SH"]
    assert plan_symbol_migration(tmp_path) == []


def test_migration_never_overwrites_an_existing_target(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    dm.save_symbol("SHSE.510300", _bars(1.0), frequency="1d")
    dm.save_symbol("510300.SH", _bars(9.0), frequency="1d")

    plan = plan_symbol_migration(tmp_path)
    assert [p.conflict for p in plan] == [True]
    assert apply_symbol_migration(plan) == []
    assert dm.list_symbols("1d") == ["510300.SH", "SHSE.510300"]
    assert dm.read_symbol("510300.SH")["close"].iloc[0] == 9.0


def test_missing_reads_point_to_the_migration_command(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    dm.save_symbol("SHSE.510300", _bars(1.0), frequency="1d")
    dm.save_adj_factor("SHSE.600000", _bars(1.0))
    for read in (
        lambda: dm.read_symbol("510300.SH"),
        lambda: dm.read_symbols(["510300.SH"]),
        lambda: dm.read_adj_factor("600000.SH"),
    ):
        with pytest.raises(FileNotFoundError, match="qs store migrate-symbols --write"):
            read()


def test_missing_reads_without_legacy_files_carry_no_hint(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    dm.save_symbol("159915.SZ", _bars(1.0), frequency="1d")
    with pytest.raises(FileNotFoundError) as error:
        dm.read_symbol("510300.SH")
    assert "migrate-symbols" not in str(error.value)
