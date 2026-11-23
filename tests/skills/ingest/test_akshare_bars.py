"""Offline tests for AKShare intraday bars: code mapping, cleaning, and the CLI command.

A fake ``akshare`` module replaces the real one, so nothing reaches Sina.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime

import pandas as pd
import pytest

from skills.cli import main
from skills.ingest.akshare_bars import COLUMNS, SOURCE, fetch_intraday_bars, sina_code

NOW = datetime(2026, 11, 21, 10, 0, 30)  # Saturday: Monday's bars have not started


class FakeAkshare:
    """Stock pages return strings; futures pages carry ``hold`` and a next-session placeholder."""

    def __init__(self, failing=()):
        self.calls = []
        self.failing = set(failing)

    def stock_zh_a_hist_min_sina(self, symbol, period, adjust):
        self.calls.append(("stock", symbol, period, adjust))
        if symbol in self.failing:
            raise ConnectionError("Sina closed the connection")
        return pd.DataFrame(
            {
                "day": ["2026-11-20 14:55:00", "2026-11-20 15:00:00", "2026-11-20 15:00:00"],
                "open": ["12.200", "12.220", "12.220"],
                "high": ["12.240", "12.250", "12.250"],
                "low": ["12.190", "12.210", "12.210"],
                "close": ["12.220", "12.220", "12.220"],
                "volume": ["15625605", "8267800", "8267800"],
                "amount": ["190919798.4895", "101125060.9240", "101125060.9240"],
            }
        )

    def futures_zh_min_sina(self, symbol, period):
        self.calls.append(("future", symbol, period))
        if symbol in self.failing:
            raise KeyError("None of ['datetime'] are in the columns")
        return pd.DataFrame(
            {
                "datetime": [
                    "2026-11-20 22:55:00",
                    "2026-11-20 23:00:00",
                    "2026-11-23 09:05:00",  # placeholder written after the night session
                    "2026-11-23 09:10:00",
                ],
                "open": [2997.0, 2995.0, 2997.0, 2996.0],
                "high": [2998.0, 2998.0, 2997.0, 2999.0],
                "low": [2995.0, 2995.0, 2997.0, 2995.0],
                "close": [2995.0, 2997.0, 2997.0, 2998.0],
                "volume": [1921, 47, 3, 900],
                "hold": [1488467, 1484538, 1484536, 1484000],
            }
        )


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("000001.SZ", ("stock", "sz000001")),
        ("600000.SH", ("stock", "sh600000")),
        ("510300.SH", ("stock", "sh510300")),
        ("920000.BJ", ("stock", "bj920000")),
        ("000300.SH", ("stock", "sh000300")),
        ("RB2701.SHF", ("future", "RB2701")),
        ("m2701.DCE", ("future", "M2701")),
        ("IF2612.CFE", ("future", "IF2612")),
        ("CF2701.CZC", ("future", "CF2701")),
        ("CF701.CZC", ("future", "CF2701")),
        ("SA609.CZC", ("future", "SA2609")),
    ],
)
def test_sina_codes(symbol, expected):
    assert sina_code(symbol, today=date(2026, 11, 22)) == expected


def test_zhengzhou_year_digit_resolves_to_the_nearest_decade():
    assert sina_code("CF001.CZC", today=date(2026, 11, 22)) == ("future", "CF3001")
    assert sina_code("CF209.CZC", today=date(2026, 11, 22)) == ("future", "CF2209")
    assert sina_code("CF001.CZC", today=date(2029, 6, 1)) == ("future", "CF3001")


@pytest.mark.parametrize(
    "symbol",
    ["RB_DOMINANT.SHF", "0700.HK", "AAPL.NB", "RB701.SHF", "60000.SH", "nonsense"],
)
def test_sina_code_refuses_what_sina_minute_pages_cannot_serve(symbol):
    with pytest.raises(ValueError):
        sina_code(symbol, today=date(2026, 11, 22))


def test_fetch_keeps_only_finished_bars_in_pandadata_codes():
    fake = FakeAkshare()
    result = fetch_intraday_bars(["RB2701.SHF", "000001.SZ"], "5m", now=NOW, akshare=fake)
    bars = result.bars
    assert list(bars.columns) == COLUMNS
    assert set(bars["symbol"]) == {"RB2701.SHF", "000001.SZ"}
    assert (bars["source"] == SOURCE).all()
    assert result.as_of == datetime(2026, 11, 21, 10, 0)
    futures = bars[bars["symbol"] == "RB2701.SHF"]
    assert futures["eob"].max() == pd.Timestamp("2026-11-20 23:00:00")
    assert result.unfinished == {"RB2701.SHF": 2, "000001.SZ": 0}
    assert futures["open_interest"].tolist() == [1488467.0, 1484538.0]
    stock = bars[bars["symbol"] == "000001.SZ"]
    assert len(stock) == 2  # the duplicated 15:00 row collapses to one
    assert stock["close"].dtype == float and stock["volume"].iloc[-1] == 8267800.0
    assert stock["amount"].iloc[-1] == pytest.approx(101125060.924)
    assert fake.calls == [("future", "RB2701", "5"), ("stock", "sz000001", "5", "")]
    assert result.codes == {"RB2701.SHF": "RB2701", "000001.SZ": "sz000001"}


def test_a_failing_symbol_is_reported_without_stopping_the_rest():
    fake = FakeAkshare(failing={"CF2701"})
    pauses = []
    result = fetch_intraday_bars(
        ["CF701.CZC", "RB_DOMINANT.SHF", "000001.SZ"],
        "1m",
        now=NOW,
        akshare=fake,
        pause=0.5,
        sleep=pauses.append,
    )
    assert set(result.bars["symbol"]) == {"000001.SZ"}
    assert result.errors["CF701.CZC"].startswith("KeyError")
    assert "continuous contract" in result.errors["RB_DOMINANT.SHF"]
    assert pauses == [0.5, 0.5]


def test_a_symbol_with_only_unfinished_bars_counts_as_an_error():
    fake = FakeAkshare()
    result = fetch_intraday_bars(
        ["RB2701.SHF"], "5m", now=datetime(2026, 11, 20, 22, 54), akshare=fake
    )
    assert result.bars.empty and list(result.bars.columns) == COLUMNS
    assert result.errors == {"RB2701.SHF": "AKShare returned no finished bars"}


def test_timezone_aware_now_is_read_in_shanghai_time():
    from zoneinfo import ZoneInfo

    utc = datetime(2026, 11, 21, 2, 0, 30, tzinfo=ZoneInfo("UTC"))
    result = fetch_intraday_bars(["RB2701.SHF"], "5m", now=utc, akshare=FakeAkshare())
    assert result.as_of == datetime(2026, 11, 21, 10, 0)


def test_unknown_frequency_is_refused():
    with pytest.raises(ValueError):
        fetch_intraday_bars(["RB2701.SHF"], "2m", now=NOW, akshare=FakeAkshare())


@pytest.fixture
def fake_akshare(monkeypatch, tmp_path):
    fake = FakeAkshare()
    monkeypatch.setitem(sys.modules, "akshare", fake)
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", str(tmp_path / "data"))
    # The CLI reads the clock; pin it so the fake pages' placeholders stay unfinished.
    import skills.ingest.akshare_bars as module

    real = module.fetch_intraday_bars
    monkeypatch.setattr(
        module, "fetch_intraday_bars", lambda *args, **kwargs: real(*args, now=NOW, **kwargs)
    )
    return fake


def run(capsys, *argv):
    code = main(["ingest", "intraday", *argv])
    return code, json.loads(capsys.readouterr().out)


def test_cli_writes_the_table_and_summarizes_each_symbol(capsys, fake_akshare, tmp_path):
    output = tmp_path / "out" / "bars.parquet"
    code, response = run(
        capsys, "--symbols", "RB2701.SHF,000001.SZ", "--pause", "0", "--output", str(output)
    )
    assert code == 0 and response["ok"]
    data = response["data"]
    assert data["source"] == SOURCE and data["frequency"] == "5m"
    assert data["rows"] == 4 and data["output"] == str(output)
    summary = {item["symbol"]: item for item in data["symbols"]}
    assert summary["RB2701.SHF"]["sina_code"] == "RB2701"
    assert summary["RB2701.SHF"]["last"] == "2026-11-20 23:00:00"
    written = pd.read_parquet(output)
    assert list(written.columns) == COLUMNS and len(written) == 4


def test_cli_refuses_continuous_contracts_before_any_request(capsys, fake_akshare):
    code, response = run(capsys, "--symbols", "RB_DOMINANT.SHF")
    assert code != 0 and response["error"]["code"] == "INVALID_INPUT"
    assert fake_akshare.calls == []


def test_cli_fails_when_no_symbol_returns_bars(capsys, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "akshare", FakeAkshare(failing={"RB2701"}))
    monkeypatch.setenv("QUANTSPACE_DATA_ROOT", str(tmp_path / "data"))
    code, response = run(capsys, "--symbols", "RB2701.SHF", "--pause", "0")
    assert code == 4 and response["error"]["code"] == "UPSTREAM_ERROR"
    assert "RB2701.SHF" in response["error"]["message"]
