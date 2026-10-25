"""Offline tests for the ``qs ingest`` command adapters.

Every test drives the runner (``skills.cli.main``) against a fake ``panda_data`` SDK
installed in ``sys.modules``; nothing touches the network, the repository ``data/``
directory, or real credentials.
"""

from __future__ import annotations

import json
import sys
import types
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from skills.cli import main
from skills.cli.models import CLIModel
from skills.ingest import PandaDataClient
from skills.ingest import cli as ingest_cli
from skills.ingest import panda_future_tick as tick

PUBLIC_ENDPOINTS = [
    "get_market_data",
    "get_market_min_data",
    "get_hk_daily",
    "get_us_daily",
    "get_fund_detail",
    "get_fund_daily",
    "get_fund_daily_pre",
    "get_fund_daily_post",
    "get_fund_etf_cr_limits",
    "get_fund_etf_cr_net",
    "get_fund_etf_constituents",
    "get_fund_etf_cr",
    "get_stock_detail",
    "get_index_detail",
    "get_index_indicator",
    "get_index_weights",
    "get_industry_detail",
    "get_industry_constituents",
    "get_stock_industry",
    "get_concept_list",
    "get_concept_constituents",
    "get_adj_factor",
    "get_trade_cal",
]


def daily_frame(symbols=("600000.SH",), dates=("20240103", "20240102")) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        for offset, day in enumerate(dates):
            rows.append(
                {
                    "symbol": symbol,
                    "date": day,
                    "name": "demo",
                    "open": 1.0 + offset,
                    "high": 2.0 + offset,
                    "low": 0.5 + offset,
                    "close": 1.5 + offset,
                    "volume": 100.0 + offset,
                    "amount": 1000.0 + offset,
                }
            )
    return pd.DataFrame(rows)


def minute_frame(symbol="600000.SH") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol] * 3,
            "date": ["20250127"] * 3,
            "minute": ["110000", "105900", "095500"],
            "open": [3.0, 2.0, 1.0],
            "high": [3.5, 2.5, 1.5],
            "low": [2.5, 1.5, 0.5],
            "close": [3.2, 2.2, 1.2],
            "volume": [30.0, 20.0, 10.0],
            "amount": [300.0, 200.0, 100.0],
        }
    )


def symbols_of(kwargs) -> list[str]:
    value = kwargs.get("symbol")
    if value is None or value == "":
        return ["600000.SH"]
    return [value] if isinstance(value, str) else list(value)


class FakeSDK(types.ModuleType):
    """Stands in for ``panda_data``; records calls and serves canned frames."""

    def __dir__(self):
        # Like the real SDK namespace: endpoints and helpers, not this fake's own plumbing.
        return [*PUBLIC_ENDPOINTS, "init_token", "Helper", "_hidden", "calls", "responses"]

    def __init__(self):
        super().__init__("panda_data")
        self.calls: list[tuple[str, dict]] = []
        self.responses: dict = {}
        for name in PUBLIC_ENDPOINTS:
            setattr(self, name, self._endpoint(name))
        self.init_token = self._init_token
        self.Helper = type("Helper", (), {})
        self._hidden = lambda **kwargs: None

    def _init_token(self, **kwargs):
        self.calls.append(("init_token", kwargs))

    def _endpoint(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            response = self.responses.get(name)
            if isinstance(response, Exception):
                raise response
            if callable(response):
                return response(kwargs)
            if response is not None:
                return response
            return self.default(name, kwargs)

        return call

    @staticmethod
    def default(name, kwargs):
        if name == "get_market_min_data":
            return minute_frame(symbols_of(kwargs)[0])
        if name in {
            "get_market_data",
            "get_hk_daily",
            "get_us_daily",
            "get_fund_daily",
            "get_fund_daily_pre",
            "get_fund_daily_post",
        }:
            return daily_frame(symbols_of(kwargs))
        if name == "get_adj_factor":
            return pd.DataFrame(
                {
                    "symbol": ["600000.SH", "000001.SZ", "600000.SH"],
                    "ex_date": ["20240602", "20240603", "20230601"],
                    "ex_cum_factor": [2.0, 3.0, 1.5],
                    "ex_factor": [1.3, 3.0, 1.5],
                    "ex_end_date": [None, None, None],
                    "announcement_date": ["20240601", "20240602", "20230531"],
                }
            )
        return pd.DataFrame({"symbol": ["600000.SH", "000001.SZ"], "value": [1, 2]})

    def sdk_calls(self) -> list[tuple[str, dict]]:
        return [call for call in self.calls if call[0] != "init_token"]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Fake credentials, an empty working directory (no .env), and no data-root override."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PANDA_DATA_USERNAME", "fake-user")
    monkeypatch.setenv("PANDA_DATA_PASSWORD", "fake-password")
    monkeypatch.delenv("QUANTSPACE_DATA_ROOT", raising=False)


@pytest.fixture
def sdk(monkeypatch):
    fake = FakeSDK()
    monkeypatch.setitem(sys.modules, "panda_data", fake)
    return fake


def run(capsys, *argv):
    code = main(["ingest", *argv])
    return code, json.loads(capsys.readouterr().out)


def direct(sdk, method, *args, **kwargs):
    """What a Python caller gets from PandaDataClient for the same fake SDK."""
    sdk.calls.clear()
    frame = getattr(PandaDataClient(), method)(*args, **kwargs)
    calls = list(sdk.calls)
    sdk.calls.clear()
    return frame, calls


def assert_error(code, response, name, status):
    assert code == status, response
    assert response["ok"] is False
    assert response["error"]["code"] == name, response


# ---------------------------------------------------------------------------
# Registry and schemas
# ---------------------------------------------------------------------------


def test_commands_are_registered_with_described_schemas():
    names = [command.name for command in ingest_cli.COMMANDS]
    assert len(names) == len(set(names))
    assert set(names) == {
        "ingest.bars",
        "ingest.adj-factor",
        "ingest.ref.stock-detail",
        "ingest.ref.fund-detail",
        "ingest.ref.index-detail",
        "ingest.ref.index-indicator",
        "ingest.ref.index-weights",
        "ingest.ref.industry-detail",
        "ingest.ref.industry-constituents",
        "ingest.ref.stock-industry",
        "ingest.ref.concept-list",
        "ingest.ref.concept-constituents",
        "ingest.etf.limits",
        "ingest.etf.net",
        "ingest.etf.constituents",
        "ingest.etf.list",
        "ingest.raw",
        "ingest.future-ticks",
    }
    by_name = {command.name: command for command in ingest_cli.COMMANDS}
    assert by_name["ingest.bars"].priority == "P0"
    assert set(by_name["ingest.bars"].side_effects) == {"network", "writes-output", "writes-store"}
    assert by_name["ingest.raw"].positional == ("method",)
    for command in ingest_cli.COMMANDS:
        assert issubclass(command.input_model, CLIModel)
        schemas = command.schemas()
        for part in ("input", "output"):
            for field, schema in schemas[part]["properties"].items():
                assert schema.get("description"), (
                    f"{command.name} {part}.{field} has no description"
                )
        assert schemas["output"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "argv",
    [
        ["bars"],
        ["adj-factor"],
        ["ref", "fund-detail"],
        ["etf", "limits"],
        ["raw"],
        ["future-ticks"],
    ],
)
def test_print_template_and_help_work(capsys, argv):
    code, response = run(capsys, *argv, "--print-template")
    assert code == 0 and response["ok"], response
    assert main(["ingest", *argv, "--help"]) == 0
    assert "usage: qs ingest" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# ingest.bars: routing
# ---------------------------------------------------------------------------

