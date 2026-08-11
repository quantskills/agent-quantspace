from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from scripts import import_csi300_etf


@pytest.mark.parametrize(
    ("adjust", "method_name"),
    [("none", "get_fund_daily"), ("pre", "get_fund_daily_pre"), ("post", "get_fund_daily_post")],
)
def test_download_csi300_etf_delegates_full_range_to_client(
    monkeypatch, tmp_path, adjust: str, method_name: str
) -> None:
    calls: list[tuple[str, tuple, dict]] = []
    raw = pd.DataFrame(
        {
            "date": ["20200102", "20250102"],
            "open": [3.0, 4.0],
            "high": [3.1, 4.1],
            "low": [2.9, 3.9],
            "close": [3.05, 4.05],
            "volume": [100, 200],
        }
    )

    def endpoint(*args, **kwargs) -> pd.DataFrame:
        calls.append((method_name, args, kwargs))
        return raw

    client = SimpleNamespace(
        get_fund_daily=endpoint,
        get_fund_daily_pre=endpoint,
        get_fund_daily_post=endpoint,
    )
    saved: dict[str, object] = {}

    class FakeDataManager:
        def __init__(self, data_root: str | None) -> None:
            saved["data_root"] = data_root

        def save_symbol(self, symbol: str, bars: pd.DataFrame, **kwargs) -> None:
            saved["symbol"] = symbol
            saved["bars"] = bars
            saved["kwargs"] = kwargs

    monkeypatch.setattr(import_csi300_etf, "PandaDataClient", lambda: client)
    monkeypatch.setattr(import_csi300_etf, "DataManager", FakeDataManager)

    import_csi300_etf.download_csi300_etf(
        "20200101", "20250101", data_root=str(tmp_path), adjust=adjust
    )

    assert calls == [
        (
            method_name,
            ("20200101", "20250101"),
            {"symbol": "SHSE.510300", "fields": import_csi300_etf.FIELDS},
        )
    ]
    assert saved["data_root"] == str(tmp_path)
    assert saved["symbol"] == "SHSE.510300"
    assert saved["kwargs"] == {"frequency": "1d", "source": "panda_data_fund"}
    assert saved["bars"].index.tolist() == [pd.Timestamp("2020-01-02"), pd.Timestamp("2025-01-02")]
