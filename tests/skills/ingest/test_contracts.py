"""Offline tests for ``qs ingest contracts``: the dominant table and each contract's bars."""

from __future__ import annotations

import json
import sys

import pandas as pd
import pytest

from skills.cli import main
from skills.ingest.cli import contract_ranges
from skills.store.data_manager import DataManager
from tests.skills.ingest.test_cli import FakeSDK

DOMINANT = pd.DataFrame(
    {
        "date": ["20250827", "20250828", "20250829", "20250901", "20250902"],
        "underlying_symbol": ["RB"] * 5,
        "symbol": ["RB2510.SHF", "RB2510.SHF", "RB2601.SHF", "RB2601.SHF", "RB2601.SHF"],
        "trading_code": ["rb2510", "rb2510", "rb2601", "rb2601", "rb2601"],
    }
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PANDA_DATA_USERNAME", "fake-user")
    monkeypatch.setenv("PANDA_DATA_PASSWORD", "fake-password")
    monkeypatch.delenv("QUANTSPACE_DATA_ROOT", raising=False)


def daily(kwargs):
    symbol = kwargs["symbol"]
    days = pd.bdate_range(kwargs["start_date"], kwargs["end_date"])
    base = 3000.0 if symbol == "RB2510.SHF" else 3100.0
    return pd.DataFrame(
        {
            "symbol": symbol,
            "date": days.strftime("%Y%m%d"),
            "open": base,
            "high": base + 5,
            "low": base - 5,
            "close": base + 1,
            "volume": 10.0,
        }
    )


def minute(kwargs):
    symbol = kwargs["symbol"]
    return pd.DataFrame(
        {
            "symbol": symbol,
            "datetime": [
                f"{kwargs['start_date'][:4]}-{kwargs['start_date'][4:6]}-"
                f"{kwargs['start_date'][6:]} 09:01:00"
            ],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
        }
    )


@pytest.fixture
def sdk(monkeypatch):
    fake = FakeSDK()
    fake.responses["get_future_daily"] = daily
    fake.responses["get_future_min"] = minute

    def dominant(**kwargs):
        fake.calls.append(("get_future_dominant", kwargs))
        return DOMINANT

    fake.get_future_dominant = dominant
    monkeypatch.setitem(sys.modules, "panda_data", fake)
    return fake


def run(capsys, *argv):
    code = main(["ingest", "contracts", *argv])
    return code, json.loads(capsys.readouterr().out)


def test_each_run_is_needed_through_the_roll_day():
    days = {"20250829": "B", "20250827": "A", "20250828": "A", "20250901": "B", "20250902": "A"}
    assert contract_ranges(days) == [
        ("A", "20250827", "20250829"),
        ("B", "20250829", "20250902"),
        ("A", "20250902", "20250902"),
    ]


def test_dry_run_reports_the_plan_and_stores_nothing(capsys, sdk, tmp_path):
    code, response = run(
        capsys,
        "--underlyings",
        "rb",
        "--start",
        "2025-08-27",
        "--end",
        "2025-09-02",
        "--data-root",
        str(tmp_path / "data"),
    )
    assert code == 0, response
    data = response["data"]
    assert data["dry_run"] is True and data["days"] == 5
    assert data["ranges"] == [
        {
            "continuous": "RB_DOMINANT.SHF",
            "contract": "RB2510.SHF",
            "first": "20250827",
            "last": "20250829",
        },
        {
            "continuous": "RB_DOMINANT.SHF",
            "contract": "RB2601.SHF",
            "first": "20250829",
            "last": "20250902",
        },
    ]
    assert [name for name, _ in sdk.sdk_calls()] == ["get_future_dominant"]
    assert not (tmp_path / "data" / "market" / "dominant").exists()


def test_write_stores_the_dominant_table_and_bars_through_the_roll_day(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    code, response = run(
        capsys,
        "--underlyings",
        "RB",
        "--start",
        "20250827",
        "--end",
        "20250902",
        "--freq",
        "1d,1m",
        "--write",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    dm = DataManager(str(root))
    table = dm.read_dominant(["RB_DOMINANT.SHF"])
    assert table["RB_DOMINANT.SHF"].to_dict() == {
        pd.Timestamp(day): contract for day, contract in zip(DOMINANT["date"], DOMINANT["symbol"])
    }
    old = dm.read_symbol("RB2510.SHF", "1d")
    # The old contract is kept through the roll day 08-29, when the position is closed.
    assert old.index.max() == pd.Timestamp("2025-08-29")
    assert list(old.columns) == ["open", "high", "low", "close", "volume"]
    new = dm.read_symbol("RB2601.SHF", "1d")
    assert new.index.min() == pd.Timestamp("2025-08-29")
    assert response["data"]["rows"]["1m/RB2510.SHF"] == 1
    assert dm.read_symbol("RB2601.SHF", "1m").index[0] == pd.Timestamp("2025-08-29 09:01")


def test_minute_ranges_are_requested_in_pieces(capsys, sdk, tmp_path):
    long = DOMINANT.assign(date=["20250101", "20250201", "20250301", "20250401", "20250501"])
    long["symbol"] = "RB2510.SHF"
    sdk.get_future_dominant = lambda **kwargs: long
    code, response = run(
        capsys,
        "--underlyings",
        "RB",
        "--start",
        "20250101",
        "--end",
        "20250501",
        "--freq",
        "1m",
        "--write",
        "--data-root",
        str(tmp_path / "data"),
    )
    assert code == 0, response
    pieces = [kwargs for name, kwargs in sdk.sdk_calls() if name == "get_future_min"]
    assert len(pieces) == 7
    assert all(
        (pd.Timestamp(item["end_date"]) - pd.Timestamp(item["start_date"])).days < 20
        for item in pieces
    )


def test_rerun_merges_with_stored_days(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    args = ("--underlyings", "RB", "--write", "--data-root", str(root))
    assert run(capsys, *args, "--start", "20250827", "--end", "20250828")[0] == 0
    assert run(capsys, *args, "--start", "20250829", "--end", "20250902")[0] == 0
    table = DataManager(str(root)).read_dominant(["RB_DOMINANT.SHF"])
    assert len(table) == 5


def test_unknown_freq_is_refused(capsys, sdk):
    code, response = run(capsys, "--underlyings", "RB", "--start", "20250827", "--freq", "2m")
    assert code != 0 and "--freq" in response["error"]["message"]