BAR_ROUTES = [
    (
        ["--asset", "stock"],
        "get_market_data",
        {"type": "stock", "fields": [], "indicator": "", "st": True},
    ),
    (
        ["--asset", "stock", "--indicator", "000300", "--no-st", "--fields", "close,volume"],
        "get_market_data",
        {"type": "stock", "fields": ["close", "volume"], "indicator": "000300", "st": False},
    ),
    (["--asset", "index"], "get_market_data", {"type": "index"}),
    (["--asset", "future"], "get_market_data", {"type": "future"}),
    (
        ["--asset", "stock", "--freq", "5m"],
        "get_market_min_data",
        {"symbol_type": "stock", "frequency": "5m", "fields": []},
    ),
    (
        ["--asset", "index", "--freq", "1m"],
        "get_market_min_data",
        {"symbol_type": "index", "frequency": "1m"},
    ),
    (
        ["--asset", "future", "--freq", "60m"],
        "get_market_min_data",
        {"symbol_type": "future", "frequency": "60m"},
    ),
    (["--asset", "hk"], "get_hk_daily", {"fields": []}),
    (["--asset", "us"], "get_us_daily", {"fields": []}),
    (["--asset", "fund"], "get_fund_daily", {}),
    (["--asset", "fund", "--adjust", "none"], "get_fund_daily", {}),
    (["--asset", "fund", "--adjust", "pre"], "get_fund_daily_pre", {}),
    (["--asset", "fund", "--adjust", "post"], "get_fund_daily_post", {}),
]


@pytest.mark.parametrize(("flags", "method", "expected"), BAR_ROUTES)
def test_bars_route_each_asset_frequency_and_adjustment(capsys, sdk, flags, method, expected):
    code, response = run(
        capsys,
        "bars",
        *flags,
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
    )
    assert code == 0, response
    calls = sdk.sdk_calls()
    assert [name for name, _ in calls] == [method]
    kwargs = calls[0][1]
    # QuantSpace symbols reach the SDK in native form, dates as YYYYMMDD.
    assert kwargs["symbol"] == "600000.SH"
    assert (kwargs["start_date"], kwargs["end_date"]) == ("20240102", "20240103")
    for key, value in expected.items():
        assert kwargs[key] == value, key
    assert response["data"]["rows"] == len(sdk.default(method, kwargs))
    assert response["data"]["start"] == "20240102" and response["data"]["end"] == "20240103"


def test_bars_accept_compact_dates_comma_symbols_and_symbols_file(capsys, sdk, tmp_path):
    listing = tmp_path / "symbols.txt"
    listing.write_text("SHSE.600001\nSHSE.600002\n", encoding="utf-8")
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000,600003.SH",
        "--start",
        "20240102",
        "--end",
        "20240103",
    )
    assert code == 0, response
    assert sdk.sdk_calls()[0][1]["symbol"] == ["600000.SH", "600003.SH"]
    assert sdk.sdk_calls()[0][1]["start_date"] == "20240102"
    assert response["data"]["requested_symbols"] == ["SHSE.600000", "SHSE.600003"]
    sdk.calls.clear()
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols-file",
        str(listing),
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
    )
    assert code == 0, response
    assert sdk.sdk_calls()[0][1]["symbol"] == ["600001.SH", "600002.SH"]


def test_bars_default_end_is_today(capsys, sdk):
    code, response = run(
        capsys, "bars", "--asset", "stock", "--symbols", "SHSE.600000", "--start", "2024-01-02"
    )
    assert code == 0, response
    assert sdk.sdk_calls()[0][1]["end_date"] == date.today().strftime("%Y%m%d")


def test_long_daily_ranges_are_split_below_the_provider_cap(capsys, sdk):
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2015-01-01",
        "--end",
        "2022-06-30",
    )
    assert code == 0, response
    windows = [(kw["start_date"], kw["end_date"]) for _, kw in sdk.sdk_calls()]
    assert len(windows) == 2

    def parse(text):
        return date(int(text[:4]), int(text[4:6]), int(text[6:]))

    for first, last in windows:
        assert (parse(last) - parse(first)).days < 365 * 5
    assert windows[0][0] == "20150101" and windows[-1][1] == "20220630"
    assert parse(windows[1][0]) - parse(windows[0][1]) == timedelta(days=1)
    assert response["data"]["rows"] == 4  # two canned rows per chunk, concatenated


def test_minute_and_fund_requests_are_not_split_by_the_adapter(capsys, sdk):
    code, _ = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--freq",
        "1m",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2015-01-01",
        "--end",
        "2022-06-30",
    )
    assert code == 0 and len(sdk.sdk_calls()) == 1
    sdk.calls.clear()
    # The client itself chunks listed-fund ranges to 365 days.
    code, _ = run(
        capsys,
        "bars",
        "--asset",
        "fund",
        "--symbols",
        "SHSE.510300",
        "--start",
        "2023-01-01",
        "--end",
        "2024-12-31",
    )
    assert code == 0 and len(sdk.sdk_calls()) == 3


# ---------------------------------------------------------------------------
# ingest.bars: rejected combinations
# ---------------------------------------------------------------------------

BASE = ["bars", "--symbols", "SHSE.510300", "--start", "2024-01-01"]
REJECTED = [
    [*BASE, "--asset", "fund", "--freq", "1m"],
    [*BASE, "--asset", "hk", "--freq", "5m"],
    [*BASE, "--asset", "us", "--freq", "60m"],
    [*BASE, "--asset", "index", "--freq", "5m"],
    [*BASE, "--asset", "index", "--freq", "15m"],
    [*BASE, "--asset", "stock", "--adjust", "pre"],
    [*BASE, "--asset", "future", "--adjust", "post"],
    [*BASE, "--asset", "index", "--indicator", "000300"],
    [*BASE, "--asset", "stock", "--freq", "5m", "--no-st"],
    [*BASE, "--asset", "stock", "--freq", "5m", "--indicator", "000300"],
    [*BASE, "--asset", "fund", "--no-st"],
    [*BASE, "--asset", "stock", "--write"],
    [*BASE, "--asset", "stock", "--end", "2023-01-01"],
    [*BASE, "--asset", "stock", "--save-frequency", "../escape", "--write"],
    [*BASE, "--asset", "stock", "--freq", "1d_adj"],
    [*BASE, "--asset", "bond"],
    ["bars", "--asset", "stock", "--start", "2024-01-01"],
    ["bars", "--asset", "stock", "--symbols", "SHSE.600000", "--start", "2024/01/01"],
    ["bars", "--asset", "stock", "--symbols", "SHSE.600000", "--start", "2024-13-01"],
    ["bars", "--asset", "stock", "--symbols", "SHSE.600000"],
    ["bars", "--asset", "stock", "--symbols", "a/b", "--start", "2024-01-01"],
]


@pytest.mark.parametrize("argv", REJECTED)
def test_bars_reject_impossible_inputs_before_any_sdk_call(capsys, sdk, tmp_path, argv):
    code, response = run(capsys, *argv, "--data-root", str(tmp_path / "data"))
    assert_error(code, response, "INVALID_INPUT", 2)
    assert sdk.calls == []
    assert not (tmp_path / "data").exists()


