from __future__ import annotations

import pandas as pd
import pytest

from strategies.cross_sectional.rules import ma_gap_reversal_weights


def test_cross_sectional_ma_gap_reversal_uses_risk_parity_weights() -> None:
    index = pd.date_range("2024-01-01", periods=6, name="eob")
    close = pd.DataFrame(
        {
            "A": [10.0, 10.0, 10.0, 8.0, 8.0, 8.0],
            "B": [10.0, 10.0, 10.0, 11.0, 11.0, 11.0],
            "C": [10.0, 10.0, 10.0, 7.0, 7.0, 7.0],
        },
        index=index,
    )

    weights = ma_gap_reversal_weights(
        close,
        symbols=["A", "B", "C"],
        lookback=3,
        top_n=2,
        vol_lookback=2,
        rebalance_days=2,
    )

    assert set(weights.columns) == {"A", "B", "C"}
    assert weights.iloc[-1].sum() == pytest.approx(1.0)
    assert weights.iloc[-1]["B"] == 0.0
    assert weights.iloc[-1]["C"] > 0.0
