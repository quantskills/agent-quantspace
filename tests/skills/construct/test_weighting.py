from __future__ import annotations

import pandas as pd
import pytest

from skills.construct.weighting import equal_weight, inverse_variance, risk_parity


def test_equal_weight_normalizes_votes_by_row() -> None:
    votes = pd.DataFrame({"A": [1, 0], "B": [1, 1]}, index=pd.date_range("2024-01-01", periods=2))

    weights = equal_weight(votes)

    assert weights.iloc[0].to_dict() == {"A": 0.5, "B": 0.5}
    assert weights.iloc[1].to_dict() == {"A": 0.0, "B": 1.0}


def test_risk_parity_allocates_more_to_lower_vol_asset() -> None:
    idx = pd.date_range("2024-01-01", periods=5)
    votes = pd.DataFrame(1.0, index=idx, columns=["LOW", "HIGH"])
    returns = pd.DataFrame(
        {"LOW": [0.001, 0.001, 0.002, 0.001, 0.002], "HIGH": [0.01, -0.02, 0.03, -0.01, 0.02]},
        index=idx,
    )

    weights = risk_parity(votes, returns, lookback=3, min_periods=3)

    assert weights.iloc[-1]["LOW"] > weights.iloc[-1]["HIGH"]
    assert weights.iloc[-1].sum() == pytest.approx(1.0)


def test_inverse_variance_allocates_more_to_lower_variance_asset() -> None:
    idx = pd.date_range("2024-01-01", periods=5)
    votes = pd.DataFrame(1.0, index=idx, columns=["LOW", "HIGH"])
    returns = pd.DataFrame(
        {"LOW": [0.001, 0.001, 0.002, 0.001, 0.002], "HIGH": [0.01, -0.02, 0.03, -0.01, 0.02]},
        index=idx,
    )

    weights = inverse_variance(votes, returns, lookback=3, min_periods=3)

    assert weights.iloc[-1]["LOW"] > weights.iloc[-1]["HIGH"]
    assert weights.iloc[-1].sum() == pytest.approx(1.0)