def test_output_in_managed_namespace_is_rejected_before_any_sdk_call(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    code, response = run(
        capsys,
        *BASE,
        "--asset",
        "fund",
        "--output",
        str(root / "market" / "1d" / "x.parquet"),
        "--data-root",
        str(root),
    )
    assert_error(code, response, "INVALID_INPUT", 2)
    code, response = run(capsys, *BASE, "--asset", "fund", "--output", str(tmp_path / "bars.txt"))
    assert_error(code, response, "INVALID_INPUT", 2)
    assert sdk.calls == [] and not root.exists()


# ---------------------------------------------------------------------------
# ingest.bars: outputs equal the direct client call
# ---------------------------------------------------------------------------


def test_bars_output_is_the_raw_client_table(capsys, sdk, tmp_path):
    expected, expected_calls = direct(
        sdk, "fetch_market_data", "SHSE.600000", "20240102", "20240103", type="stock"
    )
    target = tmp_path / "out" / "bars.parquet"
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--output",
        str(target),
    )
    assert code == 0, response
    pd.testing.assert_frame_equal(pd.read_parquet(target), expected)
    assert sdk.calls[1:] == expected_calls[1:] and sdk.calls[0][0] == "init_token"
    assert response["artifacts"][0]["path"] == str(target.resolve())
    assert response["artifacts"][0]["rows"] == len(expected)
    assert response["data"]["output"] == str(target.resolve())
    assert response["data"]["columns"] == list(expected.columns)
    # stdout carries a preview, not the table.
    assert len(response["data"]["preview"]) == len(expected)
    assert response["data"]["preview"][0]["symbol"] == "SHSE.600000"
    assert response["data"]["symbols"][0] == {
        "symbol": "SHSE.600000",
        "rows": 2,
        "start": "2024-01-02 00:00:00",
        "end": "2024-01-03 00:00:00",
    }


def test_bars_csv_output_and_preview_limit(capsys, sdk, tmp_path):
    sdk.responses["get_fund_daily"] = daily_frame(
        ("510300.SH",), tuple(f"202401{d:02d}" for d in range(2, 12))
    )
    expected, _ = direct(
        sdk, "get_fund_daily", "20240102", "20240111", symbol="SHSE.510300", fields=None
    )
    target = tmp_path / "fund.csv"
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "fund",
        "--symbols",
        "SHSE.510300",
        "--start",
        "20240102",
        "--end",
        "20240111",
        "--output",
        str(target),
        "--preview",
        "2",
    )
    assert code == 0, response
    written = pd.read_csv(target, dtype={"date": str})
    pd.testing.assert_frame_equal(written, expected, check_dtype=False)
    assert len(response["data"]["preview"]) == 2 and response["data"]["rows"] == 10
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "fund",
        "--symbols",
        "SHSE.510300",
        "--start",
        "20240102",
        "--end",
        "20240111",
        "--output",
        str(target),
    )
    assert_error(code, response, "CONFLICT", 2)


@pytest.mark.parametrize(
    ("flags", "method", "args", "kwargs"),
    [
        (
            ["--asset", "stock", "--indicator", "000300", "--no-st"],
            "fetch_market_data",
            ("SHSE.600000", "20240102", "20240103"),
            {"type": "stock", "indicator": "000300", "st": False},
        ),
        (
            ["--asset", "stock", "--freq", "15m", "--fields", "close"],
            "fetch_market_min_data",
            ("SHSE.600000", "20240102", "20240103"),
            {"symbol_type": "stock", "frequency": "15m", "fields": ["close"]},
        ),
        (
            ["--asset", "hk"],
            "fetch_hk_daily",
            ("SHSE.600000", "20240102", "20240103"),
            {},
        ),
        (
            ["--asset", "us"],
            "fetch_us_daily",
            ("SHSE.600000", "20240102", "20240103"),
            {},
        ),
        (
            ["--asset", "fund", "--adjust", "pre", "--fields", "close,volume"],
            "get_fund_daily_pre",
            ("20240102", "20240103"),
            {"symbol": "SHSE.600000", "fields": ["close", "volume"]},
        ),
        (
            ["--asset", "fund", "--adjust", "post"],
            "get_fund_daily_post",
            ("20240102", "20240103"),
            {"symbol": "SHSE.600000"},
        ),
    ],
)
def test_bars_make_the_same_sdk_call_as_a_python_caller(
    capsys, sdk, tmp_path, flags, method, args, kwargs
):
    expected, expected_calls = direct(sdk, method, *args, **kwargs)
    target = tmp_path / "bars.parquet"
    code, response = run(
        capsys,
        "bars",
        *flags,
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--output",
        str(target),
    )
    assert code == 0, response
    assert [call for call in sdk.calls if call[0] != "init_token"] == [
        call for call in expected_calls if call[0] != "init_token"
    ]
    pd.testing.assert_frame_equal(pd.read_parquet(target), expected)


# ---------------------------------------------------------------------------
# ingest.bars: market store (dry run, --write, --overwrite)
# ---------------------------------------------------------------------------


def test_save_frequency_without_write_is_a_dry_run(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "600000.SH,SHSE.600001",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--save-frequency",
        "1d_adj",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    data = response["data"]
    assert data["dry_run"] is True and data["saved"] is False and data["rows"] == 0
    # Native input symbols are planned under their QuantSpace names, like the client returns.
    assert data["planned_paths"] == [
        str((root / "market" / "1d_adj" / "SHSE.600000.parquet").resolve()),
        str((root / "market" / "1d_adj" / "SHSE.600001.parquet").resolve()),
    ]
    assert data["target_frequency"] == "1d_adj" and data["written_paths"] == []
    assert sdk.calls == [] and not root.exists()


def test_dry_run_ignores_output_with_a_warning(capsys, sdk, tmp_path):
    target = tmp_path / "bars.parquet"
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--save-frequency",
        "1d",
        "--output",
        str(target),
        "--data-root",
        str(tmp_path / "data"),
    )
    assert code == 0 and response["data"]["dry_run"]
    assert any("--output ignored" in warning for warning in response["warnings"])
    assert sdk.calls == [] and not target.exists()


