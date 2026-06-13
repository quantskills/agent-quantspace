from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.cross_sectional.ml_rank import rank_scores_to_weights
from strategies.time_series.ml import probability_spread_weights


def test_probability_spread_weight_mapping_is_stable() -> None:
    probabilities = np.array(
        [
            [0.10, 0.20, 0.70],
            [0.70, 0.20, 0.10],
            [0.30, 0.40, 0.30],
        ]
    )
    index = pd.date_range("2024-01-01", periods=3)

    weights = probability_spread_weights(
        probabilities,
        classes=np.array([0, 1, 2]),
        index=index,
        symbol="AAA",
        threshold=0.25,
    )

    assert weights["AAA"].tolist() == [1.0, -1.0, 0.0]


def test_rank_scores_to_weights_holds_top_ranked_symbol() -> None:
    index = pd.date_range("2024-01-01", periods=5)
    score = pd.DataFrame(
        {
            "AAA": [1.0, 3.0, 1.0, 3.0, 1.0],
            "BBB": [2.0, 1.0, 2.0, 1.0, 2.0],
        },
        index=index,
    )
    close = pd.DataFrame(
        {
            "AAA": [100.0, 101.0, 102.0, 103.0, 104.0],
            "BBB": [100.0, 99.0, 98.0, 97.0, 96.0],
        },
        index=index,
    )

    weights = rank_scores_to_weights(score, close, top_n=1, vol_lookback=2)

    assert weights.loc[index[-1], "BBB"] == pytest.approx(1.0)
    assert weights.loc[index[-1], "AAA"] == pytest.approx(0.0)
