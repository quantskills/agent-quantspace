from __future__ import annotations

from datetime import date

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
        ("CZCE.CF2509", "CF2509.CZC"),
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


@pytest.mark.parametrize(
    ("legacy", "as_of", "native"),
    [
        ("CZCE.CF509", date(2025, 9, 12), "CF2509.CZC"),  # last bar in the delivery month
        ("CZCE.CF509", date(2024, 9, 13), "CF2509.CZC"),  # listed a year before delivery
        ("CZCE.CF009", date(2020, 9, 14), "CF2009.CZC"),  # more than five years back
        ("CZCE.CF001", date(2019, 12, 31), "CF2001.CZC"),  # delivery in the next decade
        ("CZCE.SR101", date(2029, 6, 1), "SR3101.CZC"),
        ("CZCE.CF2509", date(2031, 1, 1), "CF2509.CZC"),  # four digits never change
    ],
)
def test_zhengzhou_three_digit_contracts_get_a_four_digit_year_month(legacy, as_of, native) -> None:
    assert legacy_to_panda_data(legacy, as_of=as_of) == native


def _bars(value: float, start: str = "2024-01-01") -> pd.DataFrame:
    index = pd.date_range(start, periods=2, name="eob")
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


def test_migration_dates_zhengzhou_contracts_by_their_last_bar(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    dm.save_symbol("CZCE.CF509", _bars(1.0, "2015-09-14"), frequency="1d")
    dm.save_symbol("CZCE.CF509", _bars(2.0, "2025-09-12"), frequency="1m")
    dm.save_symbol("CZCE.SR101", _bars(3.0).iloc[:0], frequency="5m")

    plan = plan_symbol_migration(tmp_path)
    assert sorted((p.source.parent.name, p.target.stem) for p in plan) == [
        ("1d", "CF1509.CZC"),
        ("1m", "CF2509.CZC"),
        # No bars to date it: today's decade, as for a bare symbol.
        ("5m", legacy_to_panda_data("CZCE.SR101")),
    ]
    assert len(apply_symbol_migration(plan)) == 3
    assert dm.read_symbol("CF1509.CZC", "1d")["close"].iloc[0] == 1.0
    assert plan_symbol_migration(tmp_path) == []


def test_migration_keeps_the_second_file_mapping_to_the_same_code(tmp_path) -> None:
    dm = DataManager(data_root=str(tmp_path))
    dm.save_symbol("CZCE.CF2509", _bars(1.0, "2025-09-12"), frequency="1d")
    dm.save_symbol("CZCE.CF509", _bars(2.0, "2025-09-12"), frequency="1d")

    plan = plan_symbol_migration(tmp_path)
    assert [(p.source.stem, p.target.stem, p.conflict) for p in plan] == [
        ("CZCE.CF2509", "CF2509.CZC", False),
        ("CZCE.CF509", "CF2509.CZC", True),
    ]
    assert [p.source.stem for p in apply_symbol_migration(plan)] == ["CZCE.CF2509"]
    assert dm.list_symbols("1d") == ["CF2509.CZC", "CZCE.CF509"]
    assert dm.read_symbol("CF2509.CZC")["close"].iloc[0] == 1.0


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
