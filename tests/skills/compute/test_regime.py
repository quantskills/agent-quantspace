from __future__ import annotations

import pandas as pd
import pytest

from skills.compute.regime import split_by_regime


def test_split_by_regime_slices_datetime_index() -> None:
    frame = pd.DataFrame({"x": [1, 2, 3]}, index=pd.date_range("2024-01-01", periods=3))

    result = split_by_regime(frame, regimes={"first_two": ("2024-01-01", "2024-01-02")})

    assert result["first_two"]["x"].tolist() == [1, 2]


def test_split_by_regime_requires_date_level_for_multiindex() -> None:
    index = pd.MultiIndex.from_product([["AAA"], pd.date_range("2024-01-01", periods=2)], names=["symbol", "date"])
    frame = pd.DataFrame({"x": [1, 2]}, index=index)

    with pytest.raises(ValueError, match="date level"):
        split_by_regime(frame, date_level="eob")