def test_write_stores_ohlcv_per_symbol_with_a_naive_sorted_eob_index(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    sdk.responses["get_market_data"] = daily_frame(
        ("600000.SH", "600001.SH"), ("20240103", "20240102")
    )
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000,SHSE.600001",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--save-frequency",
        "1d",
        "--write",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    assert response["data"]["saved"] is True and response["data"]["dry_run"] is False
    written = sorted(response["data"]["written_paths"])
    assert written == sorted(
        str((root / "market" / "1d" / f"SHSE.60000{n}.parquet").resolve()) for n in (0, 1)
    )
    assert response["data"]["written_paths"] == response["data"]["planned_paths"]
    for number in (0, 1):
        stored = pd.read_parquet(root / "market" / "1d" / f"SHSE.60000{number}.parquet")
        assert stored.index.name == "eob"
        assert isinstance(stored.index, pd.DatetimeIndex) and stored.index.tz is None
        assert list(stored.index) == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
        assert list(stored.columns) == ["open", "high", "low", "close", "volume"]
        # The canned frame lists 2024-01-03 first (offset 0): sorting kept each row intact.
        assert stored.loc["2024-01-03", "close"] == 1.5
        assert stored.loc["2024-01-02", "close"] == 2.5
    assert [item["symbol"] for item in response["data"]["symbols"]] == [
        "SHSE.600000",
        "SHSE.600001",
    ]


def test_write_store_matches_the_direct_client_table(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    raw, _ = direct(
        sdk, "get_fund_daily", "20240102", "20240103", symbol="SHSE.510300", fields=None
    )
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "fund",
        "--symbols",
        "SHSE.510300",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--save-frequency",
        "1d",
        "--write",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    stored = pd.read_parquet(root / "market" / "1d" / "SHSE.510300.parquet")
    expected = (
        raw.assign(eob=pd.to_datetime(raw["date"]))
        .set_index("eob")[["open", "high", "low", "close", "volume"]]
        .sort_index()
    )
    pd.testing.assert_frame_equal(stored, expected)


def test_write_minute_bars_combine_date_and_minute(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--freq",
        "5m",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2025-01-27",
        "--end",
        "2025-01-27",
        "--save-frequency",
        "5m",
        "--write",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    stored = pd.read_parquet(root / "market" / "5m" / "SHSE.600000.parquet")
    assert list(stored.index) == [
        pd.Timestamp("2025-01-27 09:55:00"),
        pd.Timestamp("2025-01-27 10:59:00"),
        pd.Timestamp("2025-01-27 11:00:00"),
    ]
    assert list(stored["close"]) == [1.2, 2.2, 3.2]
    assert response["data"]["symbols"][0]["start"] == "2025-01-27 09:55:00"


def test_write_minute_bars_accept_numeric_minutes_and_future_datetime(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    numeric = minute_frame()
    numeric["minute"] = [110000, 105900, 95500]
    sdk.responses["get_market_min_data"] = numeric
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--freq",
        "1m",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2025-01-27",
        "--end",
        "2025-01-27",
        "--save-frequency",
        "1m",
        "--write",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    stored = pd.read_parquet(root / "market" / "1m" / "SHSE.600000.parquet")
    assert stored.index[0] == pd.Timestamp("2025-01-27 09:55:00")
    futures = minute_frame("RB_DOMINANT.SHF")
    futures["datetime"] = ["2025-01-27 21:03:00", "2025-01-27 21:02:00", "2025-01-27 21:01:00"]
    futures["minute"] = ["210300", "210200", "210100"]
    sdk.responses["get_market_min_data"] = futures
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "future",
        "--freq",
        "1m",
        "--symbols",
        "SHFE.RB99",
        "--start",
        "2025-01-27",
        "--end",
        "2025-01-27",
        "--save-frequency",
        "1m",
        "--write",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    # The dominant contract round-trips: native RB_DOMINANT.SHF comes back as SHFE.RB99.
    stored = pd.read_parquet(root / "market" / "1m" / "SHFE.RB99.parquet")
    assert stored.index[0] == pd.Timestamp("2025-01-27 21:01:00")
    assert response["data"]["no_data"] == []


def test_write_requires_overwrite_for_existing_files(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    argv = [
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--save-frequency",
        "1d",
        "--write",
        "--data-root",
        str(root),
    ]
    code, _ = run(capsys, *argv)
    assert code == 0
    path = root / "market" / "1d" / "SHSE.600000.parquet"
    path.write_bytes(b"keep me")
    sdk.calls.clear()
    code, response = run(capsys, *argv)
    assert_error(code, response, "CONFLICT", 2)
    assert path.read_bytes() == b"keep me" and sdk.calls == []
    code, response = run(capsys, *argv, "--overwrite")
    assert code == 0, response
    assert list(pd.read_parquet(path).columns) == ["open", "high", "low", "close", "volume"]


def test_write_conflict_on_any_symbol_writes_nothing(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    existing = root / "market" / "1d" / "SHSE.600001.parquet"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"keep me")
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000,SHSE.600001",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--save-frequency",
        "1d",
        "--write",
        "--data-root",
        str(root),
    )
    assert_error(code, response, "CONFLICT", 2)
    assert response["error"]["details"] == ["SHSE.600001"]
    assert not (root / "market" / "1d" / "SHSE.600000.parquet").exists()


def test_write_refuses_to_write_through_a_symlink(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    outside = tmp_path / "outside.parquet"
    outside.write_text("keep")
    link = root / "market" / "1d" / "SHSE.600000.parquet"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--save-frequency",
        "1d",
        "--write",
        "--overwrite",
        "--data-root",
        str(root),
    )
    assert_error(code, response, "INVALID_INPUT", 2)
    assert outside.read_text() == "keep" and sdk.calls == []


def test_write_and_output_together_and_returned_symbol_conflicts(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    target = tmp_path / "raw.parquet"
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--output",
        str(target),
        "--save-frequency",
        "1d",
        "--write",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    assert target.exists() and (root / "market" / "1d" / "SHSE.600000.parquet").exists()
    assert [item["name"] for item in response["artifacts"]] == ["bars"]
    # The provider returns a symbol that was not requested: it is stored under its own name,
    # and an existing file for it is a conflict that leaves the raw output unwritten.
    other = root / "market" / "1d" / "SHSE.688000.parquet"
    other.write_bytes(b"keep me")
    sdk.responses["get_market_data"] = daily_frame(("600000.SH", "688000.SH"))
    second = tmp_path / "second.parquet"
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--output",
        str(second),
        "--save-frequency",
        "1d",
        "--write",
        "--overwrite",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    assert other.read_bytes() != b"keep me"
    (root / "market" / "1d" / "SHSE.600000.parquet").unlink()
    sdk.responses["get_market_data"] = daily_frame(("600000.SH", "688001.SH"))
    third = tmp_path / "third.parquet"
    (root / "market" / "1d" / "SHSE.688001.parquet").write_bytes(b"keep me")
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--output",
        str(third),
        "--save-frequency",
        "1d",
        "--write",
        "--data-root",
        str(root),
    )
    assert_error(code, response, "CONFLICT", 2)
    assert not third.exists() and not (root / "market" / "1d" / "SHSE.600000.parquet").exists()


def test_write_rejects_unstorable_returned_tables_without_writing(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    argv = [
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--output",
        str(tmp_path / "raw.parquet"),
        "--save-frequency",
        "1d",
        "--write",
        "--data-root",
        str(root),
    ]
    sdk.responses["get_market_data"] = daily_frame()[["symbol", "date", "name"]]
    code, response = run(capsys, *argv)
    assert_error(code, response, "INVALID_INPUT", 2)
    sdk.responses["get_market_data"] = daily_frame().drop(columns=["date"])
    code, response = run(capsys, *argv)
    assert_error(code, response, "INVALID_INPUT", 2)
    unsafe = daily_frame(("../escape",))
    sdk.responses["get_market_data"] = unsafe
    code, response = run(capsys, *argv)
    assert_error(code, response, "UPSTREAM_ERROR", 4)
    assert not root.exists() and not (tmp_path / "raw.parquet").exists()


def test_write_drops_duplicate_timestamps_with_a_warning(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    frame = daily_frame(dates=("20240102", "20240102", "20240103"))
    frame["close"] = [10.0, 11.0, 12.0]
    sdk.responses["get_market_data"] = frame
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--save-frequency",
        "1d",
        "--write",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    stored = pd.read_parquet(root / "market" / "1d" / "SHSE.600000.parquet")
    assert len(stored) == 2 and stored.loc["2024-01-02", "close"] == 11.0
    assert any("duplicate" in warning for warning in response["warnings"])


def test_mismatched_save_frequency_warns_and_empty_results_write_nothing(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    sdk.responses["get_market_data"] = pd.DataFrame()
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--save-frequency",
        "5m",
        "--write",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    assert response["data"]["saved"] is False and response["data"]["rows"] == 0
    assert any("does not match" in warning for warning in response["warnings"])
    assert any("no rows" in warning for warning in response["warnings"])
    assert not (root / "market").exists()


def test_requested_symbols_without_rows_are_reported(capsys, sdk):
    sdk.responses["get_market_data"] = daily_frame(("600000.SH",))
    code, response = run(
        capsys,
        "bars",
        "--asset",
        "stock",
        "--symbols",
        "SHSE.600000,SHSE.600001",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
    )
    assert code == 0, response
    assert response["data"]["no_data"] == ["SHSE.600001"]
    assert any("SHSE.600001" in warning for warning in response["warnings"])
    assert response["artifacts"] == []


# ---------------------------------------------------------------------------
# ingest.adj-factor
# ---------------------------------------------------------------------------


def test_adj_factor_without_destination_is_a_dry_run(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    code, response = run(
        capsys,
        "adj-factor",
        "--symbols",
        "600000.SH",
        "--start",
        "2024-01-01",
        "--data-root",
        str(root),
    )
    assert code == 0, response
    data = response["data"]
    assert data["dry_run"] and data["scope"] == "explicit-symbols"
    assert data["planned_paths"] == [str((root / "adj_factor" / "SHSE.600000.parquet").resolve())]
    assert data["start"] == "20240101" and data["end"] is None
    code, response = run(capsys, "adj-factor", "--data-root", str(root))
    assert code == 0 and response["data"]["scope"] == "all-market"
    assert response["data"]["planned_paths"] == []
    assert response["data"]["path_template"].endswith("/adj_factor/{symbol}.parquet")
    assert sdk.calls == [] and not root.exists()


def test_adj_factor_output_equals_the_direct_client_call(capsys, sdk, tmp_path):
    expected, expected_calls = direct(
        sdk, "get_adj_factor", "SHSE.600000", "20240101", "20241231", fields=None
    )
    target = tmp_path / "adj.parquet"
    code, response = run(
        capsys,
        "adj-factor",
        "--symbols",
        "SHSE.600000",
        "--start",
        "2024-01-01",
        "--end",
        "2024-12-31",
        "--output",
        str(target),
    )
    assert code == 0, response
    assert [call for call in sdk.calls if call[0] != "init_token"] == [
        call for call in expected_calls if call[0] != "init_token"
    ]
    pd.testing.assert_frame_equal(pd.read_parquet(target), expected)
    assert response["data"]["rows"] == 3 and response["data"]["saved"] is False
    assert response["data"]["symbols"] == ["SHSE.600000", "SZSE.000001"]


def test_adj_factor_write_stores_one_event_table_per_returned_symbol(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    code, response = run(capsys, "adj-factor", "--write", "--data-root", str(root))
    assert code == 0, response
    assert sdk.sdk_calls()[0][1]["symbol"] == ""
    assert response["data"]["saved"] and response["data"]["scope"] == "all-market"
    first = pd.read_parquet(root / "adj_factor" / "SHSE.600000.parquet")
    assert first.index.name == "ex_date" and isinstance(first.index, pd.DatetimeIndex)
    assert list(first.index) == [pd.Timestamp("2023-06-01"), pd.Timestamp("2024-06-02")]
    assert list(first["ex_cum_factor"]) == [1.5, 2.0]
    assert "symbol" not in first.columns and "ex_factor" in first.columns
    second = pd.read_parquet(root / "adj_factor" / "SZSE.000001.parquet")
    assert list(second.index) == [pd.Timestamp("2024-06-03")]
    assert sorted(response["data"]["written_paths"]) == sorted(
        str((root / "adj_factor" / f"{name}.parquet").resolve())
        for name in ("SHSE.600000", "SZSE.000001")
    )
    # The stored table is what the forward-adjust consumer reads.
    from skills.compute.adjust import forward_adjust

    bars = pd.DataFrame({"close": [10.0, 10.0]}, index=pd.to_datetime(["2023-05-01", "2024-07-01"]))
    adjusted = forward_adjust(bars, first, price_cols=("close",))
    assert adjusted["close"].iloc[-1] == 10.0


def test_adj_factor_write_explicit_symbols_overwrite_and_missing_events(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    everything = sdk.default("get_adj_factor", {})
    sdk.responses["get_adj_factor"] = lambda kwargs: everything[
        everything["symbol"].isin(symbols_of(kwargs))
    ]
    argv = [
        "adj-factor",
        "--symbols",
        "SHSE.600000,SHSE.600999",
        "--write",
        "--data-root",
        str(root),
    ]
    code, response = run(capsys, *argv)
    assert code == 0, response
    assert response["data"]["no_data"] == ["SHSE.600999"]
    assert not (root / "adj_factor" / "SHSE.600999.parquet").exists()
    assert any("SHSE.600999" in warning for warning in response["warnings"])
    sdk.calls.clear()
    code, response = run(capsys, *argv)
    assert_error(code, response, "CONFLICT", 2)
    assert sdk.calls == []
    code, response = run(capsys, *argv, "--overwrite")
    assert code == 0, response


def test_adj_factor_all_market_conflict_is_atomic_and_bad_data_is_rejected(capsys, sdk, tmp_path):
    root = tmp_path / "data"
    existing = root / "adj_factor" / "SZSE.000001.parquet"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"keep me")
    code, response = run(capsys, "adj-factor", "--write", "--data-root", str(root))
    assert_error(code, response, "CONFLICT", 2)
    assert existing.read_bytes() == b"keep me"
    assert not (root / "adj_factor" / "SHSE.600000.parquet").exists()
    existing.unlink()
    bad = sdk.default("get_adj_factor", {})
    bad.loc[1, "ex_date"] = "not-a-date"
    sdk.responses["get_adj_factor"] = bad
    code, response = run(capsys, "adj-factor", "--write", "--data-root", str(root))
    assert_error(code, response, "UPSTREAM_ERROR", 4)
    sdk.responses["get_adj_factor"] = sdk.default("get_adj_factor", {}).assign(
        symbol=["600000.SH", "../escape", "600000.SH"]
    )
    code, response = run(capsys, "adj-factor", "--write", "--data-root", str(root))
    assert_error(code, response, "UPSTREAM_ERROR", 4)
    sdk.responses["get_adj_factor"] = sdk.default("get_adj_factor", {})[["symbol", "ex_cum_factor"]]
    code, response = run(capsys, "adj-factor", "--write", "--data-root", str(root))
    assert_error(code, response, "INVALID_INPUT", 2)
    assert list((root / "adj_factor").glob("*")) == []


def test_adj_factor_rejects_bad_dates_and_managed_outputs_before_any_sdk_call(
    capsys, sdk, tmp_path
):
    root = tmp_path / "data"
    for argv in (
        ["adj-factor", "--start", "not-a-date", "--write"],
        ["adj-factor", "--start", "2024-02-01", "--end", "2024-01-01", "--write"],
        ["adj-factor", "--output", str(root / "adj_factor" / "x.parquet")],
        ["adj-factor", "--symbols", "SHSE.600000", "--write", "--symbols-file", "x.txt"],
    ):
        code, response = run(capsys, *argv, "--data-root", str(root))
        assert_error(code, response, "INVALID_INPUT", 2)
    assert sdk.calls == [] and not root.exists()


# ---------------------------------------------------------------------------
# Reference endpoints
# ---------------------------------------------------------------------------

REF_CASES = [
    (
        [
            "ref",
            "stock-detail",
            "--symbols",
            "SHSE.600000,SHSE.600001",
            "--fields",
            "name",
            "--status",
            "1",
        ],
        "get_stock_detail",
        {"symbol": ["SHSE.600000", "SHSE.600001"], "fields": ["name"], "market": "cn", "status": 1},
    ),
    (
        ["ref", "stock-detail"],
        "get_stock_detail",
        {},
    ),
    (
        [
            "ref",
            "fund-detail",
            "--etf-lof-type",
            "ETF",
            "--status",
            "L",
            "--is-class-fund",
            "0",
            "--fields",
            "name,exchange",
        ],
        "get_fund_detail",
        {"etf_lof_type": "ETF", "status": "L", "is_class_fund": 0, "fields": ["name", "exchange"]},
    ),
    (
        ["ref", "fund-detail", "--symbols", "SHSE.510300", "--exchange", "SH,SZ", "--type", "A"],
        "get_fund_detail",
        {"symbol": "SHSE.510300", "exchange": ["SH", "SZ"], "type": "A"},
    ),
    (
        ["ref", "index-detail", "--symbols", "SHSE.000300", "--status", "1"],
        "get_index_detail",
        {"symbol": "SHSE.000300", "status": 1},
    ),
    (
        [
            "ref",
            "index-indicator",
            "--symbols",
            "SHSE.000300",
            "--start",
            "2024-01-01",
            "--end",
            "20240131",
            "--fields",
            "pe",
        ],
        "get_index_indicator",
        {
            "symbol": "SHSE.000300",
            "start_date": "20240101",
            "end_date": "20240131",
            "fields": ["pe"],
        },
    ),
    (
        [
            "ref",
            "index-weights",
            "--start",
            "20240101",
            "--end",
            "2024-01-31",
            "--index-symbol",
            "SHSE.000300",
            "--stock-symbol",
            "SHSE.600000",
        ],
        "get_index_weights",
        {
            "start_date": "20240101",
            "end_date": "20240131",
            "index_symbol": "SHSE.000300",
            "stock_symbol": "SHSE.600000",
        },
    ),
    (
        ["ref", "industry-detail", "--level", "1"],
        "get_industry_detail",
        {"level": "1"},
    ),
    (
        [
            "ref",
            "industry-constituents",
            "--industry-code",
            "801010",
            "--stock-symbol",
            "SHSE.600000",
            "--level",
            "1",
        ],
        "get_industry_constituents",
        {"industry_code": "801010", "stock_symbol": "SHSE.600000", "level": "1"},
    ),
    (
        ["ref", "stock-industry", "--stock-symbol", "SHSE.600000", "--level", "2"],
        "get_stock_industry",
        {"stock_symbol": "SHSE.600000", "level": "2"},
    ),
    (
        ["ref", "concept-list", "--concept", "AI", "--start", "2024-01-01"],
        "get_concept_list",
        {"concept": "AI", "start_date": "20240101"},
    ),
    (
        [
            "ref",
            "concept-constituents",
            "--concept",
            "AI",
            "--concept-stock",
            "SHSE.600000",
            "--end",
            "2024-02-01",
            "--fields",
            "symbol",
        ],
        "get_concept_constituents",
        {
            "concept": "AI",
            "concept_stock": "SHSE.600000",
            "end_date": "20240201",
            "fields": ["symbol"],
        },
    ),
    (
        [
            "etf",
            "limits",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-31",
            "--symbols",
            "SHSE.510300",
            "--exchange",
            "SH",
            "--fields",
            "nav",
        ],
        "get_fund_etf_cr_limits",
        {
            "start_date": "20240101",
            "end_date": "20240131",
            "symbol": "SHSE.510300",
            "exchange": "SH",
            "fields": ["nav"],
        },
    ),
    (
        ["etf", "net", "--start", "20240101", "--end", "20240131"],
        "get_fund_etf_cr_net",
        {"start_date": "20240101", "end_date": "20240131"},
    ),
    (
        [
            "etf",
            "constituents",
            "--start",
            "20240101",
            "--end",
            "20240131",
            "--symbols",
            "SHSE.510300,SZSE.159919",
        ],
        "get_fund_etf_constituents",
        {
            "start_date": "20240101",
            "end_date": "20240131",
            "symbol": ["SHSE.510300", "SZSE.159919"],
        },
    ),
    (
        ["etf", "list", "--start", "20240101", "--end", "20240131"],
        "get_fund_etf_cr",
        {"start_date": "20240101", "end_date": "20240131"},
    ),
]


@pytest.mark.parametrize(("argv", "method", "python_kwargs"), REF_CASES)
def test_reference_commands_match_the_direct_client_call(
    capsys, sdk, tmp_path, argv, method, python_kwargs
):
    expected, expected_calls = direct(sdk, method, **python_kwargs)
    target = tmp_path / "table.parquet"
    code, response = run(capsys, *argv, "--output", str(target))
    assert code == 0, response
    assert [call for call in sdk.calls if call[0] != "init_token"] == [
        call for call in expected_calls if call[0] != "init_token"
    ]
    pd.testing.assert_frame_equal(pd.read_parquet(target), expected)
    data = response["data"]
    assert data["endpoint"] == method and data["rows"] == len(expected)
    assert data["columns"] == list(expected.columns) and data["output"] == str(target.resolve())
    assert data["preview"] == json.loads(expected.head(5).to_json(orient="records"))
    assert response["artifacts"][0]["path"] == str(target.resolve())


def test_reference_command_converts_symbols_and_works_without_output(capsys, sdk):
    code, response = run(
        capsys,
        "ref",
        "index-weights",
        "--start",
        "2024-01-01",
        "--end",
        "2024-01-31",
        "--index-symbol",
        "SHSE.000300",
    )
    assert code == 0, response
    name, kwargs = sdk.sdk_calls()[0]
    assert name == "get_index_weights" and kwargs["index_symbol"] == "000300.SH"
    assert kwargs["stock_symbol"] == "" and kwargs["fields"] == []
    # Returned symbol columns are in QuantSpace format; no artifact without --output.
    assert response["data"]["preview"][0]["symbol"] == "SHSE.600000"
    assert response["data"]["output"] is None and response["artifacts"] == []


@pytest.mark.parametrize(
    "argv",
    [
        ["ref", "index-weights", "--end", "2024-01-31"],
        ["ref", "index-weights", "--start", "2024-02-01", "--end", "2024-01-31"],
        ["ref", "index-indicator", "--start", "2024-02-01", "--end", "2024-01-31"],
        ["ref", "stock-industry"],
        ["ref", "concept-list", "--start", "tomorrow"],
        ["ref", "stock-detail", "--status", "active"],
        ["etf", "limits", "--start", "2024-01-01"],
        ["etf", "net", "--end", "2024-01-01"],
        ["etf", "list", "--start", "2024-02-01", "--end", "2024-01-01"],
    ],
)
def test_reference_and_etf_reject_invalid_inputs_before_any_sdk_call(capsys, sdk, argv):
    code, response = run(capsys, *argv)
    assert_error(code, response, "INVALID_INPUT", 2)
    assert sdk.calls == []


def test_reference_output_conflicts_and_managed_paths(capsys, sdk, tmp_path):
    target = tmp_path / "ref.csv"
    target.write_text("keep")
    code, response = run(capsys, "ref", "index-detail", "--output", str(target))
    assert_error(code, response, "CONFLICT", 2)
    assert target.read_text() == "keep" and sdk.calls == []
    code, response = run(capsys, "ref", "index-detail", "--output", str(target), "--overwrite")
    assert code == 0, response
    assert "symbol" in pd.read_csv(target).columns
    sdk.responses["get_index_detail"] = lambda kwargs: None
    code, response = run(capsys, "ref", "index-detail")
    assert code == 0 and response["data"]["rows"] == 0
    assert any("no rows" in warning for warning in response["warnings"])


# ---------------------------------------------------------------------------
# ingest.raw
# ---------------------------------------------------------------------------


def test_raw_list_shows_public_callable_sdk_functions(capsys, sdk):
    code, response = run(capsys, "raw", "--list")
    assert code == 0, response
    methods = response["data"]["methods"]
    assert methods == sorted(PUBLIC_ENDPOINTS)
    assert "init_token" not in methods and "_hidden" not in methods and "Helper" not in methods
    assert sdk.calls == []
    code, response = run(capsys, "raw", "get_trade_cal", "--list")
    assert_error(code, response, "INVALID_INPUT", 2)


def test_raw_passes_params_through_unchanged_and_converts_returned_symbols(capsys, sdk, tmp_path):
    sdk.responses["get_trade_cal"] = lambda kwargs: pd.DataFrame(
        {"symbol": ["510300.SH"], "date": ["20240102"], "flag": [1]}
    )
    target = tmp_path / "cal.parquet"
    code, response = run(
        capsys,
        "raw",
        "get_trade_cal",
        "--params",
        '{"symbol": "SHSE.600000", "start_date": "20240101"}',
        "--output",
        str(target),
    )
    assert code == 0, response
    assert sdk.sdk_calls() == [
        ("get_trade_cal", {"symbol": "SHSE.600000", "start_date": "20240101"})
    ]
    expected, _ = direct(sdk, "_call", "get_trade_cal", symbol="SHSE.600000", start_date="20240101")
    pd.testing.assert_frame_equal(pd.read_parquet(target), expected)
    assert pd.read_parquet(target)["symbol"].tolist() == ["SHSE.510300"]
    assert response["data"]["method"] == "get_trade_cal" and response["data"]["rows"] == 1
    assert response["data"]["preview"][0]["flag"] == 1
    sdk.calls.clear()
    code, response = run(capsys, "raw", "get_trade_cal", "-p", "start_date=2024-01-01", "-p", "n=3")
    assert code == 0, response
    assert sdk.sdk_calls() == [("get_trade_cal", {"start_date": "2024-01-01", "n": 3})]


@pytest.mark.parametrize(
    "argv",
    [
        ["raw"],
        ["raw", "get_does_not_exist"],
        ["raw", "init_token"],
        ["raw", "_hidden"],
        ["raw", "Helper"],
        ["raw", "get_trade_cal", "--params", "[1, 2]"],
    ],
)
def test_raw_rejects_unknown_methods_without_calling_the_sdk(capsys, sdk, argv):
    code, response = run(capsys, *argv)
    assert_error(code, response, "INVALID_INPUT", 2)
    assert sdk.calls == []


def test_raw_non_tabular_results_are_an_upstream_error(capsys, sdk):
    sdk.responses["get_trade_cal"] = lambda kwargs: 42
    code, response = run(capsys, "raw", "get_trade_cal")
    assert_error(code, response, "UPSTREAM_ERROR", 4)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

FUND_ARGV = [
    "bars",
    "--asset",
    "fund",
    "--symbols",
    "SHSE.510300",
    "--start",
    "2024-01-01",
    "--end",
    "2024-01-02",
]


def test_missing_credentials_are_detected_before_any_request(capsys, sdk, monkeypatch, tmp_path):
    monkeypatch.delenv("PANDA_DATA_USERNAME")
    monkeypatch.delenv("PANDA_DATA_PASSWORD")
    for argv in (
        FUND_ARGV,
        ["adj-factor", "--write", "--data-root", str(tmp_path / "data")],
        ["ref", "index-detail"],
        ["raw", "get_trade_cal"],
    ):
        code, response = run(capsys, *argv)
        assert_error(code, response, "MISSING_CREDENTIAL", 3)
        assert "PANDA_DATA_USERNAME" in response["error"]["message"]
    assert sdk.calls == []


def test_credentials_come_from_dotenv_in_the_working_directory(capsys, sdk, monkeypatch, tmp_path):
    monkeypatch.delenv("PANDA_DATA_USERNAME")
    monkeypatch.delenv("PANDA_DATA_PASSWORD")
    (tmp_path / ".env").write_text(
        "PANDA_DATA_USERNAME=dotenv-user\nPANDA_DATA_PASSWORD=dotenv-pass\n", encoding="utf-8"
    )
    # The client copies .env values into os.environ; monkeypatch restores them afterwards.
    code, response = run(capsys, *FUND_ARGV)
    assert code == 0, response
    assert sdk.calls[0] == ("init_token", {"username": "dotenv-user", "password": "dotenv-pass"})


def test_missing_sdk_is_a_dependency_error_with_an_install_hint(capsys, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "panda_data", None)
    for argv in (
        FUND_ARGV,
        ["adj-factor", "--write"],
        ["ref", "index-detail"],
        ["etf", "net", "--start", "20240101", "--end", "20240131"],
        ["raw", "--list"],
        ["raw", "get_trade_cal"],
    ):
        code, response = run(capsys, *argv)
        assert_error(code, response, "MISSING_DEPENDENCY", 3)
        assert response["error"]["hint"] == "uv sync --extra panda_data"


def test_missing_sdk_is_reported_before_missing_credentials(capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "panda_data", None)
    monkeypatch.delenv("PANDA_DATA_USERNAME")
    code, response = run(capsys, *FUND_ARGV)
    assert_error(code, response, "MISSING_DEPENDENCY", 3)


def test_sdk_failures_are_upstream_errors_and_keep_wrapped_causes(capsys, sdk):
    sdk.responses["get_fund_daily"] = RuntimeError("provider is unavailable")
    code, response = run(capsys, *FUND_ARGV)
    assert_error(code, response, "UPSTREAM_ERROR", 4)
    # The client wraps fund chunk failures; the original cause stays visible.
    assert "get_fund_daily failed" in response["error"]["message"]
    assert "provider is unavailable" in response["error"]["message"]
    sdk.responses["get_market_data"] = ConnectionError("connection reset")
    code, response = run(
        capsys, "bars", "--asset", "stock", "--symbols", "SHSE.600000", "--start", "2024-01-01"
    )
    assert_error(code, response, "UPSTREAM_ERROR", 4)


def test_timeouts_and_late_import_errors_keep_distinct_codes(capsys, sdk):
    sdk.responses["get_fund_daily"] = TimeoutError("provider timed out")
    code, response = run(capsys, *FUND_ARGV)
    assert_error(code, response, "TIMEOUT", 124)
    sdk.responses["get_fund_daily"] = ImportError("No module named 'panda_data_extra'")
    code, response = run(capsys, *FUND_ARGV)
    assert_error(code, response, "MISSING_DEPENDENCY", 3)
    sdk.responses["get_fund_daily"] = RuntimeError(
        "PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD not set"
    )
    code, response = run(capsys, *FUND_ARGV)
    assert_error(code, response, "MISSING_CREDENTIAL", 3)


# ---------------------------------------------------------------------------
# ingest.future-ticks
# ---------------------------------------------------------------------------


@pytest.fixture
def ticks(monkeypatch, sdk, tmp_path):
    """Fake the downloader's network and process work; record what it was asked to run."""
    state = SimpleNamespace(single=[], all=[], init=[], status="ok", all_code=0)
    monkeypatch.setattr(tick, "ROOT", tmp_path)
    monkeypatch.setattr(
        tick, "_init_panda_data", lambda username, password, **kwargs: state.init.append(kwargs)
    )

    def run_underlying(args, **kwargs):
        state.single.append((args, kwargs))
        return SimpleNamespace(status=state.status)

    def run_all_underlyings(args, **kwargs):
        state.all.append((args, kwargs))
        return state.all_code

    monkeypatch.setattr(tick, "run_underlying", run_underlying)
    monkeypatch.setattr(tick, "run_all_underlyings", run_all_underlyings)
    return state


def test_future_ticks_maps_every_option_to_the_downloader(capsys, ticks, tmp_path):
    out = tmp_path / "ticks" / "AG"
    code, response = run(
        capsys,
        "future-ticks",
        "--underlying",
        "AG",
        "--start",
        "2024-01-01",
        "--end",
        "20240131",
        "--output-dir",
        str(out),
        "--workers",
        "2",
        "--symbol-batch-size",
        "4",
        "--progress-every",
        "5",
        "--max-retries",
        "1",
        "--retry-sleep",
        "0.5",
        "--retry-failed-rounds",
        "0",
        "--http-timeout",
        "30",
        "--stall-timeout",
        "120",
        "--provider-timeout-threshold",
        "2",
        "--allow-provider-timeout-gaps",
        "--no-fallback-on-batch-timeout",
        "--compression",
        "snappy",
        "--compression-level",
        "3",
        "--overwrite",
        "--include-dominant",
        "--refresh-discovery",
        "--no-combine",
        "--monthly-output",
        "--no-month-by-month",
        "--min-free-disk-gb",
        "5",
        "--limit-tasks",
        "7",
        "--limit-underlyings",
        "3",
        "--priority-underlyings",
        "AG,SA",
    )
    assert code == 0, response
    assert len(ticks.single) == 1 and ticks.all == []
    parsed, kwargs = ticks.single[0]
    assert kwargs["underlying"] == "AG" and kwargs["workers"] == 2
    assert kwargs["username"] == "fake-user" and kwargs["password"] == "fake-password"
    assert (parsed.start_date, parsed.end_date) == ("20240101", "20240131")
    assert parsed.output_dir == str(out) and parsed.output_root is None
    assert parsed.all_underlyings is False
    expected = {
        "symbol_batch_size": 4,
        "progress_every": 5,
        "max_retries": 1,
        "retry_sleep": 0.5,
        "retry_failed_rounds": 0,
        "http_timeout": 30,
        "stall_timeout": 120,
        "provider_timeout_threshold": 2,
        "allow_provider_timeout_gaps": True,
        "no_fallback_on_batch_timeout": True,
        "compression": "snappy",
        "compression_level": 3,
        "overwrite": True,
        "include_dominant": True,
        "refresh_discovery": True,
        "no_combine": True,
        "monthly_output": True,
        "no_month_by_month": True,
        "min_free_disk_gb": 5.0,
        "limit_tasks": 7,
        "limit_underlyings": 3,
        "priority_underlyings": "AG,SA",
    }
    for name, value in expected.items():
        assert getattr(parsed, name) == value, name
    assert ticks.init == [{"http_timeout": 30}]
    data = response["data"]
    assert data["status"] == "ok" and data["exit_code"] == 0
    assert data["output_dir"] == str(out.resolve()) and "--underlying" in data["argv"]


def test_future_ticks_defaults_follow_the_downloader(capsys, ticks, tmp_path):
    code, response = run(capsys, "future-ticks", "--underlying", "AG")
    assert code == 0, response
    parsed, kwargs = ticks.single[0]
    reference = tick._parse_args([])
    model = ingest_cli.FutureTicksInput()
    for name in (
        "symbol_batch_size",
        "progress_every",
        "max_retries",
        "retry_sleep",
        "retry_failed_rounds",
        "http_timeout",
        "stall_timeout",
        "provider_timeout_threshold",
        "allow_provider_timeout_gaps",
        "compression",
        "compression_level",
        "overwrite",
        "include_dominant",
        "refresh_discovery",
        "monthly_output",
        "min_free_disk_gb",
        "limit_tasks",
        "limit_underlyings",
        "priority_underlyings",
        "all_underlyings",
    ):
        assert getattr(model, name) == getattr(reference, name), name
        assert getattr(parsed, name) == getattr(reference, name), name
    # The model's positive switches mirror the downloader's --no-x switches.
    for positive, negative in (
        ("fallback_on_batch_timeout", "no_fallback_on_batch_timeout"),
        ("combine", "no_combine"),
        ("month_by_month", "no_month_by_month"),
    ):
        assert getattr(model, positive) is (not getattr(reference, negative)), positive
        assert getattr(parsed, negative) is False, negative
    assert (parsed.start_date, parsed.end_date) == (reference.start_date, reference.end_date)
    assert kwargs["workers"] == reference.workers
    # An underlying other than SA must not land in the downloader's SA default directory.
    assert parsed.output_dir == "data/export/panda_future_ticks/AG"
    assert response["data"]["output_dir"] == str(
        (tmp_path / "data" / "export" / "panda_future_ticks" / "AG").resolve()
    )


def test_future_ticks_exit_code_follows_task_failures(capsys, ticks, tmp_path):
    ticks.status = "failed"
    code, response = run(capsys, "future-ticks", "--output-dir", str(tmp_path / "ticks"))
    assert code == 1 and response["ok"] is False
    assert response["data"]["status"] == "failed" and response["data"]["exit_code"] == 1
    assert response["error"]["code"] == "CHECK_FAILED"
    ticks.status = "skipped"
    code, response = run(capsys, "future-ticks", "--output-dir", str(tmp_path / "ticks"))
    assert code == 0 and response["data"]["status"] == "ok"


def test_future_ticks_all_underlyings_mode(capsys, ticks, tmp_path):
    root = tmp_path / "all"
    code, response = run(
        capsys,
        "future-ticks",
        "--all-underlyings",
        "--output-root",
        str(root),
        "--workers",
        "3",
    )
    assert code == 0, response
    parsed, kwargs = ticks.all[0]
    assert ticks.single == [] and parsed.all_underlyings is True
    assert parsed.output_root == str(root) and kwargs["username"] == "fake-user"
    assert response["data"]["output_dir"] == str(root.resolve())
    ticks.all_code = 1
    code, response = run(capsys, "future-ticks", "--all-underlyings", "--output-root", str(root))
    assert code == 1 and response["data"]["status"] == "failed"
    ticks.all_code = 0
    code, response = run(capsys, "future-ticks", "--all-underlyings")
    assert code == 0
    assert ticks.all[-1][0].output_root == "data/export/panda_future_ticks"


def test_future_ticks_output_root_in_single_mode_uses_the_underlying_subdirectory(
    capsys, ticks, tmp_path
):
    code, response = run(
        capsys, "future-ticks", "--underlying", "SA", "--output-root", str(tmp_path / "root")
    )
    assert code == 0, response
    assert ticks.single[0][0].output_root == str(tmp_path / "root")
    assert response["data"]["output_dir"] == str((tmp_path / "root" / "SA").resolve())


@pytest.mark.parametrize(
    "extra",
    [
        ["--all-underlyings", "--output-dir", "somewhere"],
        ["--output-dir", "a", "--output-root", "b"],
        ["--underlying", "../AG"],
        ["--underlying", "AG,SA"],
        ["--start", "2024-02-01", "--end", "2024-01-01"],
        ["--workers", "0"],
        ["--http-timeout", "0"],
        ["--start", "soon"],
    ],
)
def test_future_ticks_rejects_invalid_inputs_without_running(capsys, ticks, extra):
    code, response = run(capsys, "future-ticks", *extra)
    assert_error(code, response, "INVALID_INPUT", 2)
    assert ticks.single == [] and ticks.all == [] and ticks.init == []


def test_future_ticks_never_writes_into_managed_store_namespaces(capsys, ticks, tmp_path):
    root = tmp_path / "data"
    for target in (root / "market" / "ticks", root / "adj_factor", root / "backtest" / "x"):
        code, response = run(
            capsys, "future-ticks", "--output-dir", str(target), "--data-root", str(root)
        )
        assert_error(code, response, "INVALID_INPUT", 2)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    code, response = run(capsys, "future-ticks", "--output-dir", str(blocker))
    assert_error(code, response, "INVALID_INPUT", 2)
    assert ticks.single == [] and not root.exists()
    # Existing non-managed directories are resumed by the downloader, not rejected.
    resume = tmp_path / "ticks"
    resume.mkdir()
    code, response = run(capsys, "future-ticks", "--output-dir", str(resume))
    assert code == 0, response


def test_future_ticks_credential_and_sdk_errors(capsys, ticks, monkeypatch, tmp_path):
    monkeypatch.delenv("PANDA_DATA_PASSWORD")
    code, response = run(capsys, "future-ticks", "--output-dir", str(tmp_path / "t"))
    assert_error(code, response, "MISSING_CREDENTIAL", 3)
    monkeypatch.setenv("PANDA_DATA_PASSWORD", "fake-password")
    monkeypatch.setitem(sys.modules, "panda_data", None)
    code, response = run(capsys, "future-ticks", "--output-dir", str(tmp_path / "t"))
    assert_error(code, response, "MISSING_DEPENDENCY", 3)
    assert ticks.single == [] and ticks.init == []


def test_future_ticks_downloader_failures_are_classified(capsys, ticks, monkeypatch, tmp_path):
    def broken(args, **kwargs):
        raise RuntimeError("provider is unavailable")

    monkeypatch.setattr(tick, "run_underlying", broken)
    code, response = run(capsys, "future-ticks", "--output-dir", str(tmp_path / "t"))
    assert_error(code, response, "UPSTREAM_ERROR", 4)
    monkeypatch.setattr(
        tick, "run_underlying", lambda args, **kwargs: (_ for _ in ()).throw(TimeoutError("slow"))
    )
    code, response = run(capsys, "future-ticks", "--output-dir", str(tmp_path / "t"))
    assert_error(code, response, "TIMEOUT", 124)
