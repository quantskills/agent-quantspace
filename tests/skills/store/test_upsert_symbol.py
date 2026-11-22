"""``DataManager.upsert_symbol``: merge by eob, report rewritten bars, trim, write atomically."""

from __future__ import annotations

import pandas as pd
import pytest

from skills.store.data_manager import DataManager


def bars(times, close, source="pandadata", volume=None):
    index = pd.DatetimeIndex(pd.to_datetime(times), name="eob")
    return pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": volume if volume is not None else [100.0] * len(times),
            "source": source,
        },
        index=index,
    )


def test_first_write_creates_the_file_without_research_folders(tmp_path):
    dm = DataManager(tmp_path / "live", create_layout=False)
    report = dm.upsert_symbol(
        "RB2701.SHF", bars(["2026-11-20 14:55", "2026-11-20 15:00"], [1.0, 2.0]), "5m"
    )
    assert (report.added, report.replaced, report.dropped, report.rows) == (2, 0, 0, 2)
    assert report.changed.empty
    assert report.path == tmp_path / "live" / "market" / "5m" / "RB2701.SHF.parquet"
    assert sorted(p.name for p in (tmp_path / "live").iterdir()) == ["market"]
    stored = dm.read_symbol("RB2701.SHF", "5m")
    assert stored.index.name == "eob" and stored["source"].tolist() == ["pandadata"] * 2


def test_incoming_bars_replace_overlaps_and_report_changed_values(tmp_path):
    dm = DataManager(tmp_path, create_layout=False)
    dm.upsert_symbol("RB2701.SHF", bars(["09:05", "09:10", "09:15"], [1.0, 2.0, 3.0]), "5m")
    report = dm.upsert_symbol(
        "RB2701.SHF",
        bars(["09:10", "09:15", "09:20"], [2.0, 3.5, 4.0], source="akshare_sina"),
        "5m",
    )
    assert (report.added, report.replaced, report.rows) == (1, 2, 4)
    changed = report.changed
    assert set(changed["column"]) == {"open", "high", "low", "close"}
    assert (changed["eob"] == pd.Timestamp("09:15")).all()
    assert changed.loc[changed["column"] == "close", ["stored", "incoming"]].iloc[0].tolist() == [
        3.0,
        3.5,
    ]
    stored = dm.read_symbol("RB2701.SHF", "5m")
    assert stored["close"].tolist() == [1.0, 2.0, 3.5, 4.0]
    assert stored["source"].tolist() == ["pandadata", "akshare_sina", "akshare_sina", "akshare_sina"]


def test_tolerance_and_missing_values(tmp_path):
    dm = DataManager(tmp_path, create_layout=False)
    dm.upsert_symbol("X.SH", bars(["2026-11-20"], [10.0], volume=[float("nan")]), "1d")
    report = dm.upsert_symbol(
        "X.SH", bars(["2026-11-20"], [10.004], volume=[5.0]), "1d", tolerance=0.01
    )
    assert report.changed["column"].tolist() == ["volume"]


def test_keep_last_trims_the_oldest_bars(tmp_path):
    dm = DataManager(tmp_path, create_layout=False)
    report = dm.upsert_symbol(
        "X.SH", bars(["09:31", "09:32", "09:33", "09:34"], [1.0, 2.0, 3.0, 4.0]), "1m", keep_last=3
    )
    assert (report.dropped, report.rows) == (1, 3)
    assert dm.read_symbol("X.SH", "1m")["close"].tolist() == [2.0, 3.0, 4.0]
    with pytest.raises(ValueError):
        dm.upsert_symbol("X.SH", bars(["09:35"], [5.0]), "1m", keep_last=0)


def test_eob_column_input_and_refusals(tmp_path):
    dm = DataManager(tmp_path, create_layout=False)
    frame = bars(["09:31", "09:32"], [1.0, 2.0]).reset_index()
    assert dm.upsert_symbol("X.SH", frame, "1m").rows == 2
    duplicated = bars(["09:33", "09:33"], [1.0, 2.0])
    with pytest.raises(ValueError, match="duplicate"):
        dm.upsert_symbol("X.SH", duplicated, "1m")
    aware = bars(["09:34"], [1.0])
    aware.index = aware.index.tz_localize("Asia/Shanghai")
    with pytest.raises(ValueError, match="timezone-naive"):
        dm.upsert_symbol("X.SH", aware, "1m")
    assert dm.read_symbol("X.SH", "1m")["close"].tolist() == [1.0, 2.0]
    assert [p.name for p in (tmp_path / "market" / "1m").iterdir()] == ["X.SH.parquet"]
