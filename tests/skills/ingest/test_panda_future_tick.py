from __future__ import annotations

import pandas as pd

from skills.ingest.panda_future_tick import (
    build_tick_tasks,
    month_key,
    prioritize_underlyings,
    safe_symbol_name,
    split_date_ranges,
)


def test_build_tick_tasks_uses_traded_dates_and_skips_existing(tmp_path):
    daily = pd.DataFrame(
        {
            "symbol": ["SA2409.CZC", "SA2409.CZC", "SA2501.CZC"],
            "date": ["20240603", "20240604", "20240603"],
        }
    )
    existing = tmp_path / "SA2409.CZC" / "20240603.parquet"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"existing")

    tasks = build_tick_tasks(daily, tmp_path, overwrite=False)

    assert [(task.symbol, task.date) for task in tasks] == [
        ("SA2409.CZC", "20240604"),
        ("SA2501.CZC", "20240603"),
    ]


def test_safe_symbol_name_keeps_contract_readable():
    assert safe_symbol_name("SA2409.CZC") == "SA2409.CZC"


def test_prioritize_underlyings_moves_requested_symbols_to_front():
    underlyings = ["A", "AG", "FG", "IF", "SA"]

    ordered = prioritize_underlyings(underlyings, "SA,FG")

    assert ordered == ["SA", "FG", "A", "AG", "IF"]


def test_month_key_normalises_supported_date_values():
    assert month_key("20260203") == "202602"
    assert month_key("2026-02-03") == "202602"
    assert month_key(pd.Timestamp("2026-02-03 21:00:00")) == "202602"


def test_split_date_ranges_caps_long_spans():
    ranges = split_date_ranges("20200101", "20270105", max_years=5)

    assert ranges == [("20200101", "20250101"), ("20250102", "20270105")]
