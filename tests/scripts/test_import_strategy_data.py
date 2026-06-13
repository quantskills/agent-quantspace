from __future__ import annotations

from scripts.import_strategy_data import _year_chunks


def test_year_chunks_split_date_range_by_calendar_year() -> None:
    assert _year_chunks("20231215", "20250203") == [
        ("20231215", "20231231"),
        ("20240101", "20241231"),
        ("20250101", "20250203"),
    ]
