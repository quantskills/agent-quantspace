from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.time_series.ml import class_probability, probability_spread_weights


def test_probability_spread_weights_require_both_classes() -> None:
    probabilities = np.array([[0.7, 0.1, 0.2], [0.1, 0.1, 0.8]])
    index = pd.date_range("2024-01-01", periods=2, name="eob")

    weights = probability_spread_weights(
        probabilities,
        classes=np.array([0, 1, 2]),
        index=index,
        symbol="CFFEX.IF99",
        threshold=0.15,
    )

    assert weights["CFFEX.IF99"].tolist() == [-1.0, 1.0]

    with pytest.raises(ValueError, match="required encoded label"):
        probability_spread_weights(
            probabilities[:, :2],
            classes=np.array([1, 2]),
            index=index,
            symbol="CFFEX.IF99",
        )


def test_class_probability_extracts_requested_column() -> None:
    probabilities = np.array([[0.2, 0.3, 0.5], [0.6, 0.3, 0.1]])

    result = class_probability(probabilities, classes=np.array([0, 1, 2]), encoded_label=2)

    assert result.tolist() == [0.5, 0.1]
