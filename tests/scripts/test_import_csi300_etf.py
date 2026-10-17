from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from scripts import import_csi300_etf


def test_year_chunks_split_range_into_contiguous_one_year_windows() -> None:
    chunks = import_csi300_etf._year_chunks("20200101", "20220301")

    assert chunks == [
        ("20200101", "20201231"),
        ("20210101", "20211231"),
        ("20220101", "20220301"),
    ]


@pytest.mark.parametrize(
    ("adjust", "frequency", "expected_close", "expected_volume"),
    [
        # cum_adj_factor is 1.0 on the first bar and 2.0 on the latest bar.
        ("none", "1d", [3.05, 4.05], [100.0, 200.0]),
        # forward adjust anchors on the latest factor: older bars scaled by 0.5.
        ("pre", "1d_adj", [1.525, 4.05], [200.0, 200.0]),
        # backward adjust anchors on the earliest factor: later bars scaled by 2.
        ("post", "1d_adj", [3.05, 8.1], [100.0, 100.0]),
    ],
)
def test_download_etf_fetches_unadjusted_yearly_chunks_and_adjusts_locally(
    monkeypatch,
    tmp_path,
    adjust: str,
    frequency: str,
    expected_close: list[float],
    expected_volume: list[float],
) -> None:
    raw = pd.DataFrame(
        {
            "date": ["20200102", "20250102"],
            "open": [3.0, 4.0],
            "high": [3.1, 4.1],
            "low": [2.9, 3.9],
            "close": [3.05, 4.05],
            "volume": [100, 200],
            "cum_adj_factor": [1.0, 2.0],
        }
    )
    calls: list[tuple[tuple, dict]] = []

    def get_fund_daily(start: str, end: str, **kwargs) -> pd.DataFrame:
        calls.append(((start, end), kwargs))
        return raw[(raw["date"] >= start) & (raw["date"] <= end)]

    def forbidden(*args, **kwargs):
        raise AssertionError("pre/post fund endpoints must not be used; adjust locally")

    client = SimpleNamespace(
        get_fund_daily=get_fund_daily,
        get_fund_daily_pre=forbidden,
        get_fund_daily_post=forbidden,
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
        "20200101", "20250103", data_root=str(tmp_path), adjust=adjust
    )

    # One unadjusted request per <=1-year chunk, always with the full field set.
    expected_chunks = import_csi300_etf._year_chunks("20200101", "20250103")
    assert [window for window, _ in calls] == expected_chunks
    assert len(expected_chunks) == 6
    assert all(
        kwargs == {"symbol": "SHSE.510300", "fields": import_csi300_etf.RAW_FIELDS}
        for _, kwargs in calls
    )

    assert saved["data_root"] == str(tmp_path)
    assert saved["symbol"] == "SHSE.510300"
    assert saved["kwargs"] == {"frequency": frequency, "source": "panda_data_fund"}
    bars = saved["bars"]
    assert bars.index.tolist() == [pd.Timestamp("2020-01-02"), pd.Timestamp("2025-01-02")]
    assert bars["close"].tolist() == pytest.approx(expected_close)
    assert bars["volume"].tolist() == pytest.approx(expected_volume)
