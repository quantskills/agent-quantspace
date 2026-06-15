from __future__ import annotations

import pandas as pd

from skills.ml.ml_factor import make_precomputed_factor


def test_make_precomputed_factor_reads_pivot_value_for_group_dates() -> None:
    dates = pd.date_range("2024-01-01", periods=2, name="eob")
    pivot = pd.DataFrame({"AAA": [0.2, 0.8]}, index=dates)
    factor = make_precomputed_factor(pivot, name="ml_rank")
    group = pd.DataFrame(
        {"close": [10.0, 11.0]},
        index=pd.MultiIndex.from_product([["AAA"], dates], names=["symbol", "eob"]),
    )

    result = factor(group)

    assert result.tolist() == [0.2, 0.8]
    assert factor.__name__ == "ml_rank"
