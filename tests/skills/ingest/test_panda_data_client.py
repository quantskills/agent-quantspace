"""Offline tests for PandaDataClient configuration handling."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from skills.ingest import PandaDataClient


def test_client_ignores_pandaai_env_names(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("PANDA_DATA_USERNAME", raising=False)
    monkeypatch.delenv("PANDA_DATA_PASSWORD", raising=False)
    monkeypatch.setenv("PANDAAI_USERNAME", "alias-user")
    monkeypatch.setenv("PANDAAI_PASSWORD", "alias-pass")
    monkeypatch.chdir(tmp_path)

    client = PandaDataClient()

    assert client._username == ""
    assert client._password == ""


def test_client_loads_panda_data_dotenv_from_current_working_directory(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("PANDA_DATA_USERNAME", raising=False)
    monkeypatch.delenv("PANDA_DATA_PASSWORD", raising=False)
    monkeypatch.delenv("PANDAAI_USERNAME", raising=False)
    monkeypatch.delenv("PANDAAI_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "PANDA_DATA_USERNAME=dotenv-user\nPANDA_DATA_PASSWORD=dotenv-pass\n",
        encoding="utf-8",
    )

    client = PandaDataClient()

    assert client._username == "dotenv-user"
    assert client._password == "dotenv-pass"


def _fake_fund_client(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def init_token(**kwargs):
        calls.append(("init_token", kwargs))

    def endpoint(name):
        def call(**kwargs):
            calls.append((name, kwargs))
            return pd.DataFrame(
                {
                    "symbol": ["510300.SH"],
                    "date": ["20250613"],
                    "close": [3.98],
                }
            )

        return call

    names = [
        "get_fund_detail",
        "get_fund_daily",
        "get_fund_daily_pre",
        "get_fund_daily_post",
        "get_fund_etf_cr_limits",
        "get_fund_etf_cr_net",
        "get_fund_etf_constituents",
        "get_fund_etf_cr",
    ]
    sdk = SimpleNamespace(
        init_token=init_token,
        **{name: endpoint(name) for name in names},
    )
    client = PandaDataClient(username="test-user", password="test-password")
    monkeypatch.setattr(client, "_sdk", lambda: sdk)
    return client, calls


def test_get_fund_detail_passes_filters_and_converts_symbol(monkeypatch) -> None:
    client, calls = _fake_fund_client(monkeypatch)

    result = client.get_fund_detail(
        "SHSE.510300",
        exchange="SH",
        type="E",
        operation_mode="O",
        etf_lof_type="ETF",
        is_class_fund=0,
        index_fund_type="I",
        status="L",
        fund_status="A",
        fields=["name", "management_short_name"],
    )

    assert calls[0] == (
        "init_token",
        {"username": "test-user", "password": "test-password"},
    )
    assert calls[1] == (
        "get_fund_detail",
        {
            "symbol": "510300.SH",
            "exchange": "SH",
            "type": "E",
            "operation_mode": "O",
            "etf_lof_type": "ETF",
            "is_class_fund": 0,
            "index_fund_type": "I",
            "status": "L",
            "fund_status": "A",
            "fields": ["name", "management_short_name"],
        },
    )
    assert result["symbol"].tolist() == ["SHSE.510300"]


@pytest.mark.parametrize(
    "method_name",
    [
        "get_fund_daily",
        "get_fund_daily_pre",
        "get_fund_daily_post",
        "get_fund_etf_cr_limits",
        "get_fund_etf_cr_net",
        "get_fund_etf_constituents",
        "get_fund_etf_cr",
    ],
)
def test_fund_date_range_endpoints_use_fund_sdk_methods(monkeypatch, method_name: str) -> None:
    client, calls = _fake_fund_client(monkeypatch)

    result = getattr(client, method_name)(
        "20250610",
        "20250613",
        symbol=["SHSE.510300", "SZSE.159915"],
        exchange=["SH", "SZ"],
        fields=["close", "volume"],
    )

    assert calls[1] == (
        method_name,
        {
            "start_date": "20250610",
            "end_date": "20250613",
            "symbol": ["510300.SH", "159915.SZ"],
            "exchange": ["SH", "SZ"],
            "fields": ["close", "volume"],
        },
    )
    assert result["symbol"].tolist() == ["SHSE.510300"]


@pytest.mark.parametrize(
    "method_name",
    ["get_fund_daily", "get_fund_daily_pre", "get_fund_daily_post"],
)
def test_fund_daily_methods_split_long_ranges_and_concatenate_in_order(
    monkeypatch, method_name: str
) -> None:
    calls: list[tuple[str, dict]] = []

    def init_token(**kwargs) -> None:
        calls.append(("init_token", kwargs))

    def endpoint(**kwargs) -> pd.DataFrame:
        calls.append((method_name, kwargs))
        return pd.DataFrame(
            {
                "symbol": ["510300.SH"],
                "date": [kwargs["start_date"]],
                "chunk_end": [kwargs["end_date"]],
            }
        )

    sdk = SimpleNamespace(init_token=init_token, **{method_name: endpoint})
    client = PandaDataClient(username="test-user", password="test-password")
    monkeypatch.setattr(client, "_sdk", lambda: sdk)

    result = getattr(client, method_name)(
        "20240101",
        "20250101",
        symbol="SHSE.510300",
        exchange="SH",
        fields=["close"],
    )

    assert calls == [
        ("init_token", {"username": "test-user", "password": "test-password"}),
        (
            method_name,
            {
                "start_date": "20240101",
                "end_date": "20241230",
                "symbol": "510300.SH",
                "exchange": "SH",
                "fields": ["close"],
            },
        ),
        (
            method_name,
            {
                "start_date": "20241231",
                "end_date": "20250101",
                "symbol": "510300.SH",
                "exchange": "SH",
                "fields": ["close"],
            },
        ),
    ]
    assert result.to_dict("list") == {
        "symbol": ["SHSE.510300", "SHSE.510300"],
        "date": ["20240101", "20241231"],
        "chunk_end": ["20241230", "20250101"],
    }


def test_fund_daily_long_range_preserves_empty_response_schema(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def init_token(**kwargs) -> None:
        calls.append(("init_token", kwargs))

    def get_fund_daily(**kwargs) -> pd.DataFrame:
        calls.append(("get_fund_daily", kwargs))
        return pd.DataFrame(columns=["symbol", "date", "close"])

    sdk = SimpleNamespace(init_token=init_token, get_fund_daily=get_fund_daily)
    client = PandaDataClient(username="test-user", password="test-password")
    monkeypatch.setattr(client, "_sdk", lambda: sdk)

    result = client.get_fund_daily("20240101", "20250101", symbol="SHSE.510300")

    assert result.empty
    assert result.columns.tolist() == ["symbol", "date", "close"]
    assert [call[0] for call in calls] == ["init_token", "get_fund_daily", "get_fund_daily"]


@pytest.mark.parametrize(
    ("start_date", "end_date", "message"),
    [
        ("2024-01-01", "20240102", "start_date must be a YYYYMMDD string"),
        ("20240230", "20240301", "start_date must be a valid YYYYMMDD date"),
        ("20240102", "20240101", "start_date must be before or equal to end_date"),
    ],
)
def test_fund_daily_rejects_invalid_date_ranges(
    start_date: str, end_date: str, message: str
) -> None:
    client = PandaDataClient(username="test-user", password="test-password")

    with pytest.raises(ValueError, match=message):
        client.get_fund_daily(start_date, end_date, symbol="SHSE.510300")


def test_fund_daily_stops_on_failed_chunk_with_range_context(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def init_token(**kwargs) -> None:
        calls.append(("init_token", kwargs))

    def get_fund_daily(**kwargs) -> pd.DataFrame:
        calls.append(("get_fund_daily", kwargs))
        if kwargs["start_date"] == "20241231":
            raise ConnectionError("temporary provider failure")
        return pd.DataFrame({"symbol": ["510300.SH"], "date": [kwargs["start_date"]]})

    sdk = SimpleNamespace(init_token=init_token, get_fund_daily=get_fund_daily)
    client = PandaDataClient(username="test-user", password="test-password")
    monkeypatch.setattr(client, "_sdk", lambda: sdk)

    with pytest.raises(
        RuntimeError,
        match="get_fund_daily failed for date range 20241231 to 20251230",
    ) as error:
        client.get_fund_daily("20240101", "20261231", symbol="SHSE.510300")

    assert isinstance(error.value.__cause__, ConnectionError)
    assert [call[0] for call in calls] == ["init_token", "get_fund_daily", "get_fund_daily"]
