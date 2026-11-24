"""Whole-file replacement: retried while Windows holds the target, never half written."""

from __future__ import annotations

import sys
import threading
import time

import pandas as pd
import pytest

from skills.store.data_manager import DataManager
from skills.store.files import replace_file, write_parquet_atomic


def _refusing_replace(monkeypatch, refusals: int) -> list[int]:
    """Make ``os.replace`` fail like a held file ``refusals`` times; returns the counter."""
    import skills.store.files as module

    real, left = module.os.replace, [refusals]

    def replace(src, dst):
        if left[0]:
            left[0] -= 1
            raise PermissionError(13, "The process cannot access the file")
        real(src, dst)

    monkeypatch.setattr(module.os, "replace", replace)
    return left


def test_replace_is_retried_while_the_target_is_in_use(tmp_path, monkeypatch):
    source, target = tmp_path / "new.json", tmp_path / "state.json"
    source.write_text("new", encoding="utf-8"), target.write_text("old", encoding="utf-8")
    left, waits = _refusing_replace(monkeypatch, 2), []
    replace_file(source, target, sleep=waits.append)
    assert (target.read_text(encoding="utf-8"), waits) == ("new", [0.1, 0.1])

    source.write_text("newer", encoding="utf-8")
    left[0] = 99
    with pytest.raises(PermissionError):
        replace_file(source, target, retries=3, sleep=waits.append)
    assert target.read_text(encoding="utf-8") == "new" and len(waits) == 5


def _bars(close: float) -> pd.DataFrame:
    index = pd.DatetimeIndex(["2026-11-23", "2026-11-24"], name="eob")
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close}, index=index)


def test_save_symbol_replaces_the_file_whole(tmp_path, monkeypatch):
    manager = DataManager(tmp_path, create_layout=False)
    manager.save_symbol("RB2701.SHF", _bars(3000.0))
    path = tmp_path / "market" / "1d" / "RB2701.SHF.parquet"
    _refusing_replace(monkeypatch, 2)
    manager.save_symbol("RB2701.SHF", _bars(3100.0))
    assert pd.read_parquet(path)["close"].tolist() == [3100.0, 3100.0]
    assert [item.name for item in path.parent.iterdir()] == ["RB2701.SHF.parquet"]


def test_a_failed_write_keeps_the_old_file_and_no_temporary(tmp_path, monkeypatch):
    path = write_parquet_atomic(_bars(3000.0), tmp_path / "bars.parquet")

    def broken(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", broken)
    with pytest.raises(OSError, match="disk full"):
        write_parquet_atomic(_bars(3100.0), path)
    monkeypatch.undo()
    assert pd.read_parquet(path)["close"].tolist() == [3000.0, 3000.0]
    assert [item.name for item in tmp_path.iterdir()] == ["bars.parquet"]


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses to replace an open file")
def test_a_parquet_file_held_open_by_a_reader_is_replaced_once_released(tmp_path):
    path = write_parquet_atomic(_bars(3000.0), tmp_path / "bars.parquet")
    stream = path.open("rb")
    threading.Timer(0.3, stream.close).start()
    started = time.monotonic()
    write_parquet_atomic(_bars(3100.0), path)
    assert time.monotonic() - started >= 0.2
    assert pd.read_parquet(path)["close"].tolist() == [3100.0, 3100.0]
