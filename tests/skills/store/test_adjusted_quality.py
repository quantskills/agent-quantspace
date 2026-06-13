from __future__ import annotations

import pandas as pd

from skills.store.adjusted_quality import find_zero_volume_price_jumps


def test_find_zero_volume_price_jumps_reports_implausible_stub() -> None:
    idx = pd.date_range("2024-01-01", periods=3, name="eob")
    frame = pd.DataFrame(
        {"close": [10.0, 30.0, 10.5], "volume": [100.0, 0.0, 100.0], "is_suspended": [False, True, False]},
        index=idx,
    )

    issues = find_zero_volume_price_jumps(frame, symbol="AAA", threshold=0.2)

    assert len(issues) == 1
    assert issues.loc[0, "symbol"] == "AAA"
    assert issues.loc[0, "relative_change"] == 2.0
