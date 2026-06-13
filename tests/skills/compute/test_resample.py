from __future__ import annotations

import pandas as pd
import pytest

from skills.compute.resample import resample_to_5m


def test_resample_to_5m_aggregates_ohlcv_inside_session() -> None:
    idx = pd.date_range("2024-01-01 09:31", periods=5, freq="min", name="eob")
    frame = pd.DataFrame(
        {"open": [1, 2, 3, 4, 5], "high": [2, 3, 4, 5, 6], "low": [0, 1, 2, 3, 4], "close": [1, 2, 3, 4, 5], "volume": [10, 20, 30, 40, 50]},
        index=idx,
    )

    result = resample_to_5m(frame)

    assert result.index[0] == pd.Timestamp("2024-01-01 09:35")
    assert result.iloc[0].to_dict() == {"open": 1, "high": 6, "low": 0, "close": 5, "volume": 150}


def test_resample_to_5m_rejects_timezone_aware_index() -> None:
    idx = pd.date_range("2024-01-01 09:31", periods=1, freq="min", tz="Asia/Shanghai")
    frame = pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}, index=idx)

    with pytest.raises(ValueError, match="tz-naive"):
        resample_to_5m(frame)
