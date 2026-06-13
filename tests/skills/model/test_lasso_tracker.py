from __future__ import annotations

import pandas as pd

from skills.model.lasso_tracker import lasso_track


def test_lasso_track_returns_weights_with_bounded_row_sums() -> None:
    idx = pd.date_range("2024-01-01", periods=20)
    etf_returns = pd.DataFrame(
        {"A": [0.001] * 20, "B": [0.002] * 20, "C": [-0.001] * 20},
        index=idx,
    )
    index_returns = pd.Series([0.0015] * 20, index=idx)

    weights = lasso_track(etf_returns, index_returns, lookback=10, min_periods=5, rebalance_freq="D")

    assert weights.index.equals(idx)
    assert (weights.sum(axis=1) <= 1.0000001).all()
