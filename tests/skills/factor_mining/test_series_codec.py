"""Lossless series codec tests for factor_mining Phase 02."""

from __future__ import annotations

import math
from datetime import date

import pandas as pd
import pytest

from skills.factor_mining.adapters.series_codec import (
    SeriesCodecError,
    series_from_payload,
    series_to_payload,
)
from skills.factor_mining.contracts import FailureCode


def test_codec_preserves_ny_dst_fallback_and_spring_forward() -> None:
    # Fall-back: two distinct 01:00 America/New_York instants.
    fall = pd.date_range("2024-11-03 00:00", periods=5, freq="h", tz="America/New_York")
    idx = pd.MultiIndex.from_arrays(
        [pd.Index(["AAA"] * len(fall), dtype=object), fall],
        names=["symbol", "eob"],
    )
    series = pd.Series(range(len(fall)), index=idx, dtype="float64")
    restored = series_from_payload(series_to_payload(series))
    restored_times = restored.index.get_level_values(1)
    assert str(restored_times.tz) == "America/New_York"
    assert list(restored_times) == list(fall)
    # The repeated local 01:00 hour must remain two distinct UTC instants.
    assert restored_times[1].value != restored_times[2].value

    spring = pd.date_range("2024-03-10 00:00", periods=5, freq="h", tz="America/New_York")
    idx2 = pd.MultiIndex.from_arrays(
        [pd.Index(["AAA"] * len(spring), dtype=object), spring],
        names=["symbol", "eob"],
    )
    restored2 = series_from_payload(
        series_to_payload(pd.Series(range(len(spring)), index=idx2, dtype="float64"))
    )
    assert list(restored2.index.get_level_values(1)) == list(spring)


def test_codec_preserves_shanghai_python_dates_and_date_like_strings() -> None:
    shanghai = pd.DatetimeIndex(
        ["2024-01-01 09:30", "2024-01-02 09:30"],
        tz="Asia/Shanghai",
    )
    idx = pd.MultiIndex.from_arrays(
        [pd.Index(["AAA", "BBB"], dtype=object), shanghai],
        names=["symbol", "eob"],
    )
    restored = series_from_payload(
        series_to_payload(pd.Series([1.0, float("nan")], index=idx))
    )
    assert str(restored.index.get_level_values(1).tz) == "Asia/Shanghai"
    assert math.isnan(restored.iloc[1])
    payload = series_to_payload(pd.Series([1.0, 2.0], index=idx))
    assert payload["levels"][1]["encoding"] == "utc_ns"
    assert payload["levels"][1]["tz"] == "Asia/Shanghai"

    date_level = pd.Index([date(2024, 1, 1), date(2024, 1, 2)], dtype=object)
    idx_dates = pd.MultiIndex.from_arrays(
        [pd.Index(["AAA", "BBB"], dtype=object), date_level],
        names=["symbol", "asof"],
    )
    restored_dates = series_from_payload(
        series_to_payload(pd.Series([0.1, 0.2], index=idx_dates))
    )
    assert payload_kind(series_to_payload(pd.Series([0.1, 0.2], index=idx_dates)), 1) == "date"
    assert list(restored_dates.index.get_level_values(1)) == [
        date(2024, 1, 1),
        date(2024, 1, 2),
    ]

    obj_time = pd.Index(["2024-01-01", "2024-01-02"], dtype=object)
    idx_str = pd.MultiIndex.from_arrays(
        [pd.Index(["AAA", "BBB"], dtype=object), obj_time],
        names=["symbol", "trade_day"],
    )
    restored_str = series_from_payload(
        series_to_payload(pd.Series([0.1, 0.2], index=idx_str))
    )
    assert payload_kind(series_to_payload(pd.Series([0.1, 0.2], index=idx_str)), 1) == "object"
    assert restored_str.index.get_level_values(1).dtype == object
    assert list(restored_str.index.get_level_values(1)) == ["2024-01-01", "2024-01-02"]


def payload_kind(payload: dict, level: int) -> str:
    return payload["levels"][level]["kind"]


