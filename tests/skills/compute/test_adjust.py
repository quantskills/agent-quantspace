from __future__ import annotations

import pandas as pd

from skills.compute.adjust import forward_adjust, repair_zero_volume_price_stubs


def test_forward_adjust_scales_historical_prices_and_volume() -> None:
    idx = pd.date_range("2024-01-01", periods=3, name="eob")
    raw = pd.DataFrame({"close": [10.0, 12.0, 14.0], "volume": [100.0, 100.0, 100.0]}, index=idx)
    adj = pd.DataFrame(
        {"ex_cum_factor": [2.0], "ex_factor": [2.0]},
        index=pd.DatetimeIndex(["2024-01-02"], name="ex_date"),
    )

    result = forward_adjust(raw, adj, price_cols=("close",))

    assert result.loc[idx[0], "close"] == 5.0
    assert result.loc[idx[0], "volume"] == 200.0
    assert result.loc[idx[-1], "close"] == 14.0


def test_repair_zero_volume_price_stubs_uses_prior_tradable_close() -> None:
    idx = pd.date_range("2024-01-01", periods=3, name="eob")
    frame = pd.DataFrame(
        {"open": [10.0, 99.0, 11.0], "high": [10.0, 99.0, 11.0], "low": [10.0, 99.0, 11.0], "close": [10.0, 99.0, 11.0], "volume": [100.0, 0.0, 100.0]},
        index=idx,
    )

    result = repair_zero_volume_price_stubs(frame)

    assert result.loc[idx[1], "close"] == 10.0
    assert result.loc[idx[1], "open"] == 10.0