def test_codec_preserves_inf_bool_and_rejects_corrupt_descriptors() -> None:
    idx = pd.MultiIndex.from_arrays(
        [
            pd.Index(["AAA", "BBB", "CCC"], dtype=object),
            pd.date_range("2024-01-01", periods=3, name="eob"),
        ],
        names=["symbol", "eob"],
    )
    values = pd.Series([1.0, math.inf, -math.inf], index=idx)
    restored = series_from_payload(series_to_payload(values))
    assert restored.iloc[1] == math.inf
    assert restored.iloc[2] == -math.inf

    mask = pd.Series([True, False, True], index=idx, dtype=bool)
    restored_mask = series_from_payload(series_to_payload(mask))
    assert restored_mask.dtype == bool
    assert list(restored_mask) == [True, False, True]

    payload = series_to_payload(values)
    payload["levels"][0]["values"] = payload["levels"][0]["values"][:-1]
    with pytest.raises(SeriesCodecError) as exc:
        series_from_payload(payload)
    assert exc.value.code is FailureCode.ARTIFACT_PERSIST_FAILED

    payload2 = series_to_payload(values)
    payload2["levels"][1]["extra"] = 1
    with pytest.raises(SeriesCodecError):
        series_from_payload(payload2)

    payload4 = series_to_payload(values)
    payload4["levels"][1]["encoding"] = "wall_clock"
    with pytest.raises(SeriesCodecError):
        series_from_payload(payload4)

    aware = pd.DatetimeIndex(
        ["2024-01-01", "2024-01-02", "2024-01-03"], tz="Asia/Shanghai"
    )
    idx4 = pd.MultiIndex.from_arrays(
        [pd.Index(["A", "B", "C"], dtype=object), aware],
        names=["symbol", "eob"],
    )
    bad = series_to_payload(pd.Series([1.0, 2.0, 3.0], index=idx4))
    bad["levels"][1]["values"] = ["x", 1, 2]
    with pytest.raises(SeriesCodecError):
        series_from_payload(bad)


def test_codec_rejects_corrupt_typed_level_values() -> None:
    bool_idx = pd.MultiIndex.from_arrays(
        [
            pd.Index([True, False], dtype=bool),
            pd.date_range("2024-01-01", periods=2, name="eob"),
        ],
        names=["flag", "eob"],
    )
    payload = series_to_payload(pd.Series([1.0, 2.0], index=bool_idx))
    assert payload["levels"][0]["kind"] == "bool"
    payload["levels"][0]["values"][0] = "false"
    with pytest.raises(SeriesCodecError) as exc:
        series_from_payload(payload)
    assert exc.value.code is FailureCode.ARTIFACT_PERSIST_FAILED

    int_idx = pd.MultiIndex.from_arrays(
        [
            pd.Index([1, 2], dtype="int64"),
            pd.date_range("2024-01-01", periods=2, name="eob"),
        ],
        names=["bucket", "eob"],
    )
    int_payload = series_to_payload(pd.Series([1.0, 2.0], index=int_idx))
    int_payload["levels"][0]["values"][0] = True
    with pytest.raises(SeriesCodecError):
        series_from_payload(int_payload)
    int_payload2 = series_to_payload(pd.Series([1.0, 2.0], index=int_idx))
    int_payload2["levels"][0]["values"][0] = "1"
    with pytest.raises(SeriesCodecError):
        series_from_payload(int_payload2)

    float_payload = series_to_payload(pd.Series([1.0, 2.0], index=int_idx))
    float_payload["levels"][0]["tz"] = "UTC"
    with pytest.raises(SeriesCodecError):
        series_from_payload(float_payload)

    naive = series_to_payload(pd.Series([1.0, 2.0], index=bool_idx))
    naive["levels"][1]["values"][0] = "2024-01-01T00:00:00+00:00"
    with pytest.raises(SeriesCodecError):
        series_from_payload(naive)

    values = series_to_payload(pd.Series([math.inf, -math.inf], index=bool_idx))
    assert values["data"][0] == {"inf": 1}
    assert values["data"][1] == {"inf": -1}
    for bad_marker in (0, 2, "1", True, False, 1.0, None):
        corrupt = series_to_payload(pd.Series([1.0, 2.0], index=bool_idx))
        corrupt["data"][0] = {"inf": bad_marker}
        with pytest.raises(SeriesCodecError):
            series_from_payload(corrupt)
